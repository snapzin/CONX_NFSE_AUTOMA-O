# =============================================================================
# config.py — Configurações da Automação NFSe
# =============================================================================
# ⚠️ EDITE ESTE ARQUIVO antes de executar a automação.
# =============================================================================

# -----------------------------------------------------------------------------
# CAMINHOS LOCAIS
# -----------------------------------------------------------------------------
XLSX_PATH   = r"C:\Automacao\clientes.xlsx"       # Planilha com os clientes
PASTA_CERTS = r"C:\Automacao\Certificados"         # Pasta com os .pfx
PASTA_SAIDA = r"C:\Automacao\NFSe_Downloads"       # Onde salvar os ZIPs

# -----------------------------------------------------------------------------
# API LOCAL (via túnel ngrok / Cloudflare)
# -----------------------------------------------------------------------------
API_URL    = "http://SEU-TUNEL-NGROK.ngrok-free.app"   # URL do seu túnel
API_TOKEN  = "troque-este-token-secreto"               # Bearer token da API

# Intervalo entre verificações de status (segundos)
POLL_INTERVAL = 15

# Timeout máximo aguardando o job finalizar (segundos) — 30 min padrão
POLL_TIMEOUT = 1800

# -----------------------------------------------------------------------------
# TELEGRAM
# -----------------------------------------------------------------------------
TELEGRAM_TOKEN   = "SEU_BOT_TOKEN_AQUI"    # Token do @BotFather
TELEGRAM_CHAT_ID = "SEU_CHAT_ID_AQUI"      # Seu chat ID numérico

# -----------------------------------------------------------------------------
# AGENDAMENTO  (scheduler embutido)
# -----------------------------------------------------------------------------
# Dia do mês e hora de execução automática
SCHEDULE_DAY  = 5       # Dia 5 de cada mês
SCHEDULE_HOUR = 7       # 07:00
SCHEDULE_MIN  = 0

# -----------------------------------------------------------------------------
# WEBHOOK SERVER  (disparo manual)
# -----------------------------------------------------------------------------
WEBHOOK_HOST  = "0.0.0.0"
WEBHOOK_PORT  = 5678
WEBHOOK_PATH  = "/nfse-executar"
# Token de autenticação para o webhook (coloque em branco "" para desativar)
WEBHOOK_TOKEN = "troque-este-token-webhook"
