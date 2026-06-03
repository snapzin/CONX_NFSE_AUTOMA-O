from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_values() -> dict[str, object]:
    return {
        # Caminhos padrao do projeto. Sao gravados relativos no config.py e
        # resolvidos para caminho absoluto em runtime.
        "XLSX_PATH": "clientes.xlsx",
        "PASTA_CERTS": "Certificados",
        "PASTA_SAIDA": "Downloads",
        "CHROME_USER_DATA_DIR": "chrome-profile",
        "CHROME_PROFILE_DIRECTORY": "",
        "CHROME_EXTENSION_DIR": "",
        # ID da extensao 'Baixar NFSe' na Chrome Web Store (constante).
        # Preenchido por padrao para deteccao confiavel sem varrer service workers.
        "CHROME_EXTENSION_ID": "enehmclajcndmgefbmjhecccoegbdgea",

        # Portal NFSe / Playwright.
        "NFSE_LOGIN_URL": "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional",
        "NFSE_EMITIDAS_URL": "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
        "NFSE_RECEBIDAS_URL": "https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas",
        "AUTOSELECT_CERTIFICATE_PATTERNS": "https://www.nfse.gov.br/*",
        "CHROME_EXECUTABLE_PATH": "",
        "CHROME_CHANNEL": "chrome",
        "PLAYWRIGHT_HEADLESS": False,
        "PLAYWRIGHT_TIMEOUT_MS": 60000,
        "PLAYWRIGHT_SLOW_MO_MS": 0,
        "PLAYWRIGHT_LOGIN_TIMEOUT_S": 45,
        "PLAYWRIGHT_DOWNLOAD_TIMEOUT_S": 180,
        "PLAYWRIGHT_EXTENSION_TIMEOUT_S": 30,
        # Espera (s) para o painel da extensao carregar antes de clicar.
        "NFSE_EXTENSAO_ESPERA_S": 20,
        # Tentativas de login com certificado (recarrega a pagina entre elas).
        "NFSE_LOGIN_MAX_TENTATIVAS": 5,
        # Tentativas de acionar o download de cada tipo antes de pular.
        "NFSE_DOWNLOAD_TENTATIVAS": 2,

        # Seletores com fallback conhecido. Os demais ficam opcionais.
        "NFSE_SELECTOR_LOGIN_OK": "",
        "NFSE_SELECTOR_BOTAO_CERTIFICADO": "a:has(img[alt*='Certificado'])",
        "NFSE_SELECTOR_DATA_INICIO": "",
        "NFSE_SELECTOR_DATA_FIM": "",
        "NFSE_SELECTOR_BOTAO_FILTRAR": "",
        "NFSE_SELECTOR_LINHAS_NOTAS": "",
        "NFSE_SELECTOR_TEXTO_SEM_NOTAS": "Nenhum registro|Nenhuma nota|Sem resultados",
        "NFSE_SELECTOR_BOTAO_BAIXAR": "",
        "NFSE_ATALHO_EXTENSAO": "Control+Shift+Y",

        # Planilha.
        "XLSX_COLUNA_CNPJ": "CNPJ",
        "XLSX_COLUNA_NOME": "NOME",

        # Painel admin de licencas (Modo Desenvolvedor). O TOKEN fica VAZIO por
        # padrao de proposito: so a maquina do admin (CONX) preenche; nos
        # clientes fica vazio -> o painel de maquinas nao aparece e o token nao
        # e distribuido.
        "LICENSE_ADMIN_URL": "https://license-server-sigma-topaz.vercel.app/api/admin",
        "LICENSE_ADMIN_TOKEN": "",

        # Dominio Web e e-mail sao opcionais.
        "DOMINIO_WEB_URL": "https://www.dominioweb.com.br/",
        "DOMINIO_WEB_MODULO": "Escrita Fiscal",
        "DOMINIO_WEB_IMPORTAR": False,
        "DOMINIO_WEB_CREDENCIAIS": {},
        "ZOHO_SMTP_HOST": "",
        "ZOHO_SMTP_PORT": 587,
        "ZOHO_SMTP_USE_TLS": True,
        "ZOHO_SMTP_USER": "",
        "ZOHO_SMTP_PASSWORD": "",
        "ZOHO_EMAIL_FROM": "",
        "ZOHO_EMAIL_TO": "",
    }


