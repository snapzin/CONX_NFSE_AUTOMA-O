"""
scheduler.py — Agendador + Servidor Webhook
============================================
Substitui os dois nós de trigger do n8n:
  • ⏰ Agendamento (dia 5 às 7h)     →  schedule
  • 🔗 Webhook (disparo manual)      →  Flask  POST /nfse-executar

Como usar
---------
  python scheduler.py           # inicia agendador + servidor webhook
  python scheduler.py --run-now  # executa imediatamente e sai
"""

from __future__ import annotations

import argparse
import logging
import threading
from datetime import datetime

import schedule
from flask import Flask, jsonify, request

import config
from nfse_automacao import executar

log = logging.getLogger("nfse.scheduler")

# ---------------------------------------------------------------------------
# Flask — Webhook de disparo manual
# ---------------------------------------------------------------------------
app = Flask(__name__)


def _verificar_token() -> bool:
    """Verifica o Bearer token quando WEBHOOK_TOKEN está configurado."""
    if not config.WEBHOOK_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {config.WEBHOOK_TOKEN}"


@app.post("/nfse-executar")
def webhook_executar():
    """
    POST /nfse-executar
    Body JSON (todos opcionais):
    {
      "data_inicio": "01/01/2025",
      "data_fim":    "31/01/2025",
      "cnpjs":       ["12345678000100"]
    }
    """
    if not _verificar_token():
        return jsonify({"erro": "Não autorizado"}), 401

    body = request.get_json(silent=True) or {}
    data_inicio = body.get("data_inicio")
    data_fim    = body.get("data_fim")
    cnpjs       = body.get("cnpjs")

    # Dispara em thread separada para não bloquear a resposta HTTP
    t = threading.Thread(
        target=executar,
        kwargs={"data_inicio": data_inicio, "data_fim": data_fim, "cnpjs": cnpjs},
        daemon=True,
    )
    t.start()

    return jsonify({"recebido": True, "mensagem": "Automação iniciada"}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "hora": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Schedule — execução no dia 5 às 07:00
# ---------------------------------------------------------------------------
def _job_agendado() -> None:
    """Chamado pelo schedule apenas no dia correto do mês."""
    hoje = datetime.now()
    if hoje.day != config.SCHEDULE_DAY:
        return
    log.info("Agendamento disparado — dia %d às %02d:%02d",
             config.SCHEDULE_DAY, config.SCHEDULE_HOUR, config.SCHEDULE_MIN)
    executar()


def iniciar_scheduler() -> None:
    """Registra a tarefa e entra no loop do schedule (blocking)."""
    horario = f"{config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MIN:02d}"
    schedule.every().day.at(horario).do(_job_agendado)
    log.info("Agendador ativo — executa todo dia %d às %s",
             config.SCHEDULE_DAY, horario)

    import time
    while True:
        schedule.run_pending()
        time.sleep(30)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="NFSe Automação")
    parser.add_argument(
        "--run-now", action="store_true",
        help="Executa a automação imediatamente e encerra",
    )
    parser.add_argument("--data-inicio", default=None, help="dd/mm/aaaa")
    parser.add_argument("--data-fim",    default=None, help="dd/mm/aaaa")
    parser.add_argument(
        "--cnpjs", nargs="*", default=None,
        help="Lista de CNPJs (sem pontuação)",
    )
    args = parser.parse_args()

    if args.run_now:
        executar(
            data_inicio = args.data_inicio,
            data_fim    = args.data_fim,
            cnpjs       = args.cnpjs,
        )
        return

    # -----------------------------------------------------------------------
    # Modo normal: agendador em background + webhook em foreground
    # -----------------------------------------------------------------------
    t_sched = threading.Thread(target=iniciar_scheduler, daemon=True)
    t_sched.start()

    log.info(
        "Webhook disponível em http://%s:%d%s",
        config.WEBHOOK_HOST, config.WEBHOOK_PORT, config.WEBHOOK_PATH,
    )
    app.run(
        host  = config.WEBHOOK_HOST,
        port  = config.WEBHOOK_PORT,
        debug = False,
        use_reloader = False,
    )


if __name__ == "__main__":
    main()
