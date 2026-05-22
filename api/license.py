"""
api/license.py — Validação de licença.

Dois tipos de chave:
  - Mestra (CONX): validada localmente por hash, funciona sempre, sem servidor.
  - Cliente: validada contra o servidor Vercel a cada execução.
"""

from __future__ import annotations

import hashlib
import hmac
import platform
from pathlib import Path

import requests

# URL do servidor Vercel — atualize após o deploy
VALIDATION_URL = "https://nfse-license.vercel.app/api/validate"  # snapzins-projects
LICENSE_FILE = Path(__file__).parent.parent / "license.key"
TIMEOUT_S = 8

# Hash SHA-256 da chave mestra. A chave real está apenas no keygen_private.py (gitignored).
_MASTER_HASH = "cc1b5ad057cea06bfea3fcae5953436319d162377ce27747645dc0bb05594c2b"


def _is_master_key(key: str) -> bool:
    """Compara a chave com o hash da chave mestra usando compare_digest (resistente a timing attack)."""
    normalized = key.upper().replace("-", "").strip()
    candidate_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return hmac.compare_digest(candidate_hash, _MASTER_HASH)


def get_machine_id() -> str:
    """ID estável baseado em node + platform. Não muda com reboot."""
    raw = f"{platform.node()}|{platform.machine()}|{platform.system()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def load_key() -> str | None:
    if LICENSE_FILE.exists():
        key = LICENSE_FILE.read_text(encoding="utf-8").strip()
        return key if key else None
    return None


def save_key(key: str) -> None:
    LICENSE_FILE.write_text(key.strip(), encoding="utf-8")


def validate_key(key: str) -> tuple[bool, str]:
    """
    Valida uma chave. Chave mestra: verificação local.
    Chaves de cliente: verificação no servidor Vercel.
    """
    normalized = key.upper().replace("-", "").strip()

    # Chave mestra — nunca expira, sem servidor
    if _is_master_key(normalized):
        return True, "Licença CONX ativa."

    # Chaves de cliente — verificação online
    try:
        resp = requests.post(
            VALIDATION_URL,
            json={"key": normalized, "machine_id": get_machine_id()},
            timeout=TIMEOUT_S,
        )
        data = resp.json()
        return bool(data.get("valid")), str(data.get("message", ""))
    except requests.exceptions.ConnectionError:
        return False, "Sem conexão com o servidor de licenças."
    except requests.exceptions.Timeout:
        return False, "Tempo esgotado ao verificar licença."
    except Exception as exc:
        return False, f"Erro ao verificar licença: {exc}"


def check_license() -> tuple[bool, str]:
    """Verifica se há uma licença válida salva. Chamado antes de cada execução."""
    key = load_key()
    if not key:
        return False, "Nenhuma licença ativada. Insira sua chave na aba Executar."
    return validate_key(key)


def activate(key: str) -> tuple[bool, str]:
    """Valida e salva uma chave localmente."""
    valid, message = validate_key(key)
    if valid:
        save_key(key)
    return valid, message
