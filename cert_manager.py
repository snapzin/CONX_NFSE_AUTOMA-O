"""
cert_manager.py - Gerencia certificados .pfx no Windows Certificate Store.
"""

from __future__ import annotations

import binascii
import logging
import re
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12

log = logging.getLogger("nfse")

PULAR = {"BRUNO CASCAES DANDOLINI"}


def parse_cert_filename(filename: str) -> tuple[str, str]:
    """Extrai (nome_cliente, senha) do nome do arquivo .pfx."""
    # Senha está após "senha" ou "sanha" (typo comum)
    match = re.search(r'(?:senha|sanha)\s+(\S+)', filename, re.IGNORECASE)
    senha = match.group(1) if match else "123456"

    # Nome: remove ano (4 dígitos) e tudo que vem depois, incluindo "senha..."
    nome = re.sub(r'\s+\d{4}\s+.*', '', filename, flags=re.IGNORECASE)
    nome = re.sub(r'\s+(?:senha|sanha).*', '', nome, flags=re.IGNORECASE)
    nome = nome.replace('_', ' ').strip()

    return nome, senha


def listar_certificados(pasta_certs: str) -> list[dict]:
    """
    Lê todos os .pfx da pasta, extrai nome e senha,
    ordena alfabeticamente e pula clientes da lista PULAR.
    """
    pasta = Path(pasta_certs)
    certs = []

    if not pasta.exists():
        log.error("Pasta não encontrada: %s", pasta)
        return []

    todos = list(pasta.iterdir())
    log.info("Pasta '%s' contém %d itens no total.", pasta, len(todos))

    arquivos = sorted([
        f for f in todos
        if f.is_file() and f.suffix.lower() in (".pfx", ".p12")
    ], key=lambda f: f.name.upper())

    if not arquivos:
        extensoes = {f.suffix.lower() for f in todos if f.is_file()}
        log.warning("Nenhum .pfx/.p12 encontrado. Extensões na pasta: %s", extensoes or "nenhuma")
    else:
        log.info("%d certificado(s) encontrado(s).", len(arquivos))

    for pfx in arquivos:
        nome, senha = parse_cert_filename(pfx.stem)

        if any(p in nome.upper() for p in PULAR):
            log.info("Pulando: %s", nome)
            continue

        certs.append({
            "arquivo": pfx,
            "nome": nome,
            "senha": senha,
        })

    # Ordena pelo nome do cliente
    certs.sort(key=lambda c: c["nome"].upper())
    log.info("%d certificados encontrados na pasta.", len(certs))
    return certs


def obter_thumbprint(pfx_path: Path, senha: str) -> str:
    """Retorna o thumbprint SHA1 do certificado."""
    dados = pfx_path.read_bytes()
    _, cert, _ = pkcs12.load_key_and_certificates(dados, senha.encode())
    return binascii.hexlify(cert.fingerprint(hashes.SHA1())).decode().upper()


def instalar_cert(pfx_path: Path, senha: str) -> str:
    """Instala o .pfx no Windows Certificate Store do usuário. Retorna o thumbprint."""
    subprocess.run(
        ["certutil", "-user", "-p", senha, "-importpfx", str(pfx_path)],
        capture_output=True,
        check=True,
    )
    thumbprint = obter_thumbprint(pfx_path, senha)
    log.info("Certificado instalado: %s (%s)", pfx_path.stem, thumbprint[:16] + "...")
    return thumbprint


def remover_cert(thumbprint: str) -> None:
    """Remove o certificado do Windows Certificate Store pelo thumbprint."""
    subprocess.run(
        ["certutil", "-user", "-delstore", "MY", thumbprint],
        capture_output=True,
    )
    log.info("Certificado removido: %s...", thumbprint[:16])
