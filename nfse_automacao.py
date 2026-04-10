"""
nfse_automacao.py — Motor principal da Automação NFSe
=====================================================
Equivalente Python do fluxo n8n "NFSe — Automação Emissor Nacional".

Fluxo:
  1. Preparar parâmetros  (datas do mês anterior ou customizadas)
  2. Chamar API local      POST /executar  →  job_id
  3. Fazer polling         GET  /status/<job_id>  a cada POLL_INTERVAL s
  4. Montar mensagem       resumo de ok / erro por CNPJ
  5. Notificar Telegram    relatório final ou alerta de falha crítica
"""

from __future__ import annotations

import logging
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import requests

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nfse")


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------
@dataclass
class Parametros:
    xlsx_path: str
    pasta_certs: str
    pasta_saida: str
    data_inicio: str          # dd/mm/aaaa
    data_fim: str             # dd/mm/aaaa
    cnpjs: Optional[list[str]] = field(default=None)


@dataclass
class ResultadoCNPJ:
    cnpj: str
    nome: str
    status: str               # "ok" | "erro"
    erro: str = ""


# ---------------------------------------------------------------------------
# 1. Preparar parâmetros
# ---------------------------------------------------------------------------
def preparar_parametros(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpjs: list[str] | None = None,
) -> Parametros:
    """
    Monta o objeto de parâmetros.
    Se as datas não forem informadas, usa o mês anterior completo.
    """
    if not data_inicio or not data_fim:
        hoje = date.today()
        if hoje.month == 1:
            ano_ant, mes_ant = hoje.year - 1, 12
        else:
            ano_ant, mes_ant = hoje.year, hoje.month - 1

        ultimo_dia = monthrange(ano_ant, mes_ant)[1]
        data_inicio = date(ano_ant, mes_ant, 1).strftime("%d/%m/%Y")
        data_fim    = date(ano_ant, mes_ant, ultimo_dia).strftime("%d/%m/%Y")

    params = Parametros(
        xlsx_path   = config.XLSX_PATH,
        pasta_certs = config.PASTA_CERTS,
        pasta_saida = config.PASTA_SAIDA,
        data_inicio = data_inicio,
        data_fim    = data_fim,
        cnpjs       = cnpjs,
    )
    log.info("Parâmetros: %s → %s | CNPJs: %s",
             params.data_inicio, params.data_fim,
             params.cnpjs or "todos")
    return params


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------
def _headers() -> dict:
    return {"Authorization": f"Bearer {config.API_TOKEN}"}


# ---------------------------------------------------------------------------
# 2. Chamar API Local  POST /executar
# ---------------------------------------------------------------------------
def chamar_api_local(params: Parametros) -> str:
    """
    Envia os parâmetros para a API local e devolve o job_id.
    Levanta RuntimeError em caso de falha.
    """
    url  = f"{config.API_URL.rstrip('/')}/executar"
    body = {
        "xlsx_path":   params.xlsx_path,
        "pasta_certs": params.pasta_certs,
        "pasta_saida": params.pasta_saida,
        "data_inicio": params.data_inicio,
        "data_fim":    params.data_fim,
    }
    if params.cnpjs:
        body["cnpjs"] = params.cnpjs

    log.info("POST %s", url)
    resp = requests.post(url, json=body, headers=_headers(), timeout=30)
    resp.raise_for_status()

    job_id = resp.json().get("job_id")
    if not job_id:
        raise RuntimeError(f"API não retornou job_id: {resp.text}")

    log.info("Job iniciado: %s", job_id)
    return job_id


