"""
api/license.py — Validação de licença contra servidor remoto.
"""

from __future__ import annotations

import hashlib
import platform
from pathlib import Path

import requests

# URL do seu servidor Vercel — substitua após o deploy
VALIDATION_URL = "https://nfse-license.vercel.app/api/validate"
LICENSE_FILE = Path(__file__).parent.parent / "license.key"
TIMEOUT_S = 8


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
    Valida uma chave contra o servidor.
    Retorna (válida, mensagem).
    """
    try:
        resp = requests.post(
            VALIDATION_URL,
            json={"key": key, "machine_id": get_machine_id()},
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
    """
    Verifica se existe uma licença válida salva.
    Chamado antes de cada execução.
    """
    key = load_key()
    if not key:
        return False, "Nenhuma licença ativada. Insira sua chave na aba Executar."
    return validate_key(key)


def activate(key: str) -> tuple[bool, str]:
    """
    Tenta ativar uma nova chave. Salva localmente se válida.
    """
    valid, message = validate_key(key)
    if valid:
        save_key(key)
    return valid, message
