"""
cert_reader.py - Leitor de certificados .pfx da pasta de clientes.

Para cada arquivo .pfx:
  - Parseia o nome do arquivo para obter nome amigavel e senha
  - Abre o .pfx com cryptography para extrair CNPJ/CPF, CN e thumbprint SHA1
  - Monta um indice por CNPJ para consumo da automacao

Padrao esperado no nome do arquivo:
    <NOME AMIGAVEL> senha <SENHA>.pfx
Exemplo:
    EMPRESA ABC senha MinhaSenha123.pfx
"""
from __future__ import annotations

import os
import re
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509 import NameOID

# PKCS#12 gerados por tokens ICP-Brasil frequentemente usam BER em vez de DER;
# o aviso repetitivo polui o log da GUI sem trazer informacao util.
warnings.filterwarnings(
    "ignore",
    message=r"PKCS#12 bundle could not be parsed as DER.*",
    category=UserWarning,
)

# Captura "<nome> senha <senha>" com variacoes comuns encontradas na pasta real.
# Exemplos aceitos:
#   "... senha 123456"
#   "..._senha 123456"
#   "... senha = MinhaSenha"
#   "... senha.MinhaSenha val.28.10.2026"
#   "... senhas 123456"
#   "... sanha 123456"  (erro de digitacao observado)
_RE_SENHA = re.compile(
    r"^(?P<nome>.+?)[\s_\-]*(?:senhas|senha|sanha)\s*(?:=|:|;|\.|-)?\s*(?P<senha>.+)$",
    re.IGNORECASE,
)
# Captura documentos contiguos de 11 ou 14 digitos.
_RE_DOC = re.compile(r"(?<!\d)(\d{14}|\d{11})(?!\d)")


@dataclass
class CertificadoInfo:
    arquivo: Path
    nome_amigavel: str
    senha: str
    cn: str
    documento: str        # CNPJ ou CPF (somente digitos)
    thumbprint_sha1: str  # uppercase hex
    serial_number: str    # serial do certificado em hexadecimal
    valido_ate: str       # dd/mm/aaaa
    erro: str = ""

    @property
    def is_cnpj(self) -> bool:
        return len(self.documento) == 14

    @property
    def cnpj(self) -> str:
        return self.documento if self.is_cnpj else ""

    def __str__(self) -> str:
        if self.is_cnpj:
            return f"{self.nome_amigavel} [CNPJ {self.documento}]"
        if len(self.documento) == 11:
            return f"{self.nome_amigavel} [CPF {self.documento}]"
        return self.nome_amigavel


def _parse_nome_arquivo(stem: str) -> tuple[str, str] | None:
    """Separa nome amigavel e senha a partir do nome do arquivo .pfx."""
    m = _RE_SENHA.match(stem)
    if not m:
        return None
    nome = m.group("nome").strip(" _-.;")
    senha = m.group("senha").strip(" _-.;")
    # Remove sufixos de validade anexados ao nome do arquivo.
    senha = re.sub(r"\s+val[\s._-].*$", "", senha, flags=re.IGNORECASE).strip(" _-.;")
    if not nome or not senha:
        return None
    return nome, senha


def _extrair_documento(cn: str, serial_subject: str) -> str:
    """
    Extrai CNPJ/CPF priorizando CNPJ (14 digitos), a partir do CN/serial do subject.
    """
    candidatos = [cn or "", serial_subject or ""]
    encontrados: list[str] = []
    for texto in candidatos:
        encontrados.extend(_RE_DOC.findall(texto))

    # Sem duplicar e mantendo ordem.
    docs_ordenados = list(dict.fromkeys(encontrados))
    for doc in docs_ordenados:
        if len(doc) == 14:
            return doc
    for doc in docs_ordenados:
        if len(doc) == 11:
            return doc
    return ""


def ler_certificado(pfx_path: Path) -> CertificadoInfo:
    """Le um .pfx individual e retorna metadados. Em erro, preenche campo .erro."""
    parsed = _parse_nome_arquivo(pfx_path.stem)
    if not parsed:
        return CertificadoInfo(
            arquivo=pfx_path,
            nome_amigavel=pfx_path.stem,
            senha="",
            cn="",
            documento="",
            thumbprint_sha1="",
            serial_number="",
            valido_ate="",
            erro="Nome nao segue padrao '... senha XXXXX'",
        )

    nome_amigavel, senha = parsed

    try:
        data = pfx_path.read_bytes()
        _key, cert, _extra = pkcs12.load_key_and_certificates(
            data,
            senha.encode("utf-8"),
        )
        if cert is None:
            raise ValueError("PFX nao contem certificado")

        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        cn = cn_attrs[0].value if cn_attrs else ""

        serial_attrs = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
        serial_subject = serial_attrs[0].value if serial_attrs else ""

        documento = _extrair_documento(cn, serial_subject)
        thumb = cert.fingerprint(hashes.SHA1()).hex().upper()
        valido_ate = cert.not_valid_after_utc.strftime("%d/%m/%Y")
        serial_number = format(cert.serial_number, "X")

        return CertificadoInfo(
            arquivo=pfx_path,
            nome_amigavel=nome_amigavel,
            senha=senha,
            cn=cn,
            documento=documento,
            thumbprint_sha1=thumb,
            serial_number=serial_number,
            valido_ate=valido_ate,
        )
    except Exception as exc:  # noqa: BLE001
        return CertificadoInfo(
            arquivo=pfx_path,
            nome_amigavel=nome_amigavel,
            senha=senha,
            cn="",
            documento="",
            thumbprint_sha1="",
            serial_number="",
            valido_ate="",
            erro=str(exc),
        )


