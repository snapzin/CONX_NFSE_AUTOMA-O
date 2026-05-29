"""
FastAPI backend para NFSe Automacao.
Expõe endpoints REST para o frontend Electron.
"""
import hmac
import importlib
import logging
import os
import re
import sys
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# =============================================================================
# Logging — PRIMEIRO, antes de qualquer import que possa usar logger
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suporte a bundle PyInstaller: config.py e módulos ficam ao lado do server.exe
if getattr(sys, "frozen", False):
    _app_dir = str(Path(sys.executable).parent)
    if _app_dir not in sys.path:
        sys.path.insert(0, _app_dir)
else:
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config_defaults import apply_defaults, default_values, ensure_config_file
except ImportError as e:
    logger.warning(f"Falha ao importar config_defaults: {e}")
    apply_defaults = None
    default_values = lambda: {}
    ensure_config_file = lambda: Path(__file__).parent.parent / "config.py"

try:
    ensure_config_file()
except Exception as e:
    logger.warning("Falha ao criar config.py padrao: %s", e)

try:
    import config
    if apply_defaults:
        apply_defaults(config)
except ImportError:
    logger.warning("Falha ao importar config")
    class config:
        pass
    if apply_defaults:
        apply_defaults(config, create_dirs=False)

try:
    from cert_reader import listar_certificados, indexar_certificados_por_cnpj
except ImportError as e:
    logger.warning(f"Falha ao importar cert_reader: {e}. Usando fallback.")
    def listar_certificados(*args, **kwargs):
        return []
    def indexar_certificados_por_cnpj(*args, **kwargs):
        return {}, {}

try:
    from nfse_automacao import ExecucaoCancelada, executar_local, preparar_parametros
except ImportError as e:
    logger.warning(f"Falha ao importar nfse_automacao: {e}. Usando fallback.")
    ExecucaoCancelada = RuntimeError
    def executar_local(*args, **kwargs):
        return []
    def preparar_parametros(*args, **kwargs):
        return {}

import importlib.util as _ilu
import time as _time

def _load_license_module():
    # license.py fica sempre ao lado de server.py (dentro de api/)
    _p = Path(__file__).parent / "license.py"
    if not _p.exists():
        return None
    _spec = _ilu.spec_from_file_location("license", _p)
    _mod  = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod

_lic = _load_license_module()
if _lic:
    license_activate   = _lic.activate
    check_license      = _lic.check_license
    load_key           = _lic.load_key
    license_deactivate = _lic.deactivate
    logger.info("Módulo de licença carregado.")
else:
    logger.error("LICENÇA: módulo não encontrado — execução BLOQUEADA.")
    def license_activate(key): return False, "Módulo de licença não encontrado."
    def check_license(): return False, "Módulo de licença não encontrado."
    def load_key(): return None
    def license_deactivate(): pass

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
    created_at: float = 0.0

    def __post_init__(self):
        if self.logs is None:
            self.logs = deque(maxlen=2000)
        if self.cancel_event is None:
            self.cancel_event = threading.Event()
        if self.created_at == 0.0:
            self.created_at = _time.time()

JOBS = {}
_MAX_JOBS = 50
_JOB_TTL_S = 7200  # 2 horas


def _prune_jobs() -> None:
    """Remove jobs finalizados mais antigos quando o limite é atingido."""
    if len(JOBS) <= _MAX_JOBS:
        return
    cutoff = _time.time() - _JOB_TTL_S
    to_remove = [
        jid for jid, j in JOBS.items()
        if j.status != "running" and j.created_at < cutoff
    ]
    for jid in to_remove:
        del JOBS[jid]
    # Se ainda acima do limite, remove os mais antigos independente do TTL
    if len(JOBS) > _MAX_JOBS:
        finished = sorted(
            [(jid, j) for jid, j in JOBS.items() if j.status != "running"],
            key=lambda x: x[1].created_at,
        )
        for jid, _ in finished[:len(JOBS) - _MAX_JOBS]:
            del JOBS[jid]

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
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "app://"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "x-api-token"],
)

# Token gerado pelo Electron e passado via env var NFSE_API_TOKEN.
# Se não definido (modo dev sem Electron), a auth é desativada.
_API_TOKEN = os.environ.get("NFSE_API_TOKEN", "")

