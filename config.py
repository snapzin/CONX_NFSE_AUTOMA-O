# =============================================================================
# config.py - Configuracoes da Automacao NFSe (execucao local)
# =============================================================================

# CAMINHOS LOCAIS
XLSX_PATH = r"clientes.xlsx"
PASTA_CERTS = r"G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES"
PASTA_SAIDA = r"C:\DOMINIO WEB\NFSe"
CHROME_USER_DATA_DIR = r"C:\Users\conxc\AppData\Local\Google\Chrome NFSe Automacao"
# Perfil dedicado para automacao — Chrome bloqueia Playwright em User Data padrao
# (mensagem: "DevTools remote debugging requires a non-default data directory").
# A extensao NFSe e carregada via --load-extension a partir do Profile 1, entao
# funciona igualzinho. O auto-select de certificado funciona via politica HKCU.
CHROME_PROFILE_DIRECTORY = ""
CHROME_EXTENSION_DIR = r"C:\Users\conxc\AppData\Local\Google\Chrome\User Data\Profile 1\Extensions\enehmclajcndmgefbmjhecccoegbdgea\2.8.6.21_0"
# ID da extensão "Baixar NFSe" no Chrome — deixe vazio para auto-detectar
# Para encontrar: chrome://extensions → ative "Modo do desenvolvedor" → copie o ID
CHROME_EXTENSION_ID = "enehmclajcndmgefbmjhecccoegbdgea"

# PORTAL NFSE / PLAYWRIGHT
NFSE_LOGIN_URL = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"
NFSE_EMITIDAS_URL = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
NFSE_RECEBIDAS_URL = "https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas"
AUTOSELECT_CERTIFICATE_PATTERNS = "https://www.nfse.gov.br/*"
CHROME_EXECUTABLE_PATH = ""
CHROME_CHANNEL = "chrome"

PLAYWRIGHT_HEADLESS = False
PLAYWRIGHT_TIMEOUT_MS = 60000
PLAYWRIGHT_SLOW_MO_MS = 0
PLAYWRIGHT_LOGIN_TIMEOUT_S = 45
PLAYWRIGHT_DOWNLOAD_TIMEOUT_S = 180
PLAYWRIGHT_EXTENSION_TIMEOUT_S = 30

# SELETORES DA TELA NFSE (obtenha via DevTools F12 no portal)
# Deixe em branco para usar modo automático "Mês Anterior"
NFSE_SELECTOR_LOGIN_OK = ""
NFSE_SELECTOR_BOTAO_CERTIFICADO = "a:has(img[alt*='Certificado'])"
NFSE_SELECTOR_DATA_INICIO = ""
NFSE_SELECTOR_DATA_FIM = ""
NFSE_SELECTOR_BOTAO_FILTRAR = ""
NFSE_SELECTOR_LINHAS_NOTAS = ""
NFSE_SELECTOR_TEXTO_SEM_NOTAS = "Nenhum registro|Nenhuma nota|Sem resultados"
NFSE_SELECTOR_BOTAO_BAIXAR = ""
# Atalho da extensão Chrome — obtenha em chrome://extensions/shortcuts
NFSE_ATALHO_EXTENSAO = "Control+Shift+Y"  # Ajuste conforme seu atalho

# PLANILHA (XLSX)
XLSX_COLUNA_CNPJ = "CNPJ"
XLSX_COLUNA_NOME = "NOME"

# DOMINIO WEB (importação de XMLs via browser)
DOMINIO_WEB_URL = "https://www.dominioweb.com.br/"
# Módulo a selecionar após login (ex: "Escrita Fiscal")
DOMINIO_WEB_MODULO = "Escrita Fiscal"
# Se True, executa a importação no Domínio Web após baixar as notas
DOMINIO_WEB_IMPORTAR = False
# Credenciais das empresas no Domínio Web: mapeamento CNPJ -> {"usuario": "...", "senha": "..."}
# Deixe vazio para pedir via popup a cada execução
DOMINIO_WEB_CREDENCIAIS: dict = {}
# Exemplo:
# DOMINIO_WEB_CREDENCIAIS = {
#     "12345678000100": {"usuario": "usuario1", "senha": "senha1"},
#     "98765432000100": {"usuario": "usuario2", "senha": "senha2"},
# }

# ZOHO MAIL (SMTP)
ZOHO_SMTP_HOST = "smtppro.zoho.com"
ZOHO_SMTP_PORT = 587
ZOHO_SMTP_USE_TLS = True
ZOHO_SMTP_USER = "contabil@conxcontabilidade.com.br"
ZOHO_SMTP_PASSWORD = "AgX55wEUs2jY"
ZOHO_EMAIL_FROM = "contabil@conxcontabilidade.com.br"
ZOHO_EMAIL_TO = "contabil@conxcontabilidade.com.br"
