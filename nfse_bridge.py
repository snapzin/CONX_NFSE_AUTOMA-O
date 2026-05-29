"""
nfse_bridge.py

Bridge between Electron (JavaScript) and the Python NFSe automation engine.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import config


APP_TITLE = "NFSe Automacao"
APP_VERSION = "2.3"
CONFIG_PATH = Path(__file__).resolve().with_name("config.py")
CONFIG_BACKUP_PATH = CONFIG_PATH.with_suffix(".py.bak")

FIELD_SECTIONS: list[dict[str, Any]] = [
    {
        "title": "Caminhos locais",
        "fields": [
            {"key": "XLSX_PATH", "label": "Planilha de clientes", "type": "path"},
            {"key": "PASTA_CERTS", "label": "Pasta de certificados", "type": "dir"},
            {"key": "PASTA_SAIDA", "label": "Pasta de saida", "type": "dir"},
            {"key": "CHROME_USER_DATA_DIR", "label": "Perfil Chrome", "type": "dir"},
            {"key": "CHROME_EXTENSION_DIR", "label": "Pasta da extensao", "type": "dir"},
        ],
    },
    {
        "title": "Portal NFSe / Playwright",
        "fields": [
            {"key": "NFSE_LOGIN_URL", "label": "URL de login", "type": "text"},
            {"key": "NFSE_EMITIDAS_URL", "label": "URL de notas emitidas", "type": "text"},
            {
                "key": "AUTOSELECT_CERTIFICATE_PATTERNS",
                "label": "AutoSelectCertificateForUrls",
                "type": "text",
            },
            {"key": "CHROME_CHANNEL", "label": "Canal do browser", "type": "text"},
            {"key": "CHROME_EXECUTABLE_PATH", "label": "Executavel Chrome (opcional)", "type": "path"},
            {"key": "PLAYWRIGHT_HEADLESS", "label": "Headless (True/False)", "type": "text"},
            {"key": "PLAYWRIGHT_TIMEOUT_MS", "label": "Timeout padrao (ms)", "type": "int"},
            {"key": "PLAYWRIGHT_LOGIN_TIMEOUT_S", "label": "Timeout login (s)", "type": "int"},
            {"key": "PLAYWRIGHT_DOWNLOAD_TIMEOUT_S", "label": "Timeout download (s)", "type": "int"},
        ],
    },
    {
        "title": "Seletores e extensao",
        "fields": [
            {"key": "NFSE_SELECTOR_LOGIN_OK", "label": "Seletor de login OK", "type": "text"},
            {"key": "NFSE_SELECTOR_BOTAO_CERTIFICADO", "label": "Botao acesso certificado", "type": "text"},
            {"key": "NFSE_SELECTOR_DATA_INICIO", "label": "Campo data inicio", "type": "text"},
            {"key": "NFSE_SELECTOR_DATA_FIM", "label": "Campo data fim", "type": "text"},
            {"key": "NFSE_SELECTOR_BOTAO_FILTRAR", "label": "Botao filtrar", "type": "text"},
            {"key": "NFSE_SELECTOR_LINHAS_NOTAS", "label": "Linhas da tabela de notas", "type": "text"},
            {"key": "NFSE_SELECTOR_TEXTO_SEM_NOTAS", "label": "Textos de sem notas", "type": "text"},
            {"key": "NFSE_SELECTOR_BOTAO_BAIXAR", "label": "Botao da extensao", "type": "text"},
            {"key": "NFSE_ATALHO_EXTENSAO", "label": "Atalho da extensao", "type": "text"},
        ],
    },
    {
        "title": "E-mail (Zoho SMTP)",
        "fields": [
            {"key": "ZOHO_SMTP_HOST", "label": "Host SMTP", "type": "text"},
            {"key": "ZOHO_SMTP_PORT", "label": "Porta SMTP", "type": "int"},
            {"key": "ZOHO_SMTP_USER", "label": "Usuario", "type": "text"},
            {"key": "ZOHO_SMTP_PASSWORD", "label": "Senha", "type": "secret"},
            {"key": "ZOHO_EMAIL_FROM", "label": "Remetente", "type": "text"},
            {"key": "ZOHO_EMAIL_TO", "label": "Destinatario(s)", "type": "text"},
        ],
    },
]

FIELD_ORDER: list[str] = [field["key"] for section in FIELD_SECTIONS for field in section["fields"]]


def _emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


def _reload_config_module():
    return importlib.reload(config)


def _python_string_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if "\\" in value and '"' not in value:
        return f'r"{value}"'
    return f'"{escaped}"'


def _replace_config_assignment(source: str, key: str, literal: str) -> str:
    pattern = re.compile(
        rf"^(?P<prefix>{re.escape(key)}\s*=\s*)(?P<value>.+?)(?P<suffix>\s*(?:#.*)?)$",
        re.MULTILINE,
    )

    def repl(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{literal}{match.group('suffix')}"

    new_text, count = pattern.subn(repl, source, count=1)
    if count == 0:
        new_text = source.rstrip() + f"\n{key} = {literal}\n"
    return new_text


def _normalize_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "sim", "yes", "y", "on"}


def _get_values_from_config() -> dict[str, str]:
    cfg = _reload_config_module()
    return {key: str(getattr(cfg, key, "")) for key in FIELD_ORDER}


def _save_config_values(values: dict[str, Any]) -> None:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("config.py nao encontrado.")

    cfg = _reload_config_module()
    original = CONFIG_PATH.read_text(encoding="utf-8")
    new_text = original

    for key in FIELD_ORDER:
        if key not in values:
            continue

        raw_value = str(values.get(key, ""))
        current = getattr(cfg, key, "")

        if isinstance(current, bool):
            literal = "True" if _normalize_bool(raw_value) else "False"
        elif isinstance(current, int) and not isinstance(current, bool):
            int(raw_value)  # validation
            literal = raw_value.strip()
        else:
            literal = _python_string_literal(raw_value)

        new_text = _replace_config_assignment(new_text, key, literal)

    CONFIG_BACKUP_PATH.write_text(original, encoding="utf-8")
    CONFIG_PATH.write_text(new_text, encoding="utf-8")
    _reload_config_module()


def _command_get_config() -> int:
    values = _get_values_from_config()
    payload = {
        "ok": True,
        "appTitle": APP_TITLE,
        "appVersion": APP_VERSION,
        "configPath": str(CONFIG_PATH),
        "backupPath": str(CONFIG_BACKUP_PATH),
        "sections": FIELD_SECTIONS,
        "values": values,
        "diagnostics": {
            "pythonVersion": sys.version.split()[0],
            "portalUrl": values.get("NFSE_LOGIN_URL", ""),
            "extensionDir": values.get("CHROME_EXTENSION_DIR", ""),
            "outputDir": values.get("PASTA_SAIDA", ""),
            "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    }
    _emit_json(payload)
    return 0


def _command_set_config() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("Payload vazio para salvar configuracoes.")

        values = json.loads(raw)
        if not isinstance(values, dict):
            raise ValueError("Payload invalido: esperado objeto JSON.")

        _save_config_values(values)
        _emit_json(
            {
                "ok": True,
                "message": "Configuracoes salvas com sucesso.",
                "backupPath": str(CONFIG_BACKUP_PATH),
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        _emit_json({"ok": False, "error": str(exc)})
        return 1


def _command_count_certs() -> int:
    try:
        from cert_reader import indexar_certificados_por_cnpj, listar_certificados

        cfg = _reload_config_module()
        certs_dir_raw = str(getattr(cfg, "PASTA_CERTS", "")).strip()
        if not certs_dir_raw:
            raise ValueError("PASTA_CERTS nao configurada.")

        certs_dir = Path(certs_dir_raw)
        if not certs_dir.exists():
            raise FileNotFoundError(f"Pasta nao encontrada: {certs_dir}")
        if not certs_dir.is_dir():
            raise NotADirectoryError(f"Caminho nao e uma pasta: {certs_dir}")

        certs = listar_certificados(certs_dir)
        unique_by_cnpj, duplicates = indexar_certificados_por_cnpj(certs)
        valid = [cert for cert in certs if not cert.erro]
        ecnpj = sum(1 for cert in valid if len(cert.documento) == 14)
        ecpf = sum(1 for cert in valid if len(cert.documento) == 11)
        sem_doc = sum(1 for cert in valid if len(cert.documento) not in (11, 14))
        errors = len(certs) - len(valid)
        duplicated_files = sum(len(items) for items in duplicates.values())

        _emit_json(
            {
                "ok": True,
                "path": str(certs_dir),
                "total": len(certs),
                "valid": len(valid),
                "errors": errors,
                "ecnpj": ecnpj,
                "ecpf": ecpf,
                "semDoc": sem_doc,
                "cnpjsUnicos": len(unique_by_cnpj),
                "cnpjsDuplicados": len(duplicates),
                "arquivosDuplicados": duplicated_files,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        _emit_json({"ok": False, "error": str(exc)})
        return 1


class _JsonRunLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _emit_json(
            {
                "event": "log",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def _configure_run_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.INFO)
    root.addHandler(_JsonRunLogHandler())


def _parse_cnpjs(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = [part for part in re.split(r"[\s,;]+", str(raw)) if part]

    cnpjs: list[str] = []
    seen: set[str] = set()
    for value in values:
        digits = re.sub(r"\D", "", value)
        if len(digits) != 14:
            continue
        if digits not in seen:
            cnpjs.append(digits)
            seen.add(digits)
    return cnpjs or None


def _command_run() -> int:
    from nfse_automacao import ExecucaoCancelada, executar

    _configure_run_logging()
    cancel_event = threading.Event()
    result: dict[str, str] = {"status": "ok", "error": ""}

    try:
        first_line = sys.stdin.readline()
        payload = json.loads(first_line) if first_line.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("Payload de execucao invalido.")
    except Exception as exc:  # noqa: BLE001
        _emit_json({"event": "finished", "status": "erro", "message": f"Payload invalido: {exc}"})
        return 1

    data_inicio = str(payload.get("dataInicio") or "").strip() or None
    data_fim = str(payload.get("dataFim") or "").strip() or None
    cnpjs = _parse_cnpjs(payload.get("cnpjs"))

    def stdin_listener() -> None:
        for line in sys.stdin:
            if line.strip().lower() == "cancel":
                cancel_event.set()
                _emit_json({"event": "state", "state": "canceling", "message": "Cancelamento solicitado."})
                break

    def runner() -> None:
        try:
            executar(
                data_inicio=data_inicio,
                data_fim=data_fim,
                cnpjs=cnpjs,
                cancel_event=cancel_event,
            )
        except ExecucaoCancelada as exc:
            result["status"] = "cancelado"
            result["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            result["status"] = "erro"
            result["error"] = str(exc)

    threading.Thread(target=stdin_listener, daemon=True).start()
    _emit_json({"event": "state", "state": "running", "message": "Execucao iniciada."})

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(timeout=0.25)

    status = result["status"]
    message = {
        "ok": "Execucao finalizada com sucesso.",
        "cancelado": "Execucao cancelada.",
        "erro": "Execucao finalizada com erro.",
    }.get(status, "Execucao finalizada.")

    _emit_json(
        {
            "event": "finished",
            "status": status,
            "message": message,
            "error": result["error"],
        }
    )
    return 1 if status == "erro" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge da GUI JavaScript para NFSe automacao.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("get-config")
    sub.add_parser("set-config")
    sub.add_parser("count-certs")
    sub.add_parser("run")

    args = parser.parse_args()

    if args.command == "get-config":
        return _command_get_config()
    if args.command == "set-config":
        return _command_set_config()
    if args.command == "count-certs":
        return _command_count_certs()
    if args.command == "run":
        return _command_run()

    _emit_json({"ok": False, "error": "Comando invalido."})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
