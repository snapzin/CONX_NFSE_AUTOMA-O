"""
nfse_automacao.py - Motor principal da Automacao NFSe (execucao local).

Fluxo:
  1. Preparar parametros (datas do mes anterior ou customizadas)
  2. Ler certificados .pfx locais (CNPJ, senha, thumbprint)
  3. Abrir navegador via Playwright com AutoSelectCertificateForUrls
  4. Login com certificado, filtrar periodo e detectar notas
  5. Acionar extensao "Baixar NFSe" quando houver notas
  6. Enviar relatorio final por e-mail
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
import threading
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Playwright, Page, sync_playwright

import config
from cert_reader import CertificadoInfo, indexar_certificados_por_cnpj, listar_certificados


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nfse")


class ExecucaoCancelada(RuntimeError):
    """Sinaliza que o usuario cancelou a automacao em andamento."""


def _check_cancel(cancel_event: threading.Event | None, mensagem: str = "") -> None:
    if cancel_event and cancel_event.is_set():
        raise ExecucaoCancelada(mensagem or "Execucao cancelada pelo usuario.")


@dataclass
class Parametros:
    xlsx_path: str
    pasta_certs: str
    pasta_saida: str
    data_inicio: str
    data_fim: str
    cnpjs: Optional[list[str]] = field(default=None)


@dataclass
class ResultadoCNPJ:
    cnpj: str
    nome: str
    status: str
    notas_emitidas: int = 0
    notas_recebidas: int = 0
    arquivo_emitidas: str = ""
    arquivo_recebidas: str = ""
    thumbprint: str = ""
    erro: str = ""
    importado_dominio: bool = False

    @property
    def notas_encontradas(self) -> int:
        return self.notas_emitidas + self.notas_recebidas


@dataclass
class Cliente:
    cnpj: str
    nome: str


class NFSePlaywrightRunner:
    """Executa as etapas web no portal NFSe para um unico CNPJ."""

    def __init__(self, playwright: Playwright, cancel_event: threading.Event | None = None) -> None:
        self.playwright = playwright
        self.cancel_event = cancel_event
        self.base_output = Path(config.PASTA_SAIDA)
        self.base_output.mkdir(parents=True, exist_ok=True)
        self.timeout_ms = int(getattr(config, "PLAYWRIGHT_TIMEOUT_MS", 60000))
        self.download_timeout_s = int(getattr(config, "PLAYWRIGHT_DOWNLOAD_TIMEOUT_S", 180))
        self.login_timeout_s = int(getattr(config, "PLAYWRIGHT_LOGIN_TIMEOUT_S", 45))

    def processar_cliente(
        self,
        cliente: Cliente,
        cert: CertificadoInfo,
        params: Parametros,
    ) -> tuple[int, str, int, str]:
        """Retorna (notas_emitidas, arquivo_emitidas, notas_recebidas, arquivo_recebidas)."""
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes de abrir navegador.")
        output_dir = self.base_output / cliente.cnpj
        dir_emitidas = output_dir / "emitidas"
        dir_recebidas = output_dir / "recebidas"
        dir_emitidas.mkdir(parents=True, exist_ok=True)
        dir_recebidas.mkdir(parents=True, exist_ok=True)

        context = self._abrir_contexto(cert, output_dir)
        try:
            _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada.")
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)

            self._login_com_certificado(page, cliente, cert)

            notas_emitidas, arq_emitidas = self._processar_tipo(
                page, params, cliente, "emitidas", dir_emitidas
            )
            notas_recebidas, arq_recebidas = self._processar_tipo(
                page, params, cliente, "recebidas", dir_recebidas
            )
            return notas_emitidas, arq_emitidas, notas_recebidas, arq_recebidas
        finally:
            context.close()

    def _processar_tipo(
        self,
        page: "Page",
        params: Parametros,
        cliente: Cliente,
        tipo: str,
        output_dir: Path,
    ) -> tuple[int, str]:
        """Navega, filtra, conta e baixa notas de um tipo (emitidas ou recebidas)."""
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Cancelado antes de processar {tipo}.")
        url_cfg = "NFSE_EMITIDAS_URL" if tipo == "emitidas" else "NFSE_RECEBIDAS_URL"
        url = str(getattr(config, url_cfg, "")).strip()
        if not url:
            log.warning("[%s] URL de %s nao configurada, pulando.", cliente.cnpj, tipo)
            return 0, ""

        log.info("[%s] Processando %s: %s", cliente.cnpj, tipo, url)
        page.goto(url, wait_until="domcontentloaded")
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Cancelado apos navegar para {tipo}.")

        self._aplicar_filtros_periodo(page, params, cliente)
        notas = self._contar_notas(page, cliente)
        log.info("[%s] %s no periodo: %d nota(s)", cliente.cnpj, tipo.capitalize(), notas)

        arquivo = ""
        if notas > 0:
            arquivo = str(self._baixar_nfse(page, output_dir, cliente))
        return notas, arquivo

    def _abrir_contexto(self, cert: CertificadoInfo, output_dir: Path):
        _check_cancel(self.cancel_event, "Execucao cancelada antes de abrir contexto do navegador.")
        args = self._montar_args_chromium(cert)
        user_data_dir = Path(getattr(config, "CHROME_USER_DATA_DIR", "")).expanduser()
        if not str(user_data_dir).strip():
            user_data_dir = output_dir / "_profile"
        else:
            sufixo = cert.documento or cert.nome_amigavel or "default"
            sufixo = re.sub(r"[^\w\-]", "_", sufixo)
            user_data_dir = user_data_dir / sufixo
        user_data_dir.mkdir(parents=True, exist_ok=True)

        kwargs: dict = {
            "user_data_dir": str(user_data_dir),
            "headless": bool(getattr(config, "PLAYWRIGHT_HEADLESS", False)),
            "args": args,
            "accept_downloads": True,
            "downloads_path": str(output_dir),
            "timeout": self.timeout_ms,
            "slow_mo": int(getattr(config, "PLAYWRIGHT_SLOW_MO_MS", 0)),
        }

        channel = str(getattr(config, "CHROME_CHANNEL", "")).strip()
        if channel:
            kwargs["channel"] = channel

        executable_path = str(getattr(config, "CHROME_EXECUTABLE_PATH", "")).strip()
        if executable_path:
            kwargs["executable_path"] = executable_path

        log.info("Abrindo browser para %s", cert.documento or cert.nome_amigavel)
        return self.playwright.chromium.launch_persistent_context(**kwargs)

    def _montar_args_chromium(self, cert: CertificadoInfo) -> list[str]:
        _check_cancel(self.cancel_event, "Execucao cancelada ao montar argumentos do Chromium.")
        args: list[str] = [
            "--disable-session-crashed-bubble",
            "--disable-features=InfiniteSessionRestore",
        ]

        extension_dir = str(getattr(config, "CHROME_EXTENSION_DIR", "")).strip()
        if extension_dir:
            ext_path = Path(extension_dir)
            if not ext_path.exists():
                raise FileNotFoundError(f"Extensao nao encontrada: {ext_path}")
            args.extend(
                [
                    f"--disable-extensions-except={ext_path}",
                    f"--load-extension={ext_path}",
                ]
            )
            log.info("Extensao carregada: %s", ext_path)

        patterns = _split_csv(getattr(config, "AUTOSELECT_CERTIFICATE_PATTERNS", ""))
        if not patterns:
            raise ValueError("AUTOSELECT_CERTIFICATE_PATTERNS nao configurado.")

        filtro: dict[str, object] = {}
        if cert.cn:
            filtro["SUBJECT"] = {"CN": cert.cn}
        if cert.serial_number:
            filtro["SERIAL_NUMBER"] = cert.serial_number

        policy = [{"pattern": pattern, "filter": filtro} for pattern in patterns]
        policy_arg = json.dumps(policy, ensure_ascii=True, separators=(",", ":"))
        args.append(f"--auto-select-certificate-for-urls={policy_arg}")

        log.info(
            "AutoSelectCertificateForUrls aplicado para %s (thumbprint %s)",
            cert.documento or cert.nome_amigavel,
            cert.thumbprint_sha1[:16],
        )
        return args

    def _login_com_certificado(self, page: Page, cliente: Cliente, cert: CertificadoInfo) -> None:
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes do login.")
        login_url = str(getattr(config, "NFSE_LOGIN_URL", "")).strip()
        if not login_url:
            raise ValueError("NFSE_LOGIN_URL nao configurada.")

        log.info("[%s] Acessando login com certificado: %s", cliente.cnpj, login_url)
        page.goto(login_url, wait_until="domcontentloaded")
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada durante login.")

        # Portal NFS-e Nacional exige clique no bloco "Acesso com certificado digital".
        if self._is_nfse_nacional_login(page):
            self._acionar_login_certificado_nfse(page, cliente)

        selector_ok = str(getattr(config, "NFSE_SELECTOR_LOGIN_OK", "")).strip()
        if selector_ok:
            page.wait_for_selector(selector_ok, timeout=self.login_timeout_s * 1000)
        else:
            if self._is_nfse_nacional_login(page):
                try:
                    page.wait_for_url(
                        re.compile(r"^(?!.*EmissorNacional/Login).*$"),
                        timeout=self.login_timeout_s * 1000,
                    )
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError(
                        "Nao foi possivel concluir o login com certificado no portal NFS-e. "
                        "Verifique se o certificado foi auto-selecionado e se o clique no botao "
                        "'Acesso com certificado digital' ocorreu."
                    ) from exc
            else:
                # Fallback generico quando nao houver seletor de sucesso configurado.
                page.wait_for_timeout(2500)

        log.info("[%s] Login concluido com certificado %s", cliente.cnpj, cert.thumbprint_sha1[:16])

    @staticmethod
    def _is_nfse_nacional_login(page: Page) -> bool:
        return "nfse.gov.br/emissornacional/login" in page.url.lower()

    def _acionar_login_certificado_nfse(self, page: Page, cliente: Cliente) -> None:
        selectors: list[str] = []
        cfg_selector = str(getattr(config, "NFSE_SELECTOR_BOTAO_CERTIFICADO", "")).strip()
        if cfg_selector:
            selectors.append(cfg_selector)

        selectors.extend(
            [
                "a:has(img[alt*='Certificado'])",
                "a:has(img[src*='cert'])",
                "img[alt*='Certificado']",
            ]
        )

        for selector in selectors:
            try:
                alvo = page.locator(selector).first
                if alvo.count() == 0:
                    continue
                alvo.click(timeout=8000)
                log.info(
                    "[%s] Clique em 'Acesso com certificado digital' realizado (%s).",
                    cliente.cnpj,
                    selector,
                )
                page.wait_for_timeout(1200)
                return
            except Exception:  # noqa: BLE001
                continue

        raise RuntimeError(
            "Nao foi possivel localizar o botao de login por certificado no portal NFS-e. "
            "Ajuste NFSE_SELECTOR_BOTAO_CERTIFICADO em config.py."
        )

    def _aplicar_filtros_periodo(self, page: Page, params: Parametros, cliente: Cliente) -> None:
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes de aplicar filtros.")
        sel_inicio = str(getattr(config, "NFSE_SELECTOR_DATA_INICIO", "")).strip()
        sel_fim = str(getattr(config, "NFSE_SELECTOR_DATA_FIM", "")).strip()
        sel_filtrar = str(getattr(config, "NFSE_SELECTOR_BOTAO_FILTRAR", "")).strip()

        if sel_inicio:
            self._preencher_campo_data(page, sel_inicio, params.data_inicio)
        if sel_fim:
            self._preencher_campo_data(page, sel_fim, params.data_fim)

        if sel_filtrar:
            log.info("[%s] Aplicando filtro do periodo", cliente.cnpj)
            page.locator(sel_filtrar).first.click()
            page.wait_for_timeout(1200)
            _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada apos filtrar.")

    @staticmethod
    def _preencher_campo_data(page: Page, selector: str, valor: str) -> None:
        campo = page.locator(selector).first
        campo.wait_for(state="visible", timeout=10000)
        campo.click()
        campo.fill("")
        campo.fill(valor)
        campo.dispatch_event("change")
        campo.dispatch_event("blur")

    def _contar_notas(self, page: Page, cliente: Cliente) -> int:
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes da contagem.")
        sel_linhas = str(getattr(config, "NFSE_SELECTOR_LINHAS_NOTAS", "")).strip()
        if sel_linhas:
            return page.locator(sel_linhas).count()

        body_text = page.locator("body").inner_text(timeout=min(self.timeout_ms, 10000))
        texto_sem_notas = [
            item.lower()
            for item in str(getattr(config, "NFSE_SELECTOR_TEXTO_SEM_NOTAS", "")).split("|")
            if item.strip()
        ]
        body_lower = body_text.lower()
        if any(trecho in body_lower for trecho in texto_sem_notas):
            return 0

        regexes = (
            r"total\s*[:=]\s*(\d+)",
            r"(\d+)\s+nota(?:s)?\s+emitida(?:s)?",
            r"(\d+)\s+resultado(?:s)?",
        )
        for pattern in regexes:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                return int(m.group(1))

        raise RuntimeError(
            f"[{cliente.cnpj}] Nao foi possivel detectar notas. "
            "Configure NFSE_SELECTOR_LINHAS_NOTAS ou NFSE_SELECTOR_TEXTO_SEM_NOTAS."
        )

    def _baixar_nfse(self, page: Page, output_dir: Path, cliente: Cliente) -> Path:
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes do download.")
        before = _snapshot_files(output_dir)
        selector_botao = str(getattr(config, "NFSE_SELECTOR_BOTAO_BAIXAR", "")).strip()
        atalho_extensao = str(getattr(config, "NFSE_ATALHO_EXTENSAO", "")).strip()
        download_timeout_ms = self.download_timeout_s * 1000

        if selector_botao:
            botao = page.locator(selector_botao).first
            if botao.count() == 0:
                if not atalho_extensao:
                    raise RuntimeError(
                        f"[{cliente.cnpj}] Botao de download nao encontrado: {selector_botao}"
                    )
            else:
                try:
                    log.info("[%s] Acionando extensao via botao", cliente.cnpj)
                    with page.expect_download(timeout=download_timeout_ms) as download_info:
                        botao.click()
                    download = download_info.value
                    destino = output_dir / _nome_download_cliente(
                        cliente.cnpj,
                        download.suggested_filename,
                    )
                    download.save_as(str(destino))
                    log.info("[%s] Download salvo: %s", cliente.cnpj, destino)
                    return destino
                except PlaywrightTimeoutError:
                    log.info(
                        "[%s] Nenhum evento de download capturado, aguardando arquivo no disco.",
                        cliente.cnpj,
                    )

        if atalho_extensao:
            log.info("[%s] Acionando extensao via atalho: %s", cliente.cnpj, atalho_extensao)
            page.keyboard.press(atalho_extensao)
        elif not selector_botao:
            raise RuntimeError(
                f"[{cliente.cnpj}] Configure NFSE_SELECTOR_BOTAO_BAIXAR ou NFSE_ATALHO_EXTENSAO."
            )

        arquivo = _aguardar_novo_arquivo(
            output_dir,
            before,
            timeout_s=self.download_timeout_s,
            cancel_event=self.cancel_event,
        )
        if not arquivo:
            raise RuntimeError(
                f"[{cliente.cnpj}] Extensao acionada, mas nenhum arquivo novo foi detectado em "
                f"{output_dir} no tempo limite de {self.download_timeout_s}s."
            )
        log.info("[%s] Download detectado: %s", cliente.cnpj, arquivo)
        return arquivo


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _normalizar_cnpj(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _snapshot_files(folder: Path) -> set[str]:
    if not folder.exists():
        return set()
    return {
        str(p.resolve())
        for p in folder.iterdir()
        if p.is_file()
    }


def _aguardar_novo_arquivo(
    folder: Path,
    before: set[str],
    timeout_s: int,
    cancel_event: threading.Event | None = None,
) -> Path | None:
    fim = time.monotonic() + timeout_s
    while time.monotonic() <= fim:
        _check_cancel(cancel_event, "Execucao cancelada durante espera de download.")
        arquivos = [
            p for p in folder.iterdir()
            if p.is_file() and not p.name.lower().endswith(".crdownload")
        ]
        novos = [p for p in arquivos if str(p.resolve()) not in before]
        if novos:
            novos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return novos[0]
        time.sleep(1)
    return None


def _nome_download_cliente(cnpj: str, suggested: str) -> str:
    suggested = (suggested or "").strip()
    if not suggested:
        suggested = "nfse.zip"
    suffix = Path(suggested).suffix or ".zip"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{cnpj}_{stamp}{suffix}"


def _mes_anterior() -> tuple[str, str]:
    hoje = date.today()
    if hoje.month == 1:
        ano_ant, mes_ant = hoje.year - 1, 12
    else:
        ano_ant, mes_ant = hoje.year, hoje.month - 1
    ultimo_dia = monthrange(ano_ant, mes_ant)[1]
    inicio = date(ano_ant, mes_ant, 1).strftime("%d/%m/%Y")
    fim = date(ano_ant, mes_ant, ultimo_dia).strftime("%d/%m/%Y")
    return inicio, fim


def preparar_parametros(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpjs: list[str] | None = None,
) -> Parametros:
    """Monta parametros. Se nao houver datas, usa mes anterior."""
    if not data_inicio or not data_fim:
        data_inicio, data_fim = _mes_anterior()

    filtrados = None
    if cnpjs:
        vistos: set[str] = set()
        filtrados = []
        for item in cnpjs:
            cnpj = _normalizar_cnpj(item)
            if len(cnpj) == 14 and cnpj not in vistos:
                filtrados.append(cnpj)
                vistos.add(cnpj)

    params = Parametros(
        xlsx_path=str(getattr(config, "XLSX_PATH", "")),
        pasta_certs=str(getattr(config, "PASTA_CERTS", "")),
        pasta_saida=str(getattr(config, "PASTA_SAIDA", "")),
        data_inicio=data_inicio,
        data_fim=data_fim,
        cnpjs=filtrados,
    )
    log.info(
        "Parametros: %s -> %s | CNPJs: %s",
        params.data_inicio,
        params.data_fim,
        params.cnpjs or "todos",
    )
    return params


def _carregar_clientes_xlsx(xlsx_path: str) -> dict[str, str]:
    """
    Carrega mapa CNPJ -> nome a partir de XLSX.
    Se a planilha nao existir ou nao puder ser lida, retorna vazio.
    """
    path = Path(xlsx_path)
    if not xlsx_path or not path.exists():
        return {}

    try:
        from openpyxl import load_workbook
    except Exception as exc:  # noqa: BLE001
        log.warning("openpyxl nao disponivel para leitura de XLSX: %s", exc)
        return {}

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(min_row=1, values_only=True)
        header = next(rows, None)
        if not header:
            return {}

        header_norm = [_norm_header(cell) for cell in header]
        idx_cnpj = _find_col(
            header_norm,
            [getattr(config, "XLSX_COLUNA_CNPJ", "CNPJ"), "cnpj"],
        )
        idx_nome = _find_col(
            header_norm,
            [
                getattr(config, "XLSX_COLUNA_NOME", "NOME"),
                "nome",
                "razao",
                "empresa",
                "cliente",
            ],
        )
        if idx_cnpj is None:
            log.warning("Coluna de CNPJ nao encontrada em %s", xlsx_path)
            return {}

        clientes: dict[str, str] = {}
        for row in rows:
            if not row:
                continue
            cnpj = _normalizar_cnpj(str(row[idx_cnpj] or ""))
            if len(cnpj) != 14:
                continue
            nome = ""
            if idx_nome is not None and idx_nome < len(row):
                nome = str(row[idx_nome] or "").strip()
            clientes[cnpj] = nome or cnpj
        return clientes
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler planilha %s: %s", xlsx_path, exc)
        return {}


def _norm_header(value: object) -> str:
    texto = str(value or "").strip().lower()
    return re.sub(r"\s+", "", texto)


def _find_col(headers: list[str], candidatos: list[str]) -> int | None:
    candidatos_norm = [_norm_header(c) for c in candidatos if str(c).strip()]
    for cand in candidatos_norm:
        if cand in headers:
            return headers.index(cand)
    for idx, header in enumerate(headers):
        if any(cand in header for cand in candidatos_norm):
            return idx
    return None


def executar_local(
    params: Parametros,
    cancel_event: threading.Event | None = None,
) -> list[ResultadoCNPJ]:
    _check_cancel(cancel_event, "Execucao cancelada antes da leitura dos certificados.")
    certs = listar_certificados(params.pasta_certs)
    certs_unicos, duplicados = indexar_certificados_por_cnpj(certs)
    clientes_xlsx = _carregar_clientes_xlsx(params.xlsx_path)

    if params.cnpjs:
        alvo_cnpjs = list(params.cnpjs)
    elif clientes_xlsx:
        alvo_cnpjs = sorted(clientes_xlsx.keys())
    else:
        alvo_cnpjs = sorted(certs_unicos.keys())

    if not alvo_cnpjs:
        raise RuntimeError("Nenhum CNPJ encontrado para processar.")

    log.info(
        "Certificados validos: %d | Duplicados: %d | CNPJs alvo: %d",
        len(certs_unicos),
        len(duplicados),
        len(alvo_cnpjs),
    )

    resultados: list[ResultadoCNPJ] = []
    with sync_playwright() as playwright:
        runner = NFSePlaywrightRunner(playwright, cancel_event=cancel_event)

        for idx, cnpj in enumerate(alvo_cnpjs, start=1):
            _check_cancel(cancel_event, "Execucao cancelada pelo usuario.")
            nome = clientes_xlsx.get(cnpj, cnpj)
            log.info("[%d/%d] Processando CNPJ %s", idx, len(alvo_cnpjs), cnpj)

            if cnpj in duplicados:
                msg = (
                    f"CNPJ {cnpj} possui certificados duplicados "
                    f"({len(duplicados[cnpj])} arquivos .pfx)."
                )
                log.error(msg)
                resultados.append(
                    ResultadoCNPJ(
                        cnpj=cnpj,
                        nome=nome,
                        status="erro",
                        erro=msg,
                    )
                )
                continue

            cert = certs_unicos.get(cnpj)
            if not cert:
                msg = f"Nao existe certificado .pfx valido para o CNPJ {cnpj}."
                log.error(msg)
                resultados.append(
                    ResultadoCNPJ(
                        cnpj=cnpj,
                        nome=nome,
                        status="erro",
                        erro=msg,
                    )
                )
                continue

            if not nome or nome == cnpj:
                nome = cert.nome_amigavel or cnpj

            try:
                ne, ae, nr, ar = runner.processar_cliente(Cliente(cnpj=cnpj, nome=nome), cert, params)
                resultados.append(
                    ResultadoCNPJ(
                        cnpj=cnpj,
                        nome=nome,
                        status="ok",
                        notas_emitidas=ne,
                        arquivo_emitidas=ae,
                        notas_recebidas=nr,
                        arquivo_recebidas=ar,
                        thumbprint=cert.thumbprint_sha1,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, ExecucaoCancelada):
                    raise
                log.exception("[%s] Falha na automacao local: %s", cnpj, exc)
                resultados.append(
                    ResultadoCNPJ(
                        cnpj=cnpj,
                        nome=nome,
                        status="erro",
                        thumbprint=cert.thumbprint_sha1,
                        erro=str(exc),
                    )
                )

    # Fase 2: importar XMLs no Domínio Web (empresa por empresa)
    if bool(getattr(config, "DOMINIO_WEB_IMPORTAR", False)):
        _importar_dominio_web(resultados, cancel_event)

    return resultados


def _importar_dominio_web(
    resultados: list[ResultadoCNPJ],
    cancel_event: threading.Event | None,
) -> None:
    """Itera pelos resultados com notas baixadas e importa no Domínio Web."""
    try:
        from dominio_importer import DominioImporter
    except ImportError:
        log.warning("dominio_importer nao encontrado — importacao no Dominio Web ignorada.")
        return

    importer = DominioImporter()
    base_saida = Path(config.PASTA_SAIDA)

    for resultado in resultados:
        _check_cancel(cancel_event, "Execucao cancelada antes de importar no Dominio.")
        if resultado.status != "ok":
            continue
        if resultado.notas_emitidas == 0 and resultado.notas_recebidas == 0:
            log.info("[%s] Sem notas — pula importacao no Dominio Web.", resultado.cnpj)
            continue

        pastas_xml: list[Path] = []
        dir_empresa = base_saida / resultado.cnpj
        for sub in ("emitidas", "recebidas"):
            d = dir_empresa / sub
            if d.exists() and list(d.glob("*.xml")):
                pastas_xml.append(d)

        if not pastas_xml:
            log.info("[%s] Nenhum XML encontrado para importar.", resultado.cnpj)
            continue

        try:
            log.info("[%s] Iniciando importacao no Dominio Web...", resultado.cnpj)
            ok = importer.importar(resultado.cnpj, resultado.nome, pastas_xml)
            resultado.importado_dominio = ok
            if ok:
                log.info("[%s] Importacao no Dominio Web concluida.", resultado.cnpj)
            else:
                log.warning("[%s] Importacao no Dominio Web falhou ou foi ignorada.", resultado.cnpj)
        except Exception as exc:  # noqa: BLE001
            log.error("[%s] Erro ao importar no Dominio Web: %s", resultado.cnpj, exc)


def montar_mensagem(resultados: list[ResultadoCNPJ], params: Parametros) -> dict:
    """Formata o resumo final para envio por e-mail."""
    ok = sum(1 for r in resultados if r.status == "ok")
    erro = sum(1 for r in resultados if r.status == "erro")
    total = len(resultados)
    total_emitidas = sum(r.notas_emitidas for r in resultados if r.status == "ok")
    total_recebidas = sum(r.notas_recebidas for r in resultados if r.status == "ok")
    total_notas = total_emitidas + total_recebidas

    linhas: list[str] = []
    for r in resultados:
        if r.status == "ok":
            detalhe = f"emitidas={r.notas_emitidas} | recebidas={r.notas_recebidas}"
            if r.arquivo_emitidas:
                detalhe += f" | arq_emit={Path(r.arquivo_emitidas).name}"
            if r.arquivo_recebidas:
                detalhe += f" | arq_rec={Path(r.arquivo_recebidas).name}"
            dominio = " | dominio=OK" if r.importado_dominio else ""
            linhas.append(f"- OK   | {r.cnpj} | {r.nome} | {detalhe}{dominio}")
        else:
            linhas.append(f"- ERRO | {r.cnpj} | {r.nome}")
            linhas.append(f"  Erro: {r.erro}")

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    assunto = f"NFSe Automacao - Relatorio ({ok} OK, {erro} erro)"

    mensagem = "\n".join(
        [
            "NFSe Automacao - Relatorio",
            f"Horario: {agora}",
            f"Periodo: {params.data_inicio} -> {params.data_fim}",
            "",
            f"Total CNPJs: {total}",
            f"Sucesso: {ok}",
            f"Erros: {erro}",
            f"Notas emitidas: {total_emitidas}",
            f"Notas recebidas: {total_recebidas}",
            f"Total notas: {total_notas}",
            "",
            "Detalhes:",
            *(linhas or ["- Nenhum item processado."]),
        ]
    )

    return {
        "assunto": assunto,
        "mensagem": mensagem,
        "total": total,
        "ok": ok,
        "erro": erro,
        "houve_erro": erro > 0,
    }


def montar_mensagem_erro(erro: str) -> dict:
    """Formata a mensagem de falha critica."""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    return {
        "assunto": "NFSe Automacao - Falha critica",
        "mensagem": (
            "NFSe Automacao - Falha critica\n\n"
            f"Erro: {erro}\n"
            f"Horario: {agora}"
        ),
    }


def _destinatarios_email() -> list[str]:
    destinatarios = [
        item.strip()
        for item in str(getattr(config, "ZOHO_EMAIL_TO", "")).split(",")
        if item.strip()
    ]
    if not destinatarios:
        raise ValueError("ZOHO_EMAIL_TO nao pode ficar vazio.")
    return destinatarios


def notificar_email(assunto: str, mensagem: str) -> None:
    """Envia e-mail via SMTP do Zoho Mail."""
    email = EmailMessage()
    email["Subject"] = assunto
    email["From"] = config.ZOHO_EMAIL_FROM
    email["To"] = ", ".join(_destinatarios_email())
    email.set_content(mensagem)

    try:
        with smtplib.SMTP(
            config.ZOHO_SMTP_HOST,
            config.ZOHO_SMTP_PORT,
            timeout=30,
        ) as smtp:
            smtp.ehlo()
            if config.ZOHO_SMTP_USE_TLS:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(config.ZOHO_SMTP_USER, config.ZOHO_SMTP_PASSWORD)
            smtp.send_message(email)
        log.info("E-mail enviado com sucesso.")
    except Exception as exc:  # noqa: BLE001
        log.error("Falha ao enviar e-mail: %s", exc)


def executar(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    cnpjs: list[str] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Executa o fluxo completo da automacao local."""
    log.info("=" * 60)
    log.info("Iniciando automacao NFSe (local/Playwright)")

    try:
        params = preparar_parametros(data_inicio, data_fim, cnpjs)
        resultados = executar_local(params, cancel_event=cancel_event)

        resumo = montar_mensagem(resultados, params)
        log.info(
            "Resultado: %d ok / %d erro / %d total",
            resumo["ok"],
            resumo["erro"],
            resumo["total"],
        )
        notificar_email(resumo["assunto"], resumo["mensagem"])
    except ExecucaoCancelada as exc:
        log.warning("Automacao cancelada: %s", exc)
        raise
    except Exception as exc:  # noqa: BLE001
        log.error("Falha critica: %s", exc, exc_info=True)
        msg = montar_mensagem_erro(str(exc))
        notificar_email(msg["assunto"], msg["mensagem"])

    log.info("Automacao NFSe finalizada")
    log.info("=" * 60)


if __name__ == "__main__":
    executar()
