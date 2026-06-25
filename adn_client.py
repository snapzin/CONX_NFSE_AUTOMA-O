"""Cliente da API ADN (Ambiente de Dados Nacional) do NFS-e Nacional.

Baixa os documentos fiscais (DF-e) DIRETAMENTE da API oficial, autenticando
com o certificado digital (mTLS). Sem navegador, sem extensao, sem captcha,
sem clique por pixel — apenas HTTP + certificado.

Protocolo (engenharia reversa da extensao oficial "Baixar NFSe" v3.0.0.12):

    GET https://adn.nfse.gov.br/contribuintes/DFe/{nsu}?lote=true[&cnpjConsulta=CNPJ]
      - mTLS: o certificado .pfx do contribuinte e apresentado no handshake TLS
      - Accept: application/json
      - Comeca em NSU 0 e avanca pelo MAIOR NSU retornado no lote
      - Resposta JSON: {
            "StatusProcessamento": "...",
            "LoteDFe": [ {"NSU": int, "TipoDocumento": str,
                          "ChaveAcesso": str, "ArquivoXml": base64(gzip(xml))} ]
        }
      - Fim da caixa: StatusProcessamento == "NENHUM_DOCUMENTO_LOCALIZADO",
        lote vazio, ou HTTP 404.
      - 429/502/503/504 sao transitorios: retry com backoff.

Classificacao do documento (do ponto de vista do dono da caixa = o certificado):
    TipoDocumento == "EVENTO"            -> Eventos
    prestador (emit) == dono             -> Emitidas
    tomador   (toma) == dono             -> Recebidas
    caso contrario                       -> Outros
"""

from __future__ import annotations

import base64
import gzip
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional
from xml.etree import ElementTree as ET

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

log = logging.getLogger("nfse.adn")

ADN_BASE_URL = "https://adn.nfse.gov.br/contribuintes/DFe"
_TRANSIENT = {429, 502, 503, 504}
_TIMEOUT = (30, 120)  # (connect, read) — a 1a leitura pode demorar (mTLS + lote)


# ───────────────────────── certificado mTLS ─────────────────────────

def pfx_para_pem(pfx_path: Path, senha: str) -> tuple[bytes, bytes]:
    """Converte um .pfx em (cert_pem, key_pem) na memoria, sem tocar no disco.

    Retorna o certificado da entidade e a chave privada SEM senha, em PEM —
    formato que o `requests` aceita via `cert=(certfile, keyfile)`.
    """
    senha_b = (senha or "").encode("utf-8") or None
    key, cert, _chain = pkcs12.load_key_and_certificates(
        Path(pfx_path).read_bytes(), senha_b,
    )
    if cert is None or key is None:
        raise ValueError("PFX sem certificado ou chave privada utilizavel.")
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption(),
    )
    return cert_pem, key_pem


# ───────────────────────── parsing do XML ───────────────────────────

def _localname(tag: str) -> str:
    """Remove o namespace de uma tag ElementTree ('{ns}Nome' -> 'Nome')."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _primeiro_texto(root: ET.Element, *nomes: str) -> str:
    """Texto do primeiro elemento (em qualquer profundidade) cujo nome local
    esteja em `nomes`, na ordem dada."""
    alvo = {n.lower() for n in nomes}
    for el in root.iter():
        if _localname(el.tag).lower() in alvo and (el.text or "").strip():
            return el.text.strip()
    return ""


def _bloco(root: ET.Element, *nomes: str) -> Optional[ET.Element]:
    """Primeiro elemento (em qualquer profundidade) cujo nome local casa."""
    alvo = {n.lower() for n in nomes}
    for el in root.iter():
        if _localname(el.tag).lower() in alvo:
            return el
    return None


@dataclass
class MetaNota:
    numero: str = ""
    data_emissao_iso: str = ""   # YYYY-MM-DD
    competencia_mes: str = ""    # YYYY-MM
    prestador_cnpj: str = ""
    prestador_nome: str = ""
    tomador_cnpj: str = ""
    tomador_nome: str = ""


def parse_meta(xml_str: str) -> Optional[MetaNota]:
    """Extrai os metadados relevantes do XML da NFS-e. None se nao parsear."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    numero = _primeiro_texto(root, "nNFSe", "nDPS")
    data_emissao = _primeiro_texto(root, "dhEmi", "dhProc", "dhEvento")
    data_compet = _primeiro_texto(root, "dCompet")
    data_emissao_iso = data_emissao[:10] if data_emissao else ""
    if data_compet:
        competencia_mes = data_compet[:7]
    else:
        competencia_mes = data_emissao_iso[:7] if data_emissao_iso else ""

    emit = _bloco(root, "emit", "prest")
    toma = _bloco(root, "toma", "tomador")
    return MetaNota(
        numero=numero,
        data_emissao_iso=data_emissao_iso,
        competencia_mes=competencia_mes,
        prestador_cnpj=_so_digitos(_primeiro_texto(emit, "CNPJ", "CPF")) if emit is not None else "",
        prestador_nome=_primeiro_texto(emit, "xNome", "xRazSoc", "xFant") if emit is not None else "",
        tomador_cnpj=_so_digitos(_primeiro_texto(toma, "CNPJ", "CPF")) if toma is not None else "",
        tomador_nome=_primeiro_texto(toma, "xNome", "xRazSoc", "xFant") if toma is not None else "",
    )