def listar_certificados(
    pasta: str | Path,
    *,
    max_workers: int | None = None,
    use_processes: bool | None = None,
) -> list[CertificadoInfo]:
    """
    Lista todos os .pfx da pasta em ordem alfabetica.

    A decifragem PKCS#12 e CPU-bound e presa pelo GIL; usamos ProcessPool por
    padrao para obter paralelismo real em maquinas multi-core. Para pastas
    pequenas (<=8 arquivos) cai para ThreadPool e evita overhead de spawn.
    """
    pasta_path = Path(pasta)
    if not pasta_path.is_dir():
        raise FileNotFoundError(f"Pasta nao encontrada: {pasta}")

    arquivos = sorted(
        (p for p in pasta_path.iterdir() if p.is_file() and p.suffix.lower() == ".pfx"),
        key=lambda p: p.name.lower(),
    )
    if not arquivos:
        return []

    if len(arquivos) == 1:
        return [ler_certificado(arquivos[0])]

    if use_processes is None:
        use_processes = len(arquivos) > 8

    # No app empacotado (PyInstaller), ProcessPoolExecutor quebra com
    # BrokenProcessPool (os processos-filho nao conseguem inicializar). Usa
    # threads nesse caso — mais lento, mas confiavel. No modo dev mantem processos.
    if getattr(sys, "frozen", False):
        use_processes = False

    cpu = os.cpu_count() or 4
    if max_workers is None:
        max_workers = min(cpu, len(arquivos)) if use_processes else min(32, cpu * 2)

    executor_cls = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    with executor_cls(max_workers=max_workers) as pool:
        # chunksize reduz round-trips de IPC em ProcessPool
        if use_processes:
            chunksize = max(1, len(arquivos) // (max_workers * 4))
            return list(pool.map(ler_certificado, arquivos, chunksize=chunksize))
        return list(pool.map(ler_certificado, arquivos))


def indexar_certificados_por_cnpj(
    certs: list[CertificadoInfo],
) -> tuple[dict[str, CertificadoInfo], dict[str, list[CertificadoInfo]]]:
    """
    Gera indice por CNPJ com controle de duplicidade.

    Retorna:
      - mapa_unico: cnpj -> certificado (apenas quando unico e sem erro)
      - duplicados: cnpj -> [lista de certificados duplicados]
    """
    candidatos: dict[str, list[CertificadoInfo]] = {}
    for cert in certs:
        if cert.erro or not cert.is_cnpj:
            continue
        candidatos.setdefault(cert.cnpj, []).append(cert)

    mapa_unico: dict[str, CertificadoInfo] = {}
    duplicados: dict[str, list[CertificadoInfo]] = {}
    for cnpj, itens in candidatos.items():
        if len(itens) == 1:
            mapa_unico[cnpj] = itens[0]
        else:
            duplicados[cnpj] = itens

    return mapa_unico, duplicados


if __name__ == "__main__":
    import sys

    pasta = (
        sys.argv[1]
        if len(sys.argv) > 1
        else r"G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES"
    )
    certs = listar_certificados(pasta)

    ok = sum(1 for c in certs if not c.erro)
    erro = sum(1 for c in certs if c.erro)
    mapa, duplicados = indexar_certificados_por_cnpj(certs)

    print(f"\nPasta: {pasta}")
    print(f"Total: {len(certs)} | OK: {ok} | Erro: {erro}")
    print(f"CNPJs unicos: {len(mapa)} | CNPJs duplicados: {len(duplicados)}\n")

    print(
        f"{'#':>3}  {'NOME':<45}  {'DOC':<14}  {'VALIDADE':<10}  "
        f"{'THUMBPRINT':<40}  {'SERIAL':<16}  ERRO"
    )
    print("-" * 180)
    for i, c in enumerate(certs, 1):
        print(
            f"{i:>3}  {c.nome_amigavel[:45]:<45}  {c.documento:<14}  "
            f"{c.valido_ate:<10}  {c.thumbprint_sha1[:40]:<40}  "
            f"{c.serial_number[:16]:<16}  {c.erro[:40]}"
        )
