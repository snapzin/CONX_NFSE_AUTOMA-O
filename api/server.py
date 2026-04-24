"""
FastAPI backend para NFSe Automacao.
Expõe endpoints REST para o frontend Electron.
"""
import asyncio
import logging
import re
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import uvicorn

# Imports do projeto
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from nfse_automacao import ExecucaoCancelada, executar_local, preparar_parametros
from cert_reader import listar_certificados, indexar_certificados_por_cnpj
import config

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Job management
# =============================================================================
@dataclass
class Job:
    id: str
    status: str  # "running", "ok", "cancelado", "erro"
    logs: deque = None
    thread: Optional[threading.Thread] = None
    cancel_event: Optional[threading.Event] = None
    resultado: Optional[dict] = None

    def __post_init__(self):
        if self.logs is None:
            self.logs = deque(maxlen=2000)
        if self.cancel_event is None:
            self.cancel_event = threading.Event()

JOBS = {}

class JobLogHandler(logging.Handler):
    """Handler que adiciona logs a um Job específico."""
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        if self.job_id in JOBS:
            msg = self.format(record)
            JOBS[self.job_id].logs.append({
                "timestamp": record.created,
                "level": record.levelname,
                "message": msg,
            })

# =============================================================================
# FastAPI app
# =============================================================================
app = FastAPI(title="NFSe Automacao API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health")
async def health():
    """Health check — Electron aguarda isso para saber que o backend está pronto."""
    return {"ok": True}

@app.get("/config")
async def get_config():
    """Retorna seções + valores atuais de config.py."""
    sections = [
        {
            "title": "Caminhos locais",
            "fields": [
                ("XLSX_PATH", "Planilha de clientes", "path"),
                ("PASTA_CERTS", "Pasta de certificados", "dir"),
                ("PASTA_SAIDA", "Pasta de saida", "dir"),
                ("CHROME_USER_DATA_DIR", "Perfil Chrome", "dir"),
                ("CHROME_EXTENSION_DIR", "Pasta da extensao", "dir"),
            ],
        },
        {
            "title": "Portal NFSe / Playwright",
            "fields": [
                ("NFSE_LOGIN_URL", "URL de login", "text"),
                ("NFSE_EMITIDAS_URL", "URL de notas emitidas", "text"),
                ("AUTOSELECT_CERTIFICATE_PATTERNS", "AutoSelectCertificateForUrls", "text"),
                ("CHROME_CHANNEL", "Canal do browser", "text"),
                ("CHROME_EXECUTABLE_PATH", "Executavel Chrome (opcional)", "path"),
                ("PLAYWRIGHT_HEADLESS", "Headless (True/False)", "text"),
                ("PLAYWRIGHT_TIMEOUT_MS", "Timeout padrao (ms)", "int"),
                ("PLAYWRIGHT_LOGIN_TIMEOUT_S", "Timeout login (s)", "int"),
                ("PLAYWRIGHT_DOWNLOAD_TIMEOUT_S", "Timeout download (s)", "int"),
            ],
        },
        {
            "title": "Seletores e extensao",
            "fields": [
                ("NFSE_SELECTOR_LOGIN_OK", "Seletor de login OK", "text"),
                ("NFSE_SELECTOR_BOTAO_CERTIFICADO", "Botao acesso certificado", "text"),
                ("NFSE_SELECTOR_DATA_INICIO", "Campo data inicio", "text"),
                ("NFSE_SELECTOR_DATA_FIM", "Campo data fim", "text"),
                ("NFSE_SELECTOR_BOTAO_FILTRAR", "Botao filtrar", "text"),
                ("NFSE_SELECTOR_LINHAS_NOTAS", "Linhas da tabela de notas", "text"),
                ("NFSE_SELECTOR_TEXTO_SEM_NOTAS", "Textos de sem notas", "text"),
                ("NFSE_SELECTOR_BOTAO_BAIXAR", "Botao da extensao", "text"),
                ("NFSE_ATALHO_EXTENSAO", "Atalho da extensao", "text"),
            ],
        },
        {
            "title": "E-mail (Zoho SMTP)",
            "fields": [
                ("ZOHO_SMTP_HOST", "Host SMTP", "text"),
                ("ZOHO_SMTP_PORT", "Porta SMTP", "int"),
                ("ZOHO_SMTP_USER", "Usuario", "text"),
                ("ZOHO_SMTP_PASSWORD", "Senha", "secret"),
                ("ZOHO_EMAIL_FROM", "Remetente", "text"),
                ("ZOHO_EMAIL_TO", "Destinatario(s)", "text"),
            ],
        },
    ]

    values = {}
    for section in sections:
        for key, label, tipo in section["fields"]:
            val = getattr(config, key, "")
            values[key] = str(val)

    return {"sections": sections, "values": values}

