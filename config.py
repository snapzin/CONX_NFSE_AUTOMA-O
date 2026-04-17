# =============================================================================
# config.py - Configuracoes da Automacao NFSe (execucao local)
# =============================================================================

# CAMINHOS LOCAIS
XLSX_PATH = r"G:\Meu Drive\Automações\NFSE\clientes.xlsx"
PASTA_CERTS = r"G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES"
PASTA_SAIDA = r"G:\Meu Drive\Automações\NFSE\Downloads"
CHROME_USER_DATA_DIR = r"G:\Meu Drive\Automações\NFSE\chrome-profile"
CHROME_EXTENSION_DIR = ""

# PORTAL NFSE / PLAYWRIGHT
NFSE_LOGIN_URL = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"
NFSE_EMITIDAS_URL = "https://www.nfse.gov.br/EmissorNacional"
AUTOSELECT_CERTIFICATE_PATTERNS = "https://www.nfse.gov.br/*"
CHROME_EXECUTABLE_PATH = ""
CHROME_CHANNEL = "chromium"

PLAYWRIGHT_HEADLESS = False
PLAYWRIGHT_TIMEOUT_MS = 60000
PLAYWRIGHT_SLOW_MO_MS = 0
PLAYWRIGHT_LOGIN_TIMEOUT_S = 45
PLAYWRIGHT_DOWNLOAD_TIMEOUT_S = 180
PLAYWRIGHT_EXTENSION_TIMEOUT_S = 30

# SELETORES DA TELA NFSE (obtenha via DevTools F12 no portal)
NFSE_SELECTOR_LOGIN_OK = ""
NFSE_SELECTOR_BOTAO_CERTIFICADO = "a:has(img[alt*='Certificado'])"
NFSE_SELECTOR_DATA_INICIO = ""
NFSE_SELECTOR_DATA_FIM = ""
NFSE_SELECTOR_BOTAO_FILTRAR = ""
NFSE_SELECTOR_LINHAS_NOTAS = ""
NFSE_SELECTOR_TEXTO_SEM_NOTAS = "Nenhum registro|Nenhuma nota|Sem resultados"
NFSE_SELECTOR_BOTAO_BAIXAR = ""
NFSE_ATALHO_EXTENSAO = ""

# PLANILHA (XLSX)
XLSX_COLUNA_CNPJ = "CNPJ"
XLSX_COLUNA_NOME = "NOME"

# ZOHO MAIL (SMTP)
ZOHO_SMTP_HOST = "smtppro.zoho.com"
ZOHO_SMTP_PORT = 587
ZOHO_SMTP_USE_TLS = True
ZOHO_SMTP_USER = "contabil@conxcontabilidade.com.br"
ZOHO_SMTP_PASSWORD = "AgX55wEUs2jY"
ZOHO_EMAIL_FROM = "contabil@conxcontabilidade.com.br"
ZOHO_EMAIL_TO = "contabil@conxcontabilidade.com.br"
