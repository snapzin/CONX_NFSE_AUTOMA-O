# =============================================================================
# config_mac.py - Configuracoes para TESTE no macOS
# Para usar: copie este arquivo para config.py antes de rodar
# (Os usuarios finais usam Windows — este arquivo eh so para testes locais)
# =============================================================================

from pathlib import Path

_HOME = Path.home()

# CAMINHOS LOCAIS (macOS)
XLSX_PATH               = str(_HOME / "Documents" / "NFSe" / "clientes.xlsx")
PASTA_CERTS             = str(_HOME / "Documents" / "NFSe" / "Certificados")
PASTA_SAIDA             = str(_HOME / "Documents" / "NFSe" / "Downloads")
CHROME_USER_DATA_DIR    = str(_HOME / "Library" / "Application Support" / "Google" / "Chrome NFSe Automacao")
CHROME_PROFILE_DIRECTORY = ""
CHROME_EXTENSION_DIR    = str(_HOME / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Extensions" / "enehmclajcndmgefbmjhecccoegbdgea")
CHROME_EXTENSION_ID     = "enehmclajcndmgefbmjhecccoegbdgea"

# PORTAL NFSE / PLAYWRIGHT
NFSE_LOGIN_URL          = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"
NFSE_EMITIDAS_URL       = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
NFSE_RECEBIDAS_URL      = "https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas"
AUTOSELECT_CERTIFICATE_PATTERNS = "https://www.nfse.gov.br/*"
CHROME_EXECUTABLE_PATH  = ""
CHROME_CHANNEL          = "chrome"

PLAYWRIGHT_HEADLESS             = False
PLAYWRIGHT_TIMEOUT_MS           = 60000
PLAYWRIGHT_SLOW_MO_MS           = 0
PLAYWRIGHT_LOGIN_TIMEOUT_S      = 45
PLAYWRIGHT_DOWNLOAD_TIMEOUT_S   = 180
PLAYWRIGHT_EXTENSION_TIMEOUT_S  = 30

# SELETORES
NFSE_SELECTOR_LOGIN_OK          = ""
NFSE_SELECTOR_BOTAO_CERTIFICADO = "a:has(img[alt*='Certificado'])"
NFSE_SELECTOR_DATA_INICIO       = ""
NFSE_SELECTOR_DATA_FIM          = ""
NFSE_SELECTOR_BOTAO_FILTRAR     = ""
NFSE_SELECTOR_LINHAS_NOTAS      = ""
NFSE_SELECTOR_TEXTO_SEM_NOTAS   = "Nenhum registro|Nenhuma nota|Sem resultados"
NFSE_SELECTOR_BOTAO_BAIXAR      = ""
NFSE_ATALHO_EXTENSAO            = "Control+Shift+Y"

# PLANILHA
XLSX_COLUNA_CNPJ = "CNPJ"
XLSX_COLUNA_NOME = "NOME"

# DOMINIO WEB
DOMINIO_WEB_URL       = "https://www.dominioweb.com.br/"
DOMINIO_WEB_MODULO    = "Escrita Fiscal"
DOMINIO_WEB_IMPORTAR  = False
DOMINIO_WEB_CREDENCIAIS: dict = {}

# ZOHO MAIL
ZOHO_SMTP_HOST      = "smtppro.zoho.com"
ZOHO_SMTP_PORT      = 587
ZOHO_SMTP_USE_TLS   = True
ZOHO_SMTP_USER      = "contabil@conxcontabilidade.com.br"
ZOHO_SMTP_PASSWORD  = "AgX55wEUs2jY"
ZOHO_EMAIL_FROM     = "contabil@conxcontabilidade.com.br"
ZOHO_EMAIL_TO       = "contabil@conxcontabilidade.com.br"
