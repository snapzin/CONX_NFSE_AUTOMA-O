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
import time
from pathlib import Path

import requests

VALIDATION_URL = "https://license-server-sigma-topaz.vercel.app/api/validate"
LICENSE_FILE   = Path(__file__).parent.parent / "license.key"
GRACE_FILE     = Path(__file__).parent.parent / "license.grace"
TIMEOUT_S      = 8
GRACE_DAYS     = 7

# Hash SHA-256 da chave mestra. A chave real está apenas em keygen_private.py (gitignored).
_MASTER_HASH = "cc1b5ad057cea06bfea3fcae5953436319d162377ce27747645dc0bb05594c2b"

# Segredo compartilhado com o servidor Vercel (env var CLIENT_SECRET).
# Impede que requests não autorizados cheguem ao endpoint de validação.
_CLIENT_SECRET = "nfse-v1-a7f3c9b2d4e6f8a1b3c5d7e9f0a2b4c6"


# ── Chave mestra ──────────────────────────────────────────────────────────────

def _is_master_key(key: str) -> bool:
    normalized = key.upper().replace("-", "").strip()
    candidate  = hashlib.sha256(normalized.encode()).hexdigest()
    return hmac.compare_digest(candidate, _MASTER_HASH)


# ── Grace period (offline) ────────────────────────────────────────────────────

def _save_grace() -> None:
    try:
        GRACE_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _within_grace() -> bool:
    try:
        ts = float(GRACE_FILE.read_text(encoding="utf-8").strip())
        # Rejeita valores não-finitos (inf, -inf, nan) que burlariam o TTL
        if not (0 < ts < time.time() + 86400):
            return False
        return (time.time() - ts) < (GRACE_DAYS * 86400)
    except Exception:
        return False


def _grace_or(offline_msg: str) -> tuple[bool, str]:
    """Retorna True com mensagem de modo offline, ou False com offline_msg."""
    if _within_grace():
        return True, f"Modo offline — licença validada nos últimos {GRACE_DAYS} dias."
    return False, offline_msg


# ── Machine ID ────────────────────────────────────────────────────────────────

def get_machine_id() -> str:
    raw = f"{platform.node()}|{platform.machine()}|{platform.system()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Persistência local ────────────────────────────────────────────────────────

def load_key() -> str | None:
    if not LICENSE_FILE.exists():
        return None
    # utf-8-sig para remover BOM caso o arquivo tenha sido gravado com ele
    key = LICENSE_FILE.read_text(encoding="utf-8-sig").strip()
    return key or None


def save_key(key: str) -> None:
    LICENSE_FILE.write_text(key.strip(), encoding="utf-8")


def deactivate() -> None:
    if LICENSE_FILE.exists():
        LICENSE_FILE.unlink()
    if GRACE_FILE.exists():
        GRACE_FILE.unlink()


# ── Validação ─────────────────────────────────────────────────────────────────

def validate_key(key: str) -> tuple[bool, str]:
    if not key or not isinstance(key, str):
        return False, "Chave não informada."

    normalized = key.upper().replace("-", "").strip()

    if _is_master_key(normalized):
        return True, "Licença CONX ativa."

    try:
        resp  = requests.post(
            VALIDATION_URL,
            json={"key": normalized, "machine_id": get_machine_id()},
            headers={"x-client-secret": _CLIENT_SECRET},
            timeout=TIMEOUT_S,
        )
        data  = resp.json()
        valid = bool(data.get("valid"))
        if valid:
            _save_grace()
        return valid, str(data.get("message", ""))
    except requests.exceptions.ConnectionError:
        return _grace_or("Sem conexão com o servidor de licenças.")
    except requests.exceptions.Timeout:
        return _grace_or("Tempo esgotado ao verificar licença.")
    except Exception as exc:
        return False, f"Erro ao verificar licença: {exc}"


def check_license() -> tuple[bool, str]:
    key = load_key()
    if not key:
        return False, "Nenhuma licença ativada. Insira sua chave na aba Executar."
    return validate_key(key)


def activate(key: str) -> tuple[bool, str]:
    valid, message = validate_key(key)
    if valid:
        save_key(key)
    return valid, message