@app.middleware("http")
async def _require_token(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    if _API_TOKEN:
        token = request.headers.get("x-api-token", "")
        if not token or not hmac.compare_digest(token.encode(), _API_TOKEN.encode()):
            return JSONResponse(status_code=401, content={"error": "Não autorizado"})
    return await call_next(request)

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
                ("CHROME_EXTENSION_DIR", "Pasta da extensao (opcional)", "dir"),
                ("CHROME_EXTENSION_ID", "ID da extensao NFSe (auto-detectado se vazio)", "text"),
            ],
        },
        {
            "title": "Portal NFSe / Playwright",
            "fields": [
                ("NFSE_LOGIN_URL", "URL de login", "text"),
                ("NFSE_EMITIDAS_URL", "URL de notas emitidas", "text"),
                ("NFSE_RECEBIDAS_URL", "URL de notas recebidas", "text"),
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
            values[key] = "••••••••" if tipo == "secret" else str(val)

    return {"sections": sections, "values": values}

@app.post("/config")
async def set_config(body: dict):
    """Salva valores em config.py (com backup .bak)."""
    config_path = (
        Path(sys.executable).parent if getattr(sys, "frozen", False)
        else Path(__file__).parent.parent
    ) / "config.py"
    if not config_path.exists():
        try:
            config_path = ensure_config_file(config_path.parent)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Falha ao criar config.py: {e}")
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="config.py não encontrado")

    try:
        original = config_path.read_text(encoding="utf-8")
        novo = original
        defaults = default_values()

        for chave, valor in body.items():
            if not hasattr(config, chave):
                continue
            if str(valor).strip() == "" and defaults.get(chave) not in ("", None):
                valor = defaults[chave]
            atual = getattr(config, chave)
            if isinstance(atual, bool):
                literal = "True" if str(valor).lower() in ("true", "1", "sim") else "False"
            elif isinstance(atual, int):
                literal = str(int(valor))
            else:
                escaped = (str(valor)
                          .replace("\\", "\\\\")
                          .replace('"', '\\"')
                          .replace("\n", "\\n")
                          .replace("\r", "\\r"))
                literal = f'r"{valor}"' if ("\\" in str(valor) and '"' not in str(valor) and "\n" not in str(valor) and "\r" not in str(valor)) else f'"{escaped}"'

            pattern = re.compile(
                rf"^(?P<prefix>{re.escape(chave)}\s*=\s*)(?P<value>.+?)(?P<suffix>\s*(?:#.*)?)$",
                re.MULTILINE,
            )
            novo, count = pattern.subn(
                lambda m: f"{m.group('prefix')}{literal}{m.group('suffix')}",
                novo,
                count=1,
            )
            if count == 0:
                novo = f"{novo.rstrip()}\n{chave} = {literal}\n"

        backup = config_path.with_name(f"config.py.bak.{int(_time.time())}")
        backup.write_text(original, encoding="utf-8")

        # Remove backups mais antigos (mantém últimos 5)
        old_backups = sorted(config_path.parent.glob("config.py.bak.*"),
                             key=lambda p: p.stat().st_mtime)
        for old in old_backups[:-5]:
            try:
                old.unlink()
            except Exception:
                pass
        config_path.write_text(novo, encoding="utf-8")

        importlib.reload(config)
        if apply_defaults:
            apply_defaults(config)

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

def _resolver_xlsx_path() -> Path:
    """Resolve XLSX_PATH relativo ao diretorio do config.py."""
    raw = str(getattr(config, "XLSX_PATH", "clientes.xlsx")).strip() or "clientes.xlsx"
    p = Path(raw)
    if p.is_absolute():
        return p
    config_dir = Path(getattr(config, "__file__", __file__)).parent
    return config_dir / raw


@app.get("/clientes")
async def listar_clientes():
    """Le a planilha de clientes (CNPJ/CPF + Nome)."""
    try:
        from openpyxl import load_workbook
        xlsx_path = _resolver_xlsx_path()

        if not xlsx_path.exists():
            return {"clientes": [], "path": str(xlsx_path)}

        wb = load_workbook(xlsx_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=1, values_only=True))
        wb.close()

        if not rows:
            return {"clientes": [], "path": str(xlsx_path)}

        # Detecta colunas pelo cabecalho
        header = [str(c or "").strip().lower() for c in rows[0]]
        idx_doc = next((i for i, h in enumerate(header)
                        if "cnpj" in h or "cpf" in h or "doc" in h), 0)
        idx_nome = next((i for i, h in enumerate(header)
                         if "nome" in h or "razao" in h or "cliente" in h), 1)

        clientes = []
        for row in rows[1:]:
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue
            doc = str(row[idx_doc] or "").strip() if idx_doc < len(row) else ""
            nome = str(row[idx_nome] or "").strip() if idx_nome < len(row) else ""
            if not doc and not nome:
                continue
            clientes.append({"documento": doc, "nome": nome})

        return {"clientes": clientes, "path": str(xlsx_path)}
    except Exception as e:
        logger.exception("Falha ao listar clientes")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clientes")
async def salvar_clientes(payload: dict):
    """Grava a lista de clientes na planilha (substitui conteudo)."""
    try:
        from openpyxl import Workbook
        clientes = payload.get("clientes") or []
        xlsx_path = _resolver_xlsx_path()
        xlsx_path.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = "Clientes"
        # Cabecalho
        ws.append(["CNPJ", "NOME"])
        for c in clientes:
            doc = str(c.get("documento", "")).strip()
            nome = str(c.get("nome", "")).strip()
            if doc or nome:
                ws.append([doc, nome])
        wb.save(xlsx_path)
        wb.close()

        return {"ok": True, "salvos": len(clientes), "path": str(xlsx_path)}
    except Exception as e:
        logger.exception("Falha ao salvar clientes")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/license/status")
async def license_status():
    """Retorna estado da licença atual."""
    key = load_key()
    if not key:
        return {"licensed": False, "message": "Nenhuma licença ativada.", "key_hint": None}
    valid, message = check_license()
    hint = (key[:8] + "..." + key[-4:]) if len(key) > 12 else key
    return {"licensed": valid, "message": message, "key_hint": hint}


@app.post("/license/activate")
async def license_activate_endpoint(body: dict):
    """Ativa uma chave de licença."""
    key = str(body.get("key", "")).strip()
    if not key:
        raise HTTPException(status_code=400, detail="Chave não informada.")
    valid, message = license_activate(key)
    if not valid:
        raise HTTPException(status_code=402, detail=message)
    return {"ok": True, "message": message}


@app.post("/license/deactivate")
async def license_deactivate_endpoint():
    """Remove a chave de licença local."""
    license_deactivate()
    return {"ok": True}


@app.post("/executar")
async def start_execution(body: dict):
    """Inicia execução assíncrona. Retorna { jobId }."""
    _prune_jobs()

    # ── Verificação de licença ────────────────────────────────────────────────
    licensed, lic_msg = check_license()
    if not licensed:
        raise HTTPException(status_code=402, detail=lic_msg)

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