def classify_tipo(tipo_doc: str, meta: Optional[MetaNota], owner_digits: str) -> str:
    """Emitidas / Recebidas / Eventos / Outros, do ponto de vista do dono."""
    if (tipo_doc or "").upper() == "EVENTO":
        return "Eventos"
    if meta is None or not owner_digits:
        return "Outros"
    if meta.prestador_cnpj and meta.prestador_cnpj == owner_digits:
        return "Emitidas"
    if meta.tomador_cnpj and meta.tomador_cnpj == owner_digits:
        return "Recebidas"
    return "Outros"


# ───────────────────────── utilitarios ──────────────────────────────

def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def decode_arquivo_xml(b64: str) -> str:
    """Decodifica ArquivoXml = base64(gzip(xml)). Cai pra texto puro se nao
    estiver comprimido (o ADN sempre comprime, mas a extensao tem o fallback)."""
    raw = base64.b64decode(b64)
    try:
        return gzip.decompress(raw).decode("utf-8")
    except (OSError, gzip.BadGzipFile):
        return raw.decode("utf-8", errors="replace")


_INVALIDO_NOME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitizar(nome: str, limite: int = 80) -> str:
    """Nome de arquivo seguro no Windows (sem caracteres proibidos, sem ponto/
    espaco no fim)."""
    nome = _INVALIDO_NOME.sub("", nome or "")[:limite].rstrip(". ")
    return nome or "sem-nome"


def _nome_arquivo(meta: Optional[MetaNota], nsu, chave: str, tipo: str) -> str:
    """Nome do XML: 'Numero Contraparte NSU.xml' (NSU sempre no fim, garante
    unicidade). Espelha o esquema 'Numero + Nome + NSU' da extensao."""
    numero = (meta.numero if meta else "") or ""
    if tipo == "Emitidas":
        contraparte = (meta.tomador_nome if meta else "") or ""
    elif tipo == "Recebidas":
        contraparte = (meta.prestador_nome if meta else "") or ""
    else:
        contraparte = ""
    contraparte = contraparte.split()[0] if contraparte.split() else ""
    partes = [p for p in (numero, contraparte, str(nsu)) if p]
    base = " ".join(partes) if partes else (chave or f"nsu_{nsu}")
    return _sanitizar(base) + ".xml"


# ───────────────────────── loop de download ─────────────────────────

@dataclass
class ResultadoADN:
    emitidas: int = 0
    recebidas: int = 0
    eventos: int = 0
    outros: int = 0
    ignorados_competencia: int = 0  # fora do filtro de competencia
    ultimo_nsu: int = 0
    arquivos: list[Path] = field(default_factory=list)
    erro: str = ""

    @property
    def total_salvo(self) -> int:
        return self.emitidas + self.recebidas + self.eventos + self.outros


