from __future__ import annotations

import json
import sys
from pathlib import Path

import config


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


RUNTIME_SETTINGS_PATH = _base_dir() / "runtime_settings.json"


def load_runtime_settings() -> dict:
    """Carrega configurações dinâmicas salvas pela interface."""
    if not RUNTIME_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_runtime_settings(settings: dict) -> None:
    """Persiste configurações dinâmicas — faz merge com os valores já salvos."""
    current = load_runtime_settings()
    current.update({k: v for k, v in settings.items() if v is not None})
    RUNTIME_SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_pasta_certs() -> str:
    """Retorna a pasta de certificados atual, priorizando o override salvo."""
    return load_runtime_settings().get("pasta_certs", config.PASTA_CERTS)


def get_email_to() -> str:
    """Retorna o e-mail de destino atual, priorizando o override salvo."""
    return load_runtime_settings().get("email_to", config.EMAIL_TO)