PATH_KEYS = {
    "XLSX_PATH",
    "PASTA_CERTS",
    "PASTA_SAIDA",
    "CHROME_USER_DATA_DIR",
    "CHROME_EXTENSION_DIR",
    "CHROME_EXECUTABLE_PATH",
}

DIRECTORY_KEYS = {
    "PASTA_CERTS",
    "PASTA_SAIDA",
    "CHROME_USER_DATA_DIR",
}


def config_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config.py"


def resolve_path(value: object, base_dir: Path | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base_dir or project_root()) / path)


def _literal(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def default_config_text() -> str:
    values = default_values()
    lines = [
        "# Configuracao local da automacao NFSe.",
        "# Caminhos padrao sao relativos a esta pasta do projeto.",
        "",
        "# CAMINHOS LOCAIS",
        f"XLSX_PATH = {_literal(values['XLSX_PATH'])}",
        f"PASTA_CERTS = {_literal(values['PASTA_CERTS'])}",
        f"PASTA_SAIDA = {_literal(values['PASTA_SAIDA'])}",
        f"CHROME_USER_DATA_DIR = {_literal(values['CHROME_USER_DATA_DIR'])}",
        f"CHROME_PROFILE_DIRECTORY = {_literal(values['CHROME_PROFILE_DIRECTORY'])}",
        f"CHROME_EXTENSION_DIR = {_literal(values['CHROME_EXTENSION_DIR'])}",
        f"CHROME_EXTENSION_ID = {_literal(values['CHROME_EXTENSION_ID'])}",
        "",
        "# PORTAL NFSE / PLAYWRIGHT",
        f"NFSE_LOGIN_URL = {_literal(values['NFSE_LOGIN_URL'])}",
        f"NFSE_EMITIDAS_URL = {_literal(values['NFSE_EMITIDAS_URL'])}",
        f"NFSE_RECEBIDAS_URL = {_literal(values['NFSE_RECEBIDAS_URL'])}",
        f"AUTOSELECT_CERTIFICATE_PATTERNS = {_literal(values['AUTOSELECT_CERTIFICATE_PATTERNS'])}",
        f"CHROME_EXECUTABLE_PATH = {_literal(values['CHROME_EXECUTABLE_PATH'])}",
        f"CHROME_CHANNEL = {_literal(values['CHROME_CHANNEL'])}",
        f"PLAYWRIGHT_HEADLESS = {_literal(values['PLAYWRIGHT_HEADLESS'])}",
        f"PLAYWRIGHT_TIMEOUT_MS = {_literal(values['PLAYWRIGHT_TIMEOUT_MS'])}",
        f"PLAYWRIGHT_SLOW_MO_MS = {_literal(values['PLAYWRIGHT_SLOW_MO_MS'])}",
        f"PLAYWRIGHT_LOGIN_TIMEOUT_S = {_literal(values['PLAYWRIGHT_LOGIN_TIMEOUT_S'])}",
        f"PLAYWRIGHT_DOWNLOAD_TIMEOUT_S = {_literal(values['PLAYWRIGHT_DOWNLOAD_TIMEOUT_S'])}",
        f"PLAYWRIGHT_EXTENSION_TIMEOUT_S = {_literal(values['PLAYWRIGHT_EXTENSION_TIMEOUT_S'])}",
        f"NFSE_EXTENSAO_ESPERA_S = {_literal(values['NFSE_EXTENSAO_ESPERA_S'])}",
        f"NFSE_LOGIN_MAX_TENTATIVAS = {_literal(values['NFSE_LOGIN_MAX_TENTATIVAS'])}",
        f"NFSE_DOWNLOAD_TENTATIVAS = {_literal(values['NFSE_DOWNLOAD_TENTATIVAS'])}",
        "",
        "# SELETORES DA TELA NFSE",
        f"NFSE_SELECTOR_LOGIN_OK = {_literal(values['NFSE_SELECTOR_LOGIN_OK'])}",
        f"NFSE_SELECTOR_BOTAO_CERTIFICADO = {_literal(values['NFSE_SELECTOR_BOTAO_CERTIFICADO'])}",
        f"NFSE_SELECTOR_DATA_INICIO = {_literal(values['NFSE_SELECTOR_DATA_INICIO'])}",
        f"NFSE_SELECTOR_DATA_FIM = {_literal(values['NFSE_SELECTOR_DATA_FIM'])}",
        f"NFSE_SELECTOR_BOTAO_FILTRAR = {_literal(values['NFSE_SELECTOR_BOTAO_FILTRAR'])}",
        f"NFSE_SELECTOR_LINHAS_NOTAS = {_literal(values['NFSE_SELECTOR_LINHAS_NOTAS'])}",
        f"NFSE_SELECTOR_TEXTO_SEM_NOTAS = {_literal(values['NFSE_SELECTOR_TEXTO_SEM_NOTAS'])}",
        f"NFSE_SELECTOR_BOTAO_BAIXAR = {_literal(values['NFSE_SELECTOR_BOTAO_BAIXAR'])}",
        f"NFSE_ATALHO_EXTENSAO = {_literal(values['NFSE_ATALHO_EXTENSAO'])}",
        "",
        "# PLANILHA",
        f"XLSX_COLUNA_CNPJ = {_literal(values['XLSX_COLUNA_CNPJ'])}",
        f"XLSX_COLUNA_NOME = {_literal(values['XLSX_COLUNA_NOME'])}",
        "",
        "# DOMINIO WEB (opcional)",
        f"DOMINIO_WEB_URL = {_literal(values['DOMINIO_WEB_URL'])}",
        f"DOMINIO_WEB_MODULO = {_literal(values['DOMINIO_WEB_MODULO'])}",
        f"DOMINIO_WEB_IMPORTAR = {_literal(values['DOMINIO_WEB_IMPORTAR'])}",
        f"DOMINIO_WEB_CREDENCIAIS = {_literal(values['DOMINIO_WEB_CREDENCIAIS'])}",
        "",
        "# ZOHO MAIL / SMTP (opcional)",
        f"ZOHO_SMTP_HOST = {_literal(values['ZOHO_SMTP_HOST'])}",
        f"ZOHO_SMTP_PORT = {_literal(values['ZOHO_SMTP_PORT'])}",
        f"ZOHO_SMTP_USE_TLS = {_literal(values['ZOHO_SMTP_USE_TLS'])}",
        f"ZOHO_SMTP_USER = {_literal(values['ZOHO_SMTP_USER'])}",
        f"ZOHO_SMTP_PASSWORD = {_literal(values['ZOHO_SMTP_PASSWORD'])}",
        f"ZOHO_EMAIL_FROM = {_literal(values['ZOHO_EMAIL_FROM'])}",
        f"ZOHO_EMAIL_TO = {_literal(values['ZOHO_EMAIL_TO'])}",
        "",
    ]
    return "\n".join(lines)


def ensure_config_file(root: Path | None = None) -> Path:
    path = config_path(root)
    if not path.exists():
        path.write_text(default_config_text(), encoding="utf-8")
    return path


def apply_defaults(
    config_module: object,
    create_dirs: bool = True,
    auto_discover: bool = True,
) -> None:
    values = default_values()
    base_dir = Path(getattr(config_module, "__file__", config_path())).resolve().parent

    for key, default in values.items():
        current = getattr(config_module, key, None)
        if current is None or (isinstance(current, str) and not current.strip()):
            setattr(config_module, key, default)

    # Auto-descoberta de pastas (certificados no Google Drive, DOMINIO WEB local).
    # Roda ANTES de resolver PATH_KEYS para preservar o caminho absoluto achado.
    if auto_discover:
        try:
            import path_finder

            # Startup nunca abre dialogo: detecta automaticamente ou deixa em
            # branco (o frontend pergunta na 1a execucao). Evita travar o boot
            # do backend enquanto o Electron faz polling de /health.
            path_finder.auto_discover_into(config_module, interactive=False)
        except Exception:
            pass

    for key in PATH_KEYS:
        current = getattr(config_module, key, "")
        if current:
            setattr(config_module, key, resolve_path(current, base_dir))

    if create_dirs:
        for key in DIRECTORY_KEYS:
            raw = getattr(config_module, key, "")
            if not raw:
                continue
            try:
                Path(raw).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
