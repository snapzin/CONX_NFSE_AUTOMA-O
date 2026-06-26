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


def classify_nota(meta: Optional[MetaNota], owner_digits: str) -> str:
    """Emitidas / Recebidas / Outros, do ponto de vista do dono da caixa.
    (Cancelamento e tratado a parte, cruzando os eventos — ver parse_evento.)"""
    if meta is None or not owner_digits:
        return "Outros"
    if meta.prestador_cnpj and meta.prestador_cnpj == owner_digits:
        return "Emitidas"
    if meta.tomador_cnpj and meta.tomador_cnpj == owner_digits:
        return "Recebidas"
    return "Outros"


def parse_evento(xml_str: str) -> Optional[tuple[str, str, bool]]:
    """Le um XML de EVENTO da NFS-e. Retorna (chave_da_nota_afetada, tpEvento,
    eh_cancelamento) ou None se nao for um evento valido.

    Estrutura: <evento>..<infPedReg><chNFSe/><e101101><xDesc/></e101101>..
    Cancelamento = tpEvento '101101' OU xDesc contendo 'cancel' (NT-008 oficial).
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None
    inf = _bloco(root, "infPedReg")
    if inf is None:
        return None
    chave = _so_digitos(_primeiro_texto(inf, "chNFSe"))
    if not chave:
        return None
    tp_evento, xdesc = "", ""
    for el in inf.iter():
        ln = _localname(el.tag)
        if re.fullmatch(r"e\d{4,}", ln):
            tp_evento = ln[1:]
            xdesc = _primeiro_texto(el, "xDesc")
            break
    eh_cancelamento = tp_evento == "101101" or "cancel" in (xdesc or "").lower()
    return chave, tp_evento, eh_cancelamento


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


def _contraparte_limpa(nome: str, limite_palavras: int = 3) -> str:
    """Primeiras palavras significativas do nome (ignora tokens so de digitos/
    pontuacao, ex.: CNPJ no lugar do nome). '' se nao houver nome utilizavel."""
    toks = [t for t in (nome or "").split() if re.search(r"[A-Za-zÀ-ÿ]", t)]
    return " ".join(toks[:limite_palavras])


def _nome_nota(meta: Optional[MetaNota], owner_digits: str, nsu, chave: str) -> str:
    """Nome do XML da nota: 'Numero - Contraparte - NSU.xml'.

    Contraparte = o OUTRO lado: nas emitidas e o Tomador (cliente), nas
    recebidas e o Prestador (fornecedor). O NSU no fim garante unicidade
    (numeros podem repetir entre prestadores diferentes nas recebidas).
    """
    numero = (meta.numero if meta else "") or ""
    if meta and meta.prestador_cnpj == owner_digits:
        contraparte = _contraparte_limpa(meta.tomador_nome)      # emitida -> tomador
    else:
        contraparte = _contraparte_limpa(meta.prestador_nome if meta else "")  # recebida -> prestador
    partes = [p for p in (numero, contraparte, f"NSU{nsu}") if p]
    base = " - ".join(partes) if numero or contraparte else (chave or f"NSU{nsu}")
    return _sanitizar(base) + ".xml"


def _nome_evento_cancel(numero_nota: str, chave: str, nsu) -> str:
    """Nome do XML do evento de cancelamento: 'Cancelamento - Numero - NSU.xml'."""
    partes = [p for p in ("Cancelamento", numero_nota, f"NSU{nsu}") if p]
    base = " - ".join(partes) if numero_nota else f"Cancelamento - {chave or nsu}"
    return _sanitizar(base) + ".xml"


# ───────────────────────── loop de download ─────────────────────────

@dataclass
class ResultadoADN:
    emitidas: int = 0
    recebidas: int = 0
    canceladas: int = 0             # notas canceladas (vao para a pasta Canceladas)
    ignorados_competencia: int = 0  # fora do filtro de competencia
    eventos_ignorados: int = 0      # eventos nao-cancelamento (substituicao etc.)
    nao_classificados: int = 0      # notas sem dono claro (raro)
    ultimo_nsu: int = 0
    arquivos: list[Path] = field(default_factory=list)
    erro: str = ""

    @property
    def total_salvo(self) -> int:
        return self.emitidas + self.recebidas + self.canceladas


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

    Estrutura de saida (apenas 3 pastas):  destino/{Emitidas|Recebidas|Canceladas}/
      - Emitidas : notas em que o dono e o PRESTADOR
      - Recebidas: notas em que o dono e o TOMADOR
      - Canceladas: notas que tem um evento de cancelamento (+ o XML do evento)

    Parametros:
      owner_cnpj    : CNPJ do dono da caixa (do certificado) — define Emitidas/Recebidas.
      competencias  : se dado, salva so docs cuja competencia (YYYY-MM) esteja no conjunto.
      tipos         : subconjunto de {"Emitidas","Recebidas","Canceladas"} a salvar.
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

        # ── PASSO 1: percorre a caixa inteira, separando notas dos eventos e
        #            mapeando quais notas foram CANCELADAS (o evento de
        #            cancelamento vem depois da nota, com NSU maior — por isso
        #            precisamos de dois passos). ────────────────────────────
        notas = []                 # (nsu, chave, xml, meta)
        eventos_cancel = []        # (nsu, chave_afetada, xml)
        chaves_canceladas = set()
        chave_para_meta = {}

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

            if (d.get("TipoDocumento", "") or "").upper() == "EVENTO":
                ev = parse_evento(xml)
                if ev and ev[2]:                       # eh_cancelamento
                    chaves_canceladas.add(ev[0])
                    eventos_cancel.append((nsu, ev[0], xml))
                elif ev:
                    res.eventos_ignorados += 1         # substituicao/manifestacao/etc.
                continue

            chave = _so_digitos(d.get("ChaveAcesso", ""))
            meta = parse_meta(xml)
            notas.append((nsu, chave, xml, meta))
            if chave and meta:
                chave_para_meta[chave] = meta

        # ── PASSO 2: salva. Apenas 3 pastas: Emitidas, Recebidas, Canceladas. ──
        def _no_periodo(comp: str) -> bool:
            return competencias is None or comp in competencias

        def _salvar(pasta_nome: str, arquivo: str, conteudo: str) -> bool:
            if tipos is not None and pasta_nome not in tipos:
                return False
            pasta = destino / pasta_nome
            pasta.mkdir(parents=True, exist_ok=True)
            caminho = pasta / arquivo
            try:
                caminho.write_text(conteudo, encoding="utf-8")
            except OSError as exc:
                log.warning("ADN: falha ao gravar %s: %s", caminho, exc)
                return False
            res.arquivos.append(caminho)
            return True

        for nsu, chave, xml, meta in notas:
            comp = meta.competencia_mes if meta else ""
            if not _no_periodo(comp):
                res.ignorados_competencia += 1
                continue
            if chave and chave in chaves_canceladas:
                if _salvar("Canceladas", _nome_nota(meta, owner, nsu, chave), xml):
                    res.canceladas += 1
                continue
            tipo = classify_nota(meta, owner)
            if tipo == "Emitidas" and _salvar("Emitidas", _nome_nota(meta, owner, nsu, chave), xml):
                res.emitidas += 1
            elif tipo == "Recebidas" and _salvar("Recebidas", _nome_nota(meta, owner, nsu, chave), xml):
                res.recebidas += 1
            elif tipo == "Outros":
                res.nao_classificados += 1   # sem dono claro -> nao salva (mantem 3 pastas)

        # ── PASSO 3: guarda o XML do evento de cancelamento junto, em Canceladas
        #            (mesma competencia da nota cancelada). ──────────────────
        for nsu, chave_af, xml in eventos_cancel:
            meta_nota = chave_para_meta.get(chave_af)
            comp = meta_nota.competencia_mes if meta_nota else ""
            if not _no_periodo(comp):
                continue
            numero = meta_nota.numero if meta_nota else ""
            _salvar("Canceladas", _nome_evento_cancel(numero, chave_af, nsu), xml)
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
