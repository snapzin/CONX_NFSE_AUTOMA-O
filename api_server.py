"""
api_server.py - Servidor Flask da Automação NFSe

Expõe dois endpoints:
  POST /executar       -> recebe parâmetros, inicia job em background, retorna job_id
  GET  /status/<id>   -> retorna status do job
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request

import config

log = logging.getLogger("nfse")  # usa o mesmo logger da GUI

app = Flask(__name__)

# Armazenamento em memória dos jobs
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _verificar_token() -> bool:
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {config.API_TOKEN}"


def _processar_job(job_id: str, params: dict) -> None:
    """Executa o processamento do job em background."""
    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "processando"

        log.info("[%s] Iniciando processamento NFSe", job_id)

        from cert_manager import instalar_cert, listar_certificados, remover_cert
        from nfse_browser import processar_cliente

        pasta_certs  = params["pasta_certs"]
        log.info("[%s] Pasta de certificados: %s", job_id, pasta_certs)

        _pasta = Path(pasta_certs)
        if not _pasta.exists():
            log.error("[%s] PASTA NAO ENCONTRADA: %s", job_id, _pasta)
        else:
            _itens = list(_pasta.iterdir())
            log.info("[%s] Pasta existe. Itens: %d", job_id, len(_itens))
            _exts = {f.suffix.lower() for f in _itens if f.is_file()}
            log.info("[%s] Extensoes encontradas: %s", job_id, _exts or "nenhuma")
        pasta_saida  = params["pasta_saida"]
        data_inicio  = params["data_inicio"]
        data_fim     = params["data_fim"]
        cnpjs_filtro = params.get("cnpjs")

        certificados = listar_certificados(pasta_certs)

        # Filtra por CNPJs se informado (usa parte do nome)
        if cnpjs_filtro:
            certificados = [c for c in certificados if any(
                cnpj.lower() in c["nome"].lower() for cnpj in cnpjs_filtro
            )]

        resumo = []
        for cert in certificados:
            nome    = cert["nome"]
            arquivo = cert["arquivo"]
            senha   = cert["senha"]

            log.info("[%s] Processando: %s", job_id, nome)
            thumbprint = None
            try:
                thumbprint = instalar_cert(arquivo, senha)
                pasta_cliente = str(Path(pasta_saida) / nome)

                resultado = processar_cliente(
                    nome=nome,
                    pasta_download_cliente=pasta_cliente,
                    data_inicio=data_inicio,
                    data_fim=data_fim,
                )
                resumo.append({
                    "cnpj": "",
                    "nome": nome,
                    "status": resultado["status"],
                    "erro": resultado.get("erro", ""),
                    "arquivos": resultado.get("arquivos", []),
                })
            except Exception as exc:
                log.error("[%s] Erro em %s: %s", job_id, nome, exc)
                resumo.append({
                    "cnpj": "", "nome": nome,
                    "status": "erro", "erro": str(exc), "arquivos": [],
                })
            finally:
                if thumbprint:
                    try:
                        remover_cert(thumbprint)
                    except Exception:
                        pass

        with _jobs_lock:
            _jobs[job_id].update({
                "status": "concluido",
                "fim": datetime.now().isoformat(),
                "resumo": resumo,
            })

        log.info("[%s] Concluído.", job_id)

    except Exception as exc:  # noqa: BLE001
        log.error("[%s] Erro: %s", job_id, exc, exc_info=True)
        with _jobs_lock:
            _jobs[job_id].update({
                "status": "erro",
                "fim": datetime.now().isoformat(),
                "erro": str(exc),
                "resumo": [],
            })


@app.route("/executar", methods=["POST"])
def executar():
    if not _verificar_token():
        return jsonify({"erro": "Token inválido"}), 401

    dados = request.get_json(silent=True)
    if not dados:
        return jsonify({"erro": "JSON inválido"}), 400

    campos_obrigatorios = ["xlsx_path", "pasta_certs", "pasta_saida", "data_inicio", "data_fim"]
    for campo in campos_obrigatorios:
        if campo not in dados:
            return jsonify({"erro": f"Campo obrigatório ausente: {campo}"}), 400

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "aguardando",
            "inicio": datetime.now().isoformat(),
            "fim": None,
            "params": dados,
            "resumo": [],
        }

    thread = threading.Thread(target=_processar_job, args=(job_id, dados), daemon=True)
    thread.start()

    log.info("Job criado: %s", job_id)
    return jsonify({"job_id": job_id}), 202


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id: str):
    if not _verificar_token():
        return jsonify({"erro": "Token inválido"}), 401

    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"erro": "Job não encontrado"}), 404

    return jsonify(job), 200


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    log.info("Iniciando servidor na porta 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)
