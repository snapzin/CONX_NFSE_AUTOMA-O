# =============================================================================
# config.example.py — Copie para config.py e preencha com seus dados reais.
#   cp config.example.py config.py
# O arquivo config.py está no .gitignore e nunca vai para o repositório.
# =============================================================================

# CAMINHOS LOCAIS
XLSX_PATH = r"clientes.xlsx"
PASTA_CERTS  = r"C:\Caminho\Para\Certificados"          # pasta com os .pfx
PASTA_SAIDA  = r"C:\Caminho\Para\Downloads"             # onde salvar os XMLs
CHROME_USER_DATA_DIR = r"C:\Users\SEU_USUARIO\AppData\Local\Google\Chrome NFSe Automacao"
CHROME_PROFILE_DIRECTORY = ""
CHROME_EXTENSION_DIR = r""                              # deixe vazio para auto-detectar
CHROME_EXTENSION_ID  = ""                               # deixe vazio para auto-detectar

# PORTAL NFSE / PLAYWRIGHT
NFSE_LOGIN_URL      = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"
NFSE_EMITIDAS_URL   = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
NFSE_RECEBIDAS_URL  = "https://www.nfse.gov.br/EmissorNacional/Notas/Recebidas"
AUTOSELECT_CERTIFICATE_PATTERNS = "https://www.nfse.gov.br/*"
CHROME_EXECUTABLE_PATH = ""
CHROME_CHANNEL = "chrome"

PLAYWRIGHT_HEADLESS           = False
PLAYWRIGHT_TIMEOUT_MS         = 60000
PLAYWRIGHT_SLOW_MO_MS         = 0
PLAYWRIGHT_LOGIN_TIMEOUT_S    = 45
PLAYWRIGHT_DOWNLOAD_TIMEOUT_S = 180
PLAYWRIGHT_EXTENSION_TIMEOUT_S = 30

# SELETORES DA TELA NFSE (obtenha via DevTools F12 no portal)
NFSE_SELECTOR_LOGIN_OK            = ""
NFSE_SELECTOR_BOTAO_CERTIFICADO   = "a:has(img[alt*='Certificado'])"
NFSE_SELECTOR_DATA_INICIO         = ""
NFSE_SELECTOR_DATA_FIM            = ""
NFSE_SELECTOR_BOTAO_FILTRAR       = ""
NFSE_SELECTOR_LINHAS_NOTAS        = ""
NFSE_SELECTOR_TEXTO_SEM_NOTAS     = "Nenhum registro|Nenhuma nota|Sem resultados"
NFSE_SELECTOR_BOTAO_BAIXAR        = ""
NFSE_ATALHO_EXTENSAO              = "Control+Shift+Y"

# PLANILHA (XLSX)
XLSX_COLUNA_CNPJ = "CNPJ"
XLSX_COLUNA_NOME = "NOME"

# DOMINIO WEB (opcional)
DOMINIO_WEB_URL       = "https://www.dominioweb.com.br/"
DOMINIO_WEB_MODULO    = "Escrita Fiscal"
DOMINIO_WEB_IMPORTAR  = False
DOMINIO_WEB_CREDENCIAIS: dict = {}
# Exemplo:
# DOMINIO_WEB_CREDENCIAIS = {
#     "12345678000100": {"usuario": "usuario1", "senha": "senha1"},
# }

# ZOHO MAIL / SMTP (opcional — para envio de relatório por e-mail)
ZOHO_SMTP_HOST     = "smtppro.zoho.com"
ZOHO_SMTP_PORT     = 587
ZOHO_SMTP_USE_TLS  = True
ZOHO_SMTP_USER     = "seu_email@seudominio.com.br"
ZOHO_SMTP_PASSWORD = "sua_senha_aqui"
ZOHO_EMAIL_FROM    = "seu_email@seudominio.com.br"
ZOHO_EMAIL_TO      = "destino@seudominio.com.br"