@app.post("/config")
async def set_config(body: dict):
    """Salva valores em config.py (com backup .bak)."""
    config_path = Path(__file__).parent.parent / "config.py"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.py não encontrado")

    try:
        original = config_path.read_text(encoding="utf-8")
        novo = original

        for chave, valor in body.items():
            if not hasattr(config, chave):
                continue
            atual = getattr(config, chave)
            if isinstance(atual, bool):
                literal = "True" if str(valor).lower() in ("true", "1", "sim") else "False"
            elif isinstance(atual, int):
                literal = str(int(valor))
            else:
                escaped = str(valor).replace("\\", "\\\\").replace('"', '\\"')
                literal = f'r"{valor}"' if ("\\" in str(valor) and '"' not in str(valor)) else f'"{escaped}"'

            pattern = re.compile(
                rf"^(?P<prefix>{re.escape(chave)}\s*=\s*)(?P<value>.+?)(?P<suffix>\s*(?:#.*)?)$",
                re.MULTILINE,
            )
            novo = pattern.sub(lambda m: f"{m.group('prefix')}{literal}{m.group('suffix')}", novo, count=1)

        backup = config_path.with_suffix(".py.bak")
        backup.write_text(original, encoding="utf-8")
        config_path.write_text(novo, encoding="utf-8")

        import importlib
        importlib.reload(config)

        return {"ok": True, "backupPath": str(backup)}
    except Exception as e:
        logger.exception("Falha ao salvar config")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/certificados")
async def count_certificados(incluir_lista: bool = False):
    """Lista certificados da PASTA_CERTS."""
    try:
        pasta_raw = str(getattr(config, "PASTA_CERTS", "")).strip()
        if not pasta_raw:
            raise ValueError("PASTA_CERTS não configurada")

        pasta = Path(pasta_raw)
        if not pasta.exists():
            raise FileNotFoundError(f"Pasta não encontrada: {pasta}")

        certs = listar_certificados(pasta)
        mapa_unico, duplicados = indexar_certificados_por_cnpj(certs)

        validos = [c for c in certs if not c.erro]
        ok = len(validos)
        erro = len(certs) - ok
        ecnpj = sum(1 for c in validos if len(c.documento) == 14)
        ecpf = sum(1 for c in validos if len(c.documento) == 11)
        sem_doc = sum(1 for c in validos if len(c.documento) not in (11, 14))
        dup_arquivos = sum(len(itens) for itens in duplicados.values())

        resultado = {
            "total": len(certs),
            "validos": ok,
            "erros": erro,
            "ecnpj": ecnpj,
            "ecpf": ecpf,
            "semDoc": sem_doc,
            "cnpjsUnicos": len(mapa_unico),
            "cnpjsDuplicados": len(duplicados),
            "arquivosDuplicados": dup_arquivos,
            "path": str(pasta),
        }

        if incluir_lista:
            resultado["lista"] = [
                {
                    "arquivo": c.arquivo.name,
                    "nomeAmigavel": c.nome_amigavel,
                    "cn": c.cn,
                    "documento": c.documento,
                    "validoAte": c.valido_ate,
                    "erro": c.erro or "",
                }
                for c in certs
            ]

        return resultado
    except Exception as e:
        logger.exception("Falha ao contar certificados")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/executar")
async def start_execution(body: dict):
    """Inicia execução assíncrona. Retorna { jobId }."""
    try:
        data_inicio = body.get("dataInicio")
        data_fim = body.get("dataFim")
        cnpjs = body.get("cnpjs")

        job_id = str(uuid.uuid4())[:8]
        job = Job(id=job_id, status="running")
        JOBS[job_id] = job

        handler = JobLogHandler(job_id)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        def run_job():
            try:
                params = preparar_parametros(data_inicio, data_fim, cnpjs)
                resultado = executar_local(params, cancel_event=job.cancel_event)
                job.status = "ok"
                job.resultado = {
                    "resultados": [asdict(r) for r in resultado],
                    "total": len(resultado),
                    "ok": sum(1 for r in resultado if r.status == "ok"),
                    "erro": sum(1 for r in resultado if r.status == "erro"),
                }
            except ExecucaoCancelada:
                job.status = "cancelado"
            except Exception as e:
                logger.exception("Erro na execução")
                job.status = "erro"
                job.resultado = {"erro": str(e)}
            finally:
                root_logger.removeHandler(handler)

        job.thread = threading.Thread(target=run_job, daemon=True)
        job.thread.start()

        return {"jobId": job_id}
    except Exception as e:
        logger.exception("Falha ao iniciar execução")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/executar/{job_id}/status")
async def get_job_status(job_id: str):
    """Retorna status de um job."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    job = JOBS[job_id]
    logs = list(job.logs)

    resultado = {
        "jobId": job_id,
        "status": job.status,
        "logs": logs,
    }

    if job.resultado:
        resultado["resultado"] = job.resultado

    return resultado

@app.post("/executar/{job_id}/cancelar")
async def cancel_job(job_id: str):
    """Cancela um job em execução."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    job = JOBS[job_id]
    if job.status == "running":
        job.cancel_event.set()
        return {"ok": True, "message": "Cancelamento solicitado"}
    return {"ok": False, "message": "Job não está em execução"}

# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=17432, log_level="info")