def _fetch_lote(
    session: requests.Session, nsu: int, cnpj_consulta: str = "",
) -> tuple[Optional[dict], int]:
    """Busca um lote a partir de `nsu`. Retorna (json|None, http_status).
    Faz retry/backoff em erros transitorios (429/5xx)."""
    url = f"{ADN_BASE_URL}/{nsu}?lote=true"
    if cnpj_consulta:
        url += f"&cnpjConsulta={cnpj_consulta}"
    for tentativa in range(5):
        try:
            resp = session.get(
                url, headers={"Accept": "application/json"}, timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            log.warning("ADN: falha de rede no NSU %s (tentativa %d): %s",
                        nsu, tentativa + 1, exc)
            time.sleep(min(8, 2 * (2 ** tentativa)))
            continue
        if resp.status_code in _TRANSIENT:
            espera = resp.headers.get("retry-after")
            wait = min(8, int(espera)) if (espera or "").isdigit() else min(8, 2 * (2 ** tentativa))
            log.info("ADN: HTTP %d no NSU %s; aguardando %ds e tentando de novo.",
                     resp.status_code, nsu, wait)
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None, 404
        if not resp.ok:
            log.warning("ADN: HTTP %d no NSU %s.", resp.status_code, nsu)
            return None, resp.status_code
        try:
            return resp.json(), resp.status_code
        except ValueError:
            log.warning("ADN: resposta 200 sem JSON no NSU %s (manutencao?).", nsu)
            return None, resp.status_code
    return None, 0


def iter_documentos(
    session: requests.Session,
    cnpj_consulta: str = "",
    nsu_inicial: int = 0,
    cancelar: Optional[Callable[[], bool]] = None,
) -> Iterator[dict]:
    """Itera TODOS os documentos da caixa a partir de `nsu_inicial`, paginando
    pelo maior NSU de cada lote. Cada item: o dict cru do LoteDFe
    (NSU, TipoDocumento, ChaveAcesso, ArquivoXml)."""
    nsu = nsu_inicial
    while True:
        if cancelar and cancelar():
            return
        batch, status = _fetch_lote(session, nsu, cnpj_consulta)
        if status == 404 or batch is None:
            return
        lote = batch.get("LoteDFe") or []
        if batch.get("StatusProcessamento") == "NENHUM_DOCUMENTO_LOCALIZADO" or not lote:
            return

        max_no_lote = nsu
        for d in lote:
            try:
                n = int(d.get("NSU"))
            except (TypeError, ValueError):
                n = nsu
            if n > max_no_lote:
                max_no_lote = n
            yield d

        if max_no_lote <= nsu:  # nao avancou -> evita loop infinito
            return
        nsu = max_no_lote


def baixar_dfe(
    cert_path: Path,
    senha: str,
    owner_cnpj: str,
    destino: Path,
    competencias: Optional[set[str]] = None,
    cnpj_consulta: str = "",
    tipos: Optional[set[str]] = None,
    nsu_inicial: int = 0,
    cancelar: Optional[Callable[[], bool]] = None,
) -> ResultadoADN:
    """Baixa os DF-e da caixa do certificado e salva os XML em disco.

    Estrutura de saida:  destino/<Tipo>/<arquivo>.xml
      (o chamador ja passa `destino` como a pasta do cliente; aqui separamos
       por Tipo. A competencia entra como FILTRO, nao como pasta — o chamador
       decide a arvore.)

    Parametros:
      owner_cnpj    : CNPJ do dono da caixa (do certificado) — define Emitidas/Recebidas.
      competencias  : se dado, salva so docs cuja competencia (YYYY-MM) esteja no conjunto.
      tipos         : subconjunto de {"Emitidas","Recebidas","Eventos","Outros"} a salvar.
                      None = todos.
      cnpj_consulta : consulta de filial/terceiro (matriz->filial). "" = a propria caixa.
      nsu_inicial   : retomar a partir de um NSU (sync incremental). 0 = caixa inteira.
    """
    res = ResultadoADN()
    owner = _so_digitos(owner_cnpj)
    cert_pem, key_pem = pfx_para_pem(Path(cert_path), senha)

    # `requests` precisa de arquivos para o cert mTLS — gravamos cert+chave em
    # temporarios com permissao restrita e removemos no fim (a chave e sensivel).
    import tempfile
    import os

    tmp_cert = tempfile.NamedTemporaryFile(prefix="adn_cert_", suffix=".pem", delete=False)
    tmp_key = tempfile.NamedTemporaryFile(prefix="adn_key_", suffix=".pem", delete=False)
    try:
        tmp_cert.write(cert_pem); tmp_cert.close()
        tmp_key.write(key_pem); tmp_key.close()
        try:
            os.chmod(tmp_key.name, 0o600)
        except OSError:
            pass

        session = requests.Session()
        session.cert = (tmp_cert.name, tmp_key.name)

        destino = Path(destino)
        for d in iter_documentos(session, cnpj_consulta, nsu_inicial, cancelar):
            try:
                nsu = int(d.get("NSU"))
            except (TypeError, ValueError):
                nsu = res.ultimo_nsu
            res.ultimo_nsu = max(res.ultimo_nsu, nsu)

            arquivo_b64 = d.get("ArquivoXml")
            if not arquivo_b64:
                continue  # resumo sem XML (nada a salvar)

            try:
                xml = decode_arquivo_xml(arquivo_b64)
            except Exception as exc:  # noqa: BLE001
                log.warning("ADN: falha ao decodificar NSU %s: %s", nsu, exc)
                continue

            meta = parse_meta(xml)
            tipo = classify_tipo(d.get("TipoDocumento", ""), meta, owner)

            if competencias is not None:
                comp = meta.competencia_mes if meta else ""
                if comp not in competencias:
                    res.ignorados_competencia += 1
                    continue
            if tipos is not None and tipo not in tipos:
                continue

            pasta = destino / tipo
            pasta.mkdir(parents=True, exist_ok=True)
            nome = _nome_arquivo(meta, nsu, d.get("ChaveAcesso", ""), tipo)
            caminho = pasta / nome
            try:
                caminho.write_text(xml, encoding="utf-8")
            except OSError as exc:
                log.warning("ADN: falha ao gravar %s: %s", caminho, exc)
                continue

            res.arquivos.append(caminho)
            if tipo == "Emitidas":
                res.emitidas += 1
            elif tipo == "Recebidas":
                res.recebidas += 1
            elif tipo == "Eventos":
                res.eventos += 1
            else:
                res.outros += 1
    except Exception as exc:  # noqa: BLE001
        res.erro = str(exc)
        log.exception("ADN: erro ao baixar DF-e do CNPJ %s", owner)
    finally:
        for p in (tmp_cert.name, tmp_key.name):
            try:
                os.unlink(p)
            except OSError:
                pass

    return res