# ---------------------------------------------------------------------------
# 3. Polling de status
# ---------------------------------------------------------------------------
def verificar_status(job_id: str) -> dict:
    """Consulta GET /status/<job_id> e devolve o JSON da resposta."""
    url = f"{config.API_URL.rstrip('/')}/status/{job_id}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def aguardar_conclusao(job_id: str) -> dict:
    """
    Fica em loop consultando o status até o job chegar em
    'concluido' ou 'erro', com timeout de config.POLL_TIMEOUT segundos.
    """
    inicio = time.monotonic()
    while True:
        dados = verificar_status(job_id)
        status = dados.get("status", "")
        log.info("Status do job %s: %s", job_id, status)

        if status in ("concluido", "erro"):
            return dados

        if time.monotonic() - inicio > config.POLL_TIMEOUT:
            raise TimeoutError(
                f"Job {job_id} não finalizou em {config.POLL_TIMEOUT}s"
            )

        log.info("Aguardando %ds…", config.POLL_INTERVAL)
        time.sleep(config.POLL_INTERVAL)


# ---------------------------------------------------------------------------
# 4. Montar mensagem de relatório
# ---------------------------------------------------------------------------
def montar_mensagem(dados: dict, params: Parametros) -> dict:
    """Formata o resumo final para envio ao Telegram."""
    resumo: list[dict] = dados.get("resumo", [])
    resultados = [
        ResultadoCNPJ(
            cnpj   = r.get("cnpj", ""),
            nome   = r.get("nome", ""),
            status = r.get("status", ""),
            erro   = r.get("erro", ""),
        )
        for r in resumo
    ]

    ok    = sum(1 for r in resultados if r.status == "ok")
    erro  = sum(1 for r in resultados if r.status == "erro")
    total = len(resultados)

    linhas = []
    for r in resultados:
        if r.status == "ok":
            linhas.append(f"✅ {r.cnpj} — {r.nome}")
        else:
            linhas.append(f"❌ {r.cnpj} — {r.nome}\n   Erro: {r.erro}")

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    mensagem = "\n".join([
        "📊 *NFSe Automação — Relatório*",
        f"🗓 {agora}",
        f"📅 Período: {params.data_inicio} → {params.data_fim}",
        "",
        f"Total: {total} | ✅ {ok} | ❌ {erro}",
        "",
        *linhas,
    ])

    return {
        "mensagem":   mensagem,
        "total":      total,
        "ok":         ok,
        "erro":       erro,
        "houve_erro": erro > 0,
    }


def montar_mensagem_erro(erro: str) -> dict:
    """Formata mensagem de falha crítica."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    return {
        "mensagem": (
            f"🚨 *NFSe Automação — FALHA CRÍTICA*\n\n"
            f"Erro: {erro}\n"
            f"Horário: {agora}"
        )
    }


# ---------------------------------------------------------------------------
# 5. Notificar Telegram
# ---------------------------------------------------------------------------
def notificar_telegram(mensagem: str) -> None:
    """Envia uma mensagem de texto via Telegram Bot API."""
    url  = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    body = {
        "chat_id":    config.TELEGRAM_CHAT_ID,
        "text":       mensagem,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=body, timeout=15)
        resp.raise_for_status()
        log.info("Telegram notificado com sucesso.")
    except Exception as exc:  # noqa: BLE001
        log.error("Falha ao notificar Telegram: %s", exc)


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------
def executar(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpjs: list[str] | None = None,
) -> None:
    """
    Executa o fluxo completo:
      preparar → chamar API → polling → mensagem → Telegram.
    """
    log.info("=" * 60)
    log.info("Iniciando automação NFSe")

    try:
        # 1. Parâmetros
        params = preparar_parametros(data_inicio, data_fim, cnpjs)

        # 2. Chamar API local
        job_id = chamar_api_local(params)

        # 3. Polling
        dados = aguardar_conclusao(job_id)

        # 4. Mensagem
        resultado = montar_mensagem(dados, params)
        log.info("Resultado: %d ok / %d erro / %d total",
                 resultado["ok"], resultado["erro"], resultado["total"])

        # 5. Telegram
        notificar_telegram(resultado["mensagem"])

    except Exception as exc:  # noqa: BLE001
        log.error("Falha crítica: %s", exc, exc_info=True)
        msg = montar_mensagem_erro(str(exc))
        notificar_telegram(msg["mensagem"])

    log.info("Automação NFSe finalizada")
    log.info("=" * 60)
