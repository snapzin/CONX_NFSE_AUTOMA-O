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

import html as _html
import json
import logging
import os
import re
import smtplib
import tempfile
import threading
import time
import zipfile
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Playwright, Page, sync_playwright

from config_defaults import apply_defaults, ensure_config_file

try:
    ensure_config_file()
    import config
except ImportError:
    ensure_config_file()
    import config
apply_defaults(config)
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
    # Tipos de nota a baixar: "emitidas", "recebidas" ou "ambas".
    tipos: str = "ambas"


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


_CHROME_POLICY_KEY = r"SOFTWARE\Policies\Google\Chrome\AutoSelectCertificateForUrls"
# Nomes numericos sao OBRIGATORIOS — Chrome ignora entradas com nomes nao-numericos.
# Usamos faixa alta para nao colidir com entradas existentes (GPO, etc).
_CHROME_POLICY_NAMES = ("9990", "9991", "9992")


def _set_chrome_autoselect_policy(cn: str, url_pattern: str) -> bool:
    """
    Escreve AutoSelectCertificateForUrls em HKCU para que o Chrome
    auto-selecione o certificado pelo CN ao acessar o portal.
    Escreve multiplas entradas (com e sem 'www.') para cobrir redirects.
    """
    if os.name != "nt":
        return False
    try:
        import winreg

        # Limpa entradas antigas primeiro
        _clear_chrome_autoselect_policy()

        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _CHROME_POLICY_KEY, 0,
            winreg.KEY_WRITE | winreg.KEY_READ,
        )

        # Cobre www. e sem www. (e variantes do gov.br) — Chrome usa exact host match
        patterns = [
            url_pattern,
            url_pattern.replace("www.", ""),
            "https://*.nfse.gov.br/*",
            "https://nfse.gov.br/*",
        ]
        patterns = list(dict.fromkeys(patterns))  # dedup mantendo ordem

        for idx, pat in enumerate(patterns[:len(_CHROME_POLICY_NAMES)]):
            policy = {"pattern": pat, "filter": {"SUBJECT": {"CN": cn}}}
            winreg.SetValueEx(
                key, _CHROME_POLICY_NAMES[idx], 0, winreg.REG_SZ,
                json.dumps(policy, ensure_ascii=False),
            )

        winreg.CloseKey(key)
        log.info(
            "Politica Chrome AutoSelectCert escrita (%d patterns) para CN='%s'",
            min(len(patterns), len(_CHROME_POLICY_NAMES)), cn,
        )
        return True
    except Exception as exc:
        log.warning("Falha ao escrever politica Chrome no registro: %s", exc)
        return False


def _clear_chrome_autoselect_policy() -> None:
    """Remove as entradas temporarias de auto-select do registro."""
    if os.name != "nt":
        return
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _CHROME_POLICY_KEY, 0, winreg.KEY_ALL_ACCESS,
        )
        for name in _CHROME_POLICY_NAMES:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def _modernizar_pfx(cert_path: Path, password: str, friendly_name: str = "cert") -> Path:
    """Re-exporta .pfx legado para PBES2+AES-256 (usado apenas se client_certificates ativo)."""
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption,
        pkcs12,
    )
    data = cert_path.read_bytes()
    senha_bytes = password.encode("utf-8")
    key, cert, ca_chain = pkcs12.load_key_and_certificates(data, senha_bytes)
    novo_pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=(friendly_name or "cert").encode("utf-8"),
        key=key, cert=cert, cas=ca_chain,
        encryption_algorithm=BestAvailableEncryption(senha_bytes),
    )
    fd, tmp_path = tempfile.mkstemp(prefix="nfse_pfx_", suffix=".pfx")
    os.close(fd)
    out = Path(tmp_path)
    out.write_bytes(novo_pfx_bytes)
    return out


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
        # Espera (s) para o painel da extensao carregar tudo antes de clicar.
        self.extensao_espera_s = int(getattr(config, "NFSE_EXTENSAO_ESPERA_S", 20))
        self._pfx_temp_path: Path | None = None

    def processar_cliente(
        self,
        cliente: Cliente,
        cert: CertificadoInfo,
        params: Parametros,
    ) -> tuple[int, str, int, str]:
        """Retorna (notas_emitidas, arquivo_emitidas, notas_recebidas, arquivo_recebidas)."""
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes de abrir navegador.")
        nome_pasta = _sanitizar_nome_pasta(cliente.nome)
        output_dir = self.base_output / nome_pasta
        output_dir.mkdir(parents=True, exist_ok=True)

        context = self._abrir_contexto(cert, output_dir)
        try:
            _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada.")
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)

            self._login_com_certificado(page, cliente, cert)

            ext_id = self._obter_extension_id(context, cliente)

            tipos = str(getattr(params, "tipos", "ambas") or "ambas").lower()
            baixar_emitidas = tipos in ("emitidas", "ambas")
            baixar_recebidas = tipos in ("recebidas", "ambas")

            ne, ae, nr, ar = 0, "", 0, ""
            if baixar_emitidas:
                ne, ae = self._baixar_tipo_extensao(
                    page, context, ext_id, "emitidas", params, output_dir, cliente
                )
            if baixar_recebidas:
                nr, ar = self._baixar_tipo_extensao(
                    page, context, ext_id, "recebidas", params, output_dir, cliente
                )
            return ne, ae, nr, ar
        finally:
            try:
                context.close()
            except Exception:
                pass
            # Remove PFX modernizado temporario (contem chave privada)
            if self._pfx_temp_path is not None:
                try:
                    self._pfx_temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                self._pfx_temp_path = None

    def _obter_extension_id(self, context, cliente: Cliente) -> str:
        """Detecta o ID da extensao NFSe no contexto do browser."""
        ext_id = str(getattr(config, "CHROME_EXTENSION_ID", "")).strip()
        if ext_id:
            log.info("[%s] Usando CHROME_EXTENSION_ID configurado: %s...", cliente.cnpj, ext_id[:8])
            return ext_id

        # Aguarda service workers registrarem (Manifest V3)
        for _ in range(20):
            for sw in context.service_workers():
                if sw.url.startswith("chrome-extension://"):
                    eid = sw.url.split("//")[1].split("/")[0]
                    log.info("[%s] Extensao detectada via service worker: %s...", cliente.cnpj, eid[:8])
                    return eid
            time.sleep(0.5)

        # Tenta background pages (Manifest V2)
        for bp in context.background_pages():
            if bp.url.startswith("chrome-extension://"):
                eid = bp.url.split("//")[1].split("/")[0]
                log.info("[%s] Extensao detectada via background page: %s...", cliente.cnpj, eid[:8])
                return eid

        raise RuntimeError(
            f"[{cliente.cnpj}] ID da extensao NFSe nao encontrado automaticamente. "
            "Configure CHROME_EXTENSION_ID em config.py."
        )

    def _abrir_popup_extensao(self, context, ext_id: str, page_portal) -> None:
        """
        Abre o Side Panel da extensao 'Baixar NFSe' clicando fisicamente
        no icone fixado via pyautogui. Nao retorna page (side panel nao e
        acessivel via CDP) — os cliques subsequentes tambem sao via pyautogui.
        """
        # Maximiza a janela do Chrome para coordenadas previsiveis
        try:
            page_portal.bring_to_front()
            cdp = context.new_cdp_session(page_portal)
            cdp.send("Browser.setWindowBounds", {
                "windowId": cdp.send("Browser.getWindowForTarget")["windowId"],
                "bounds": {"windowState": "maximized"},
            })
            time.sleep(0.6)
        except Exception as e:
            log.debug("Maximize falhou: %s", e)

        # Traz o Chrome para o primeiro plano — senao os cliques/screenshots
        # do pyautogui caem em outra janela (ex.: VS Code).
        self._focar_chrome()

        # Se o painel JA esta aberto (ex.: 2o tipo no modo 'Ambas', logo apos
        # baixar as emitidas), NAO clica no icone de novo — o icone funciona
        # como toggle e fecharia o painel. Apenas reutiliza o que ja esta aberto.
        if self._side_panel_aberto():
            log.info("Side panel ja aberto; reutilizando (sem novo clique no icone).")
            return

        # Clique fisico no icone da extensao via pyautogui
        # (Funcao tenta image recognition + coords fixas como fallback)
        try:
            self._clicar_icone_via_pyautogui(context, ext_id, None)
        except Exception as e:
            log.warning("Falha no clique do icone: %s", e)
            raise RuntimeError(
                f"Nao foi possivel clicar no icone da extensao (ID: {ext_id}). "
                "Verifique que o icone esta FIXADO na barra do Chrome (clique direito no "
                "icone do quebra-cabeca -> Fixar)."
            )

    def _clicar_icone_via_pyautogui(self, context, ext_id: str, cdp) -> bool:
        """
        Localiza e clica no icone fixado da extensao via pyautogui.
        Estrategia: reconhecimento por imagem (icon16/32/48.png), fallback
        para coordenadas fixas baseadas em janela maximizada.
        Retorna True se algum clique foi feito.
        """
        try:
            import pyautogui
            import pygetwindow as gw
        except ImportError as e:
            log.error("pyautogui/pygetwindow nao instalados: %s. "
                      "Rode: pip install -r requirements.txt", e)
            return False

        # Ativa janela do Chrome
        try:
            chrome_wins = [w for w in gw.getAllWindows()
                           if w.title and ("Chrome" in w.title or "NFS-e" in w.title)]
            if chrome_wins:
                win = next((w for w in chrome_wins if w.visible and w.width > 100), chrome_wins[0])
                log.info("Janela Chrome: '%s' em (%d,%d) %dx%d",
                         win.title, win.left, win.top, win.width, win.height)
                win.activate()
                time.sleep(0.5)
        except Exception as e:
            log.debug("Ativacao da janela falhou: %s", e)

        # Fecha qualquer menu/popup que tenha ficado aberto de tentativa anterior.
        try:
            pyautogui.press("esc")
            time.sleep(0.3)
        except Exception:
            pass

        screen_w, screen_h = pyautogui.size()
        toolbar_y = min(85, screen_h - 1)

        # PRIORIDADE 1: template matching MULTI-ESCALA do icone REAL fixado.
        # Robusto a escalonamento de tela (DPI) — ao contrario do locateOnScreen.
        regiao_toolbar = (0, 0, screen_w, min(140, screen_h))
        ponto = self._template_match_icone(regiao_toolbar, threshold=0.70)
        if ponto:
            x, y = ponto
            log.info("Icone da extensao localizado (template) em (%d, %d)", x, y)
            pyautogui.click(x=x, y=y, clicks=1)
            time.sleep(1.0)
            if self._side_panel_aberto():
                log.info("Side panel aberto via icone fixado.")
                return True
            log.info("Clique no icone nao abriu o painel; tentando menu de extensoes.")
            try:
                pyautogui.press("esc")
                time.sleep(0.2)
            except Exception:
                pass

        # PRIORIDADE 2: abre o menu de extensoes (quebra-cabeca) e clica na
        # entrada da extensao, localizada por template DENTRO do menu aberto.
        for off in (150, 175, 130, 200):
            px = screen_w - off
            try:
                pyautogui.click(x=px, y=toolbar_y, clicks=1)
            except Exception:
                continue
            time.sleep(0.8)
            regiao_menu = (max(0, screen_w - 540), 60, screen_w, min(560, screen_h))
            ponto = self._template_match_icone(regiao_menu, threshold=0.62)
            if ponto:
                x, y = ponto
                log.info("Entrada da extensao no menu em (%d, %d)", x, y)
                pyautogui.click(x=x, y=y, clicks=1)
                time.sleep(1.0)
                if self._side_panel_aberto():
                    log.info("Side panel aberto via menu de extensoes.")
                    return True
            try:
                pyautogui.press("esc")
                time.sleep(0.2)
            except Exception:
                pass

        # PRIORIDADE 3 (ultimo recurso): coordenadas fixas, VERIFICANDO a abertura
        # e fechando menus errados (Escape) entre as tentativas.
        for off in (215, 245, 185, 155, 125):
            x = screen_w - off
            log.info("Tentando icone em coord (%d, %d) [offset -%d]", x, toolbar_y, off)
            try:
                pyautogui.click(x=x, y=toolbar_y, clicks=1)
            except Exception as e:
                log.warning("Click em (%d,%d) falhou: %s", x, toolbar_y, e)
                continue
            time.sleep(1.0)
            if self._side_panel_aberto():
                log.info("Side panel aberto via coordenada (offset -%d).", off)
                return True
            try:
                pyautogui.press("esc")
                time.sleep(0.2)
            except Exception:
                pass

        log.warning("Nao foi possivel abrir o side panel da extensao.")
        return False

    def _template_match_icone(self, regiao=None, threshold: float = 0.62):
        """Localiza o icone da extensao na tela via template matching multi-escala.

        Compara icon16/48/128.png (em varias escalas absolutas, p/ lidar com DPI)
        contra um recorte da tela. Retorna (x, y) do centro em coords de tela.
        """
        try:
            import pyautogui
            import numpy as np
            import cv2
        except Exception:
            return None

        ext_dir = str(getattr(config, "CHROME_EXTENSION_DIR", "") or "").strip()
        if not ext_dir:
            return None
        ext_path = Path(ext_dir)

        try:
            shot = pyautogui.screenshot()
            tela = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        except Exception:
            return None

        if regiao:
            rx, ry, rr, rb = regiao
            rx, ry = max(0, rx), max(0, ry)
            recorte = tela[ry:rb, rx:rr]
            off_x, off_y = rx, ry
        else:
            recorte = tela
            off_x, off_y = 0, 0
        if recorte.size == 0:
            return None

        def _carregar_template(arq: Path):
            """Carrega o icone e compoe a transparencia sobre fundo branco
            (a toolbar/menu do Chrome sao claros) — senao o alpha vira preto
            e o matching falha."""
            im = cv2.imread(str(arq), cv2.IMREAD_UNCHANGED)
            if im is None:
                return None
            if im.ndim == 3 and im.shape[2] == 4:
                bgr = im[:, :, :3].astype(float)
                a = (im[:, :, 3].astype(float) / 255.0)[..., None]
                return (bgr * a + 255.0 * (1.0 - a)).astype("uint8")
            return im

        melhor_score = 0.0
        melhor_ponto = None
        for nome in ("icon16.png", "icon48.png", "icon128.png"):
            arq = ext_path / nome
            if not arq.exists():
                continue
            base = _carregar_template(arq)
            if base is None:
                continue
            bh, bw = base.shape[:2]
            # Icone na toolbar/menu costuma ter ~14-26px conforme a escala de tela.
            for lado in range(12, 30, 2):
                alt = max(1, round(lado * bh / bw))  # preserva proporcao
                if recorte.shape[0] < alt or recorte.shape[1] < lado:
                    continue
                tmpl = cv2.resize(base, (lado, alt), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(recorte, tmpl, cv2.TM_CCOEFF_NORMED)
                _, maxv, _, maxloc = cv2.minMaxLoc(res)
                if maxv > melhor_score:
                    melhor_score = maxv
                    melhor_ponto = (
                        off_x + maxloc[0] + lado // 2,
                        off_y + maxloc[1] + alt // 2,
                    )

        log.info("Template matching icone: score=%.2f (limiar=%.2f)",
                 melhor_score, threshold)
        return melhor_ponto if melhor_score >= threshold else None

    def _side_panel_aberto(self) -> bool:
        """Detecta se o side panel 'Baixar NFSe' esta aberto.

        Assinatura do painel: cabecalho ESCURO largo na faixa direita (a barra
        preta com o titulo 'Baixar NFSe') E, logo abaixo, um CORPO CLARO (o
        conteudo branco do painel). Exigir as duas coisas evita falso positivo
        com janelas escuras (VS Code, etc.) e com o menu de extensoes.
        """
        try:
            import pyautogui
            import numpy as np
            import cv2
        except Exception:
            return False
        try:
            shot = pyautogui.screenshot()
            img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]
            x0 = max(0, w - 460)
            faixa = img[:, x0:w]
            gray = cv2.cvtColor(faixa, cv2.COLOR_BGR2GRAY)
            fh, fw = gray.shape

            # 1. Cabecalho escuro: alguma linha larga e escura no topo do painel.
            topo_ini, topo_fim = min(90, fh), min(310, fh)
            header_y = None
            for y in range(topo_ini, topo_fim):
                if int((gray[y] < 80).sum()) >= fw * 0.6:
                    header_y = y
                    break
            if header_y is None:
                return False

            # 2. Corpo claro logo abaixo do cabecalho (conteudo branco do painel).
            corpo_ini = min(header_y + 45, fh)
            corpo_fim = min(corpo_ini + 200, fh)
            if corpo_fim - corpo_ini < 40:
                return False
            corpo = gray[corpo_ini:corpo_fim]
            fracao_clara = float((corpo > 170).mean())
            return fracao_clara >= 0.5
        except Exception:
            return False

    def _focar_chrome(self) -> bool:
        """Traz a janela do Chrome para o PRIMEIRO PLANO de forma robusta.

        Critico: os cliques/screenshots do pyautogui agem na janela em foco.
        Se o Chrome nao estiver na frente, tudo cai na janela errada. Usa o
        truque AttachThreadInput (ctypes) para contornar a protecao do Windows
        contra roubo de foco. Retorna True se conseguiu focar.
        """
        try:
            import pygetwindow as gw
        except Exception:
            return False
        try:
            wins = [w for w in gw.getAllWindows()
                    if w.title and ("NFS-e" in w.title or "Chrome" in w.title)]
            if not wins:
                return False
            win = next((w for w in wins if w.visible and w.width > 200), wins[0])
            hwnd = getattr(win, "_hWnd", None)

            focado_via_ctypes = False
            if hwnd:
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    kernel32 = ctypes.windll.kernel32
                    SW_RESTORE = 9
                    fg = user32.GetForegroundWindow()
                    cur = kernel32.GetCurrentThreadId()
                    fg_thread = user32.GetWindowThreadProcessId(fg, None)
                    win_thread = user32.GetWindowThreadProcessId(hwnd, None)
                    user32.AttachThreadInput(win_thread, cur, True)
                    user32.AttachThreadInput(fg_thread, cur, True)
                    # IMPORTANTE: so restaura se estiver MINIMIZADA. SW_RESTORE
                    # numa janela maximizada a DESMAXIMIZA — o que causava o
                    # efeito de "entrar e sair da tela cheia" a cada clique.
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, SW_RESTORE)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(fg_thread, cur, False)
                    user32.AttachThreadInput(win_thread, cur, False)
                    focado_via_ctypes = True
                except Exception as e:
                    log.debug("Foreground via ctypes falhou: %s", e)

            # So usa o fallback do pygetwindow se o ctypes nao resolveu —
            # win.activate() tambem pode alterar o estado de maximizacao.
            if not focado_via_ctypes:
                try:
                    win.activate()
                except Exception:
                    pass
            time.sleep(0.4)

            try:
                import ctypes
                fg = ctypes.windll.user32.GetForegroundWindow()
                if hwnd and fg != hwnd:
                    log.warning("Chrome nao ficou em primeiro plano (foco em outra janela).")
                    return False
            except Exception:
                pass
            return True
        except Exception as e:
            log.debug("Foco do Chrome falhou: %s", e)
            return False

    def _detectar_lado_panel(self):
        """
        Detecta os limites do side panel via OpenCV (procura uma faixa
        vertical na direita que tenha cor distinta da pagina).
        Retorna (panel_left, panel_top, panel_right, panel_bottom) em coords de tela.
        """
        try:
            import pyautogui
            import numpy as np
            import cv2

            screenshot = pyautogui.screenshot()
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]

            # O side panel tem fundo claro (#f8f9fa) e largura ~440-480px na direita
            # Procura uma borda vertical entre painel e pagina
            # Estimativa segura: painel ocupa os ultimos 500px da tela
            return (max(0, w - 500), 0, w, h)
        except Exception:
            return None

    def _achar_botao_verde(self, regiao=None):
        """
        Procura o maior retangulo verde sólido na tela (botao 'Iniciar Download').
        Retorna (x_centro, y_centro, area) em coords de tela, ou None.
        """
        try:
            import pyautogui
            import numpy as np
            import cv2

            screenshot = pyautogui.screenshot()
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

            # Limita busca ao painel (direita da tela)
            if regiao is None:
                regiao = self._detectar_lado_panel()
            if regiao:
                px, py, pr, pb = regiao
                area = img[py:pb, px:pr]
                offset_x, offset_y = px, py
            else:
                area = img
                offset_x, offset_y = 0, 0

            # Detecta verde do botao 'Iniciar Download' (verde Bootstrap/Material)
            # HSV: H=hue 40-80, S=saturacao alta, V=brilho medio-alto
            hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
            mascara = cv2.inRange(
                hsv,
                np.array([40, 100, 80]),   # verde escuro
                np.array([85, 255, 255]),  # verde claro
            )
            # Limpa ruido
            kernel = np.ones((3, 3), np.uint8)
            mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)

            contornos, _ = cv2.findContours(
                mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
            )
            if not contornos:
                return None

            # Filtra so retangulos com area >= 2000px (botao real, nao icone pequeno)
            # e proporcao tipica de botao (largura > altura, ratio ~3:1 a 10:1)
            candidatos = []
            for c in contornos:
                x, y, w, h = cv2.boundingRect(c)
                area_px = w * h
                if area_px < 2000:
                    continue
                if h == 0:
                    continue
                ratio = w / h
                if ratio < 2.0 or ratio > 15.0:
                    continue
                candidatos.append((x, y, w, h, area_px))

            if not candidatos:
                return None

            # Pega o maior
            x, y, w, h, area_px = max(candidatos, key=lambda t: t[4])
            cx = offset_x + x + w // 2
            cy = offset_y + y + h // 2
            return (cx, cy, area_px)
        except Exception as e:
            log.debug("Detecao verde falhou: %s", e)
            return None

    def _salvar_screenshot_debug(self, cliente: Cliente, label: str) -> None:
        """Salva screenshot da tela em pasta de debug pra calibracao."""
        try:
            import pyautogui
            debug_dir = self.base_output / "_debug_screenshots"
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%H%M%S")
            path = debug_dir / f"{cliente.cnpj}_{ts}_{label}.png"
            pyautogui.screenshot(str(path))
            log.info("[%s] Screenshot debug: %s", cliente.cnpj, path.name)
        except Exception as e:
            log.debug("Screenshot falhou: %s", e)

    def _clicar_tipo_no_panel(self, tipo: str, cliente: Cliente) -> None:
        """
        Clica em 'Emitidas' ou 'Recebidas' no side panel.
        Usa o botao verde 'Iniciar Download' como ancora visual: ele esta sempre
        na parte de baixo do painel, e os botoes de tipo estao bem acima dele.
        Funciona em qualquer resolucao/setup porque encontra elementos por COR.
        """
        try:
            import pyautogui
        except ImportError:
            log.error("pyautogui nao instalado")
            return

        self._focar_chrome()
        self._salvar_screenshot_debug(cliente, f"01_antes_{tipo}")

        regiao = self._detectar_lado_panel()
        if regiao is None:
            log.warning("[%s] Side panel nao detectado.", cliente.cnpj)
            return
        panel_left, panel_top, panel_right, panel_bottom = regiao
        panel_w = panel_right - panel_left
        panel_center = panel_left + (panel_w // 2)

        # Tenta achar botao verde 'Iniciar Download' como referencia
        verde = self._achar_botao_verde(regiao=regiao)
        if verde:
            _, btn_y, _ = verde
            # Botoes Emitidas/Recebidas estao MUITO acima do verde.
            # Aprox.: 500-600px acima do botao 'Iniciar Download'
            # Sem 'Menos opcoes' expandido: ~ 400px acima
            # Com 'Menos opcoes' expandido: ~ 550px acima
            tipo_y = max(150, btn_y - 540)
        else:
            # Fallback: 1/3 do topo do painel
            tipo_y = panel_top + (panel_bottom - panel_top) // 4

        if tipo == "emitidas":
            x = panel_left + int(panel_w * 0.27)
            label = "Emitidas"
        else:
            x = panel_left + int(panel_w * 0.73)
            label = "Recebidas"

        log.info("[%s] Clicando '%s' em (%d, %d) | painel=(%d..%d) verde=%s",
                 cliente.cnpj, label, x, tipo_y, panel_left, panel_right,
                 verde[:2] if verde else None)
        try:
            pyautogui.click(x=x, y=tipo_y, clicks=1)
        except Exception as e:
            log.warning("[%s] Click pyautogui em (%d,%d) falhou: %s",
                        cliente.cnpj, x, tipo_y, e)
        time.sleep(0.5)
        self._salvar_screenshot_debug(cliente, f"02_apos_{tipo}")

    def _clicar_iniciar_download(self, cliente: Cliente) -> None:
        """
        Encontra o botao verde 'Iniciar Download' por DETECCAO DE COR (OpenCV)
        e clica fisicamente nele. Funciona em qualquer resolucao/setup.
        """
        try:
            import pyautogui
        except ImportError:
            return

        self._focar_chrome()
        self._salvar_screenshot_debug(cliente, "03_antes_iniciar")

        # Snapshot de downloads pra detectar mudancas
        downloads_dir = Path.home() / "Downloads"
        try:
            files_antes = {f.name for f in downloads_dir.iterdir() if f.is_file()}
        except Exception:
            files_antes = set()

        # Tenta encontrar o botao verde via deteccao por cor (ate 3 tentativas)
        for tentativa in range(3):
            verde = self._achar_botao_verde()
            if verde is None:
                log.warning("[%s] Botao verde 'Iniciar Download' nao encontrado "
                            "(tentativa %d/3).", cliente.cnpj, tentativa + 1)
                time.sleep(1)
                continue

            cx, cy, area_px = verde
            log.info("[%s] Botao 'Iniciar Download' detectado em (%d, %d) | area=%dpx",
                     cliente.cnpj, cx, cy, area_px)

            try:
                pyautogui.click(x=cx, y=cy, clicks=1)
            except Exception as e:
                log.warning("[%s] Click em (%d,%d) falhou: %s",
                            cliente.cnpj, cx, cy, e)
                continue

            time.sleep(1.8)

            try:
                files_agora = {f.name for f in downloads_dir.iterdir() if f.is_file()}
                novos = files_agora - files_antes
                if novos:
                    log.info("[%s] Download iniciado (novos arquivos: %s)",
                             cliente.cnpj, list(novos)[:3])
                    self._salvar_screenshot_debug(cliente, "04_download_iniciado")
                    return
            except Exception:
                pass

        self._salvar_screenshot_debug(cliente, "04_nenhum_download")
        log.warning("[%s] Nao detectou inicio de download apos 3 tentativas.",
                    cliente.cnpj)

    def _aguardar_download_em_pasta(self, cliente: Cliente, timeout_s: int = 180,
                                    panel_page=None, pastas=None) -> Optional[Path]:
        """
        Monitora a pasta Downloads por um NOVO arquivo concluido da extensao.

        A extensao 'Baixar NFSe' salva o arquivo com nome aleatorio (GUID) e
        muitas vezes SEM a extensao .zip — por isso NAO filtramos por .zip;
        consideramos qualquer arquivo novo que nao seja parcial (.crdownload/
        .tmp) e cujo tamanho ja estabilizou (terminou de baixar).

        Retorna o caminho do arquivo final, ou None se nada novo no tempo limite.
        """
        downloads_dir = Path.home() / "Downloads"
        # Vigia a pasta Downloads E pastas extra (ex.: a pasta de saida do
        # cliente). A extensao 'Baixar NFSe', em modo pasta personalizada,
        # grava o zip DIRETO na pasta de destino — entao precisamos olhar lah.
        pastas_vigiadas = [downloads_dir]
        for p in (pastas or []):
            if p and Path(p) not in pastas_vigiadas:
                pastas_vigiadas.append(Path(p))
        pastas_vigiadas = [p for p in pastas_vigiadas if p.exists()]
        if not pastas_vigiadas:
            log.warning("[%s] Nenhuma pasta de download disponivel.", cliente.cnpj)
            return None

        parciais_suf = (".crdownload", ".tmp", ".part", ".partial", ".download")

        def _listar(pasta: Path):
            try:
                return [f for f in pasta.iterdir() if f.is_file()]
            except OSError:
                return []

        # Snapshot inicial por pasta (ignora os arquivos que ja existiam).
        existentes = {str(p): {f.name for f in _listar(p)} for p in pastas_vigiadas}

        self._sem_notas = False  # sinaliza ao chamador que o painel disse "sem notas"
        deadline = time.monotonic() + timeout_s
        ultimo_log = 0.0
        ultimo_check_painel = 0.0
        tamanhos: dict[str, int] = {}  # caminho -> ultimo tamanho (estabilidade)
        while time.monotonic() < deadline:
            _check_cancel(self.cancel_event,
                          f"[{cliente.cnpj}] Cancelado aguardando download.")

            # Se o painel (DOM) avisar que nao ha notas no periodo, encerra ja —
            # sem esperar o timeout inteiro nem repetir.
            agora_p = time.monotonic()
            if panel_page is not None and agora_p - ultimo_check_painel > 2:
                ultimo_check_painel = agora_p
                if self._painel_sem_notas(panel_page):
                    log.info("[%s] Painel: nenhuma nota no periodo. Indo para o proximo.",
                             cliente.cnpj)
                    self._sem_notas = True
                    return None

            novos, em_andamento = [], []
            for p in pastas_vigiadas:
                ja = existentes.get(str(p), set())
                for f in _listar(p):
                    if f.name in ja:
                        continue
                    if f.suffix.lower() in parciais_suf:
                        em_andamento.append(f)
                    else:
                        novos.append(f)

            if novos and not em_andamento:
                mais_recente = max(novos, key=lambda f: f.stat().st_mtime)
                try:
                    tam = mais_recente.stat().st_size
                except OSError:
                    tam = -1
                # So aceita quando o tamanho repetir (arquivo terminou de escrever).
                if tam > 0 and tamanhos.get(str(mais_recente)) == tam:
                    log.info("[%s] Download concluido detectado: %s (%d bytes)",
                             cliente.cnpj, mais_recente.name, tam)
                    return mais_recente
                tamanhos[str(mais_recente)] = tam

            agora = time.monotonic()
            if agora - ultimo_log > 10:
                ultimo_log = agora
                if em_andamento:
                    log.info("[%s] Aguardando download (em andamento: %s)",
                             cliente.cnpj, em_andamento[0].name)
                else:
                    log.info("[%s] Aguardando download (nenhum arquivo novo ainda)...",
                             cliente.cnpj)

            time.sleep(1)

        log.warning("[%s] Timeout aguardando download apos %ds",
                    cliente.cnpj, timeout_s)
        return None

    def _aguardar_service_worker(self, context, cdp, ext_id: str, timeout_s: int = 15):
        """Localiza/acorda o SW da extensao via CDP."""
        # Habilita CDP ServiceWorker domain (precisa antes de startWorker)
        try:
            cdp.send("ServiceWorker.enable")
        except Exception:
            pass

        # Forca o SW a acordar via ServiceWorker.startWorker
        ext_origin = f"chrome-extension://{ext_id}"
        for scope_candidate in (f"{ext_origin}/", f"{ext_origin}"):
            try:
                cdp.send("ServiceWorker.startWorker", {"scopeURL": scope_candidate})
                log.info("ServiceWorker.startWorker enviado para %s", scope_candidate)
                break
            except Exception as e:
                log.debug("startWorker '%s' falhou: %s", scope_candidate, e)

        end = time.time() + timeout_s
        while time.time() < end:
            # Procura em service_workers do Playwright (SW ativo)
            for s in context.service_workers:
                if ext_id in s.url:
                    return s

            # Procura targets via CDP e attacha (forca registro como SW ativo)
            try:
                res = cdp.send("Target.getTargets")
                for t in res.get("targetInfos", []):
                    url = t.get("url", "")
                    ttype = t.get("type", "")
                    if ext_id in url and ttype in ("service_worker", "worker"):
                        try:
                            cdp.send("Target.attachToTarget", {
                                "targetId": t["targetId"], "flatten": True,
                            })
                        except Exception:
                            pass
            except Exception:
                pass

            # Tenta novamente startWorker (caso o primeiro tenha falhado)
            try:
                cdp.send("ServiceWorker.startWorker", {"scopeURL": f"{ext_origin}/"})
            except Exception:
                pass

            time.sleep(0.5)
        return None

    def _aguardar_pagina_extensao(self, context, ext_id: str, timeout_s: int = 5, cdp=None):
        """Aguarda qualquer target (page/sidepanel/etc) cuja URL pertenca a extensao."""
        prefix = f"chrome-extension://{ext_id}/"

        # Ativa descoberta de TODOS os tipos de target (incluindo side panels)
        if cdp is not None:
            try:
                cdp.send("Target.setDiscoverTargets", {
                    "discover": True,
                    "filter": [{}],  # filtro vazio = todos os tipos
                })
            except Exception:
                pass

        end = time.time() + timeout_s
        ultimo_log = 0.0
        while time.time() < end:
            # 1. Procura em context.pages (tabs normais)
            for p in context.pages:
                if p.url.startswith(prefix):
                    return p

            # 2. Procura via CDP — match permissivo (qualquer tipo)
            if cdp is not None:
                try:
                    res = cdp.send("Target.getTargets")
                    for t in res.get("targetInfos", []):
                        url = t.get("url", "")
                        if not url.startswith(prefix):
                            continue
                        # Ignora apenas o service worker
                        if t.get("type") in ("service_worker", "worker"):
                            continue
                        tid = t.get("targetId")
                        log.info("Target da extensao encontrado: type=%s url=%s",
                                 t.get("type"), url[:120])
                        try:
                            cdp.send("Target.attachToTarget", {
                                "targetId": tid, "flatten": True,
                            })
                            time.sleep(0.6)
                            for p in context.pages:
                                if p.url.startswith(prefix):
                                    return p
                            # Atachou mas nao virou Page do Playwright — sem
                            # driver CDP direto disponivel; segue tentando/None.
                        except Exception as e:
                            log.debug("Attach falhou: %s", e)
                except Exception:
                    pass

            # Log periodico de todos os targets (a cada 5s) — diagnostico
            if cdp is not None and time.time() - ultimo_log > 5:
                ultimo_log = time.time()
                try:
                    res = cdp.send("Target.getTargets")
                    targets_str = "\n".join(
                        f"  type={t.get('type','?'):>16} url={t.get('url','')[:130]}"
                        for t in res.get("targetInfos", [])
                    )
                    log.info("Targets atuais aguardando side panel:\n%s", targets_str)
                except Exception:
                    pass

            time.sleep(0.3)
        return None

    def _obter_pagina_painel(self, context, ext_id: str, page_portal, timeout_s: int = 6):
        """Tenta obter o side panel como uma Page do Playwright (para controle
        por DOM). Retorna a Page ou None se nao estiver acessivel."""
        try:
            cdp = context.new_cdp_session(page_portal)
        except Exception:
            cdp = None
        try:
            return self._aguardar_pagina_extensao(context, ext_id, timeout_s=timeout_s, cdp=cdp)
        except Exception as e:
            log.debug("Nao obteve page do painel: %s", e)
            return None

    def _baixar_via_dom(self, panel_page, tipo: str, params: Parametros, cliente: Cliente) -> bool:
        """Configura tipo + datas e dispara o download pelo DOM do painel
        (confiavel — sem pixel/foco). Retorna True se acionou o download.

        Seletores do popup.html da extensao 'Baixar NFSe':
          .nfse-type-btn (Emitidas/Recebidas) | #dateStart | #dateEnd | #startDownloadBtn
        """
        try:
            label = "Recebidas" if tipo == "recebidas" else "Emitidas"

            # 1. Seleciona o tipo (clicar seta data-nfse-type no body do painel).
            try:
                panel_page.locator(".nfse-type-btn", has_text=label).first.click(timeout=6000)
            except Exception:
                # Fallback: seta o atributo direto, caso o clique falhe.
                panel_page.evaluate(
                    "(t) => document.body.setAttribute('data-nfse-type', t)", label
                )

            # 2. Preenche as datas (input type=date espera yyyy-mm-dd).
            di = _data_br_para_iso(params.data_inicio)
            df = _data_br_para_iso(params.data_fim)
            for sel, val in (("#dateStart", di), ("#dateEnd", df)):
                try:
                    panel_page.fill(sel, val, timeout=4000)
                    panel_page.dispatch_event(sel, "change")
                except Exception as e:
                    log.debug("[%s] Falha ao preencher %s: %s", cliente.cnpj, sel, e)

            # 3. Dispara o download.
            panel_page.click("#startDownloadBtn", timeout=6000)
            log.info("[%s] Download de %s acionado via DOM (datas %s a %s).",
                     cliente.cnpj, tipo, di, df)
            return True
        except Exception as e:
            log.warning("[%s] Falha ao baixar via DOM: %s", cliente.cnpj, e)
            return False

    def _painel_sem_notas(self, panel_page) -> bool:
        """Le o #status do painel da extensao. True se indicar que NAO ha notas
        no periodo (ex.: 'Nenhuma nota com competencia ...')."""
        if panel_page is None:
            return False
        try:
            txt = panel_page.locator("#status").inner_text(timeout=1500)
        except Exception:
            return False
        t = (txt or "").lower()
        return "nenhuma nota" in t

    def _baixar_tipo_extensao(
        self,
        page_portal,
        context,
        ext_id: str,
        tipo: str,
        params: Parametros,
        output_dir: Path,
        cliente: Cliente,
    ) -> tuple[int, str]:
        """Abre o popup da extensao, configura tipo+datas e inicia o download."""
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Cancelado antes de baixar {tipo}.")
        log.info("[%s] Baixando %s via extensao NFSe...", cliente.cnpj, tipo)

        try:
            # 0. Se o portal estiver fora do ar (503/500/403) mesmo apos o login,
            #    recarrega ate voltar antes de tentar baixar.
            if not self._recuperar_portal_se_erro(page_portal, cliente, f"antes de baixar {tipo}"):
                log.warning("[%s] Pulando %s: portal indisponivel.", cliente.cnpj, tipo)
                return 0, ""

            # 1. Abre o side panel da extensao (clique pyautogui no icone fixado)
            self._abrir_popup_extensao(context, ext_id, page_portal)

            # 2. Espera o side panel carregar TUDO (a extensao le a sessao do
            #    portal e monta os botoes/periodo). Configuravel via
            #    NFSE_EXTENSAO_ESPERA_S (padrao 20s).
            espera = max(2.5, self.extensao_espera_s)
            log.info("[%s] Aguardando %ds o painel da extensao carregar...",
                     cliente.cnpj, int(espera))
            time.sleep(espera)
            self._salvar_screenshot_debug(cliente, f"00_panel_aberto_{tipo}")

            # 3-5. Configura tipo + datas e dispara o download. PREFERE controle
            #      por DOM (confiavel: clica/seleciona por seletor e ja preenche
            #      o periodo); se o painel nao estiver acessivel via Playwright,
            #      cai para o metodo por tela (pyautogui). Com retry.
            tentativas_dl = max(1, int(getattr(config, "NFSE_DOWNLOAD_TENTATIVAS", 2)))
            novo_arquivo = None
            for tnt in range(1, tentativas_dl + 1):
                _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Cancelado ao baixar {tipo}.")

                acionou = False
                panel_page = self._obter_pagina_painel(context, ext_id, page_portal)
                if panel_page is not None:
                    acionou = self._baixar_via_dom(panel_page, tipo, params, cliente)

                if not acionou:
                    log.info("[%s] Painel via DOM indisponivel; usando metodo por tela.",
                             cliente.cnpj)
                    self._clicar_tipo_no_panel(tipo, cliente)
                    time.sleep(0.8)
                    self._clicar_iniciar_download(cliente)

                log.info("[%s] %s: download acionado (tentativa %d/%d), monitorando...",
                         cliente.cnpj, tipo, tnt, tentativas_dl)
                novo_arquivo = self._aguardar_download_em_pasta(
                    cliente, timeout_s=self.download_timeout_s, panel_page=panel_page,
                    pastas=[output_dir],
                )
                if novo_arquivo is not None:
                    break
                # Painel informou que nao ha notas: nao adianta repetir, vai pro proximo.
                if getattr(self, "_sem_notas", False):
                    log.info("[%s] %s: sem notas no periodo.", cliente.cnpj, tipo)
                    return 0, ""
                if tnt < tentativas_dl:
                    log.warning("[%s] Nenhum download de %s detectado; tentando de novo...",
                                cliente.cnpj, tipo)
                    time.sleep(2)

            if novo_arquivo is None:
                log.info("[%s] Nenhum download de %s apos %d tentativa(s). Indo para o proximo.",
                         cliente.cnpj, tipo, tentativas_dl)
                return 0, ""

            # 6. Renomeia para o NOME DA EMPRESA (move da Downloads se preciso;
            #    se o arquivo ja caiu na pasta de saida com nome GUID, renomeia
            #    no lugar).
            fname = _nome_download_cliente(cliente.nome, cliente.cnpj, novo_arquivo.name, tipo)
            dest = output_dir / fname
            try:
                if novo_arquivo.resolve() != dest.resolve():
                    if dest.exists():
                        dest.unlink()
                    import shutil
                    shutil.move(str(novo_arquivo), str(dest))
                    log.info("[%s] Arquivo renomeado para: %s", cliente.cnpj, dest.name)
            except Exception as e:
                log.warning("[%s] Falha ao renomear/mover %s -> %s: %s",
                            cliente.cnpj, novo_arquivo, dest, e)
                dest = novo_arquivo

            # 7. Conta XMLs e extrai
            try:
                count = _contar_xmls_ativos_no_zip(dest)
                _extrair_zip(dest, output_dir)
            except Exception as e:
                log.warning("[%s] Falha ao processar zip: %s", cliente.cnpj, e)
                count = 0
            log.info("[%s] %s: %d nota(s) ativa(s) em %s", cliente.cnpj, tipo, count, dest.name)
            return count, str(dest)

        finally:
            pass

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
        page.goto(url, wait_until="commit", timeout=30000)
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Cancelado apos navegar para {tipo}.")

        self._aplicar_filtros_periodo(page, params, cliente)
        notas = self._contar_notas(page, cliente, tipo)
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
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Limpa cookies/storage do cliente anterior — isolamento entre clientes
        # (substitui o que --incognito fazia, mas sem bloquear chrome-extension://)
        for subdir in ("Default", "Profile 1"):
            profile_path = user_data_dir / subdir
            if profile_path.exists():
                for to_clear in ("Cookies", "Cookies-journal", "Login Data",
                                 "Login Data-journal", "Local Storage",
                                 "Session Storage", "Sessions", "IndexedDB"):
                    target = profile_path / to_clear
                    try:
                        if target.is_file():
                            target.unlink(missing_ok=True)
                        elif target.is_dir():
                            import shutil
                            shutil.rmtree(target, ignore_errors=True)
                    except Exception:
                        pass

        # Escreve a politica AutoSelectCertificateForUrls em HKCU para que o
        # Chrome auto-selecione o certificado pelo CN ao iniciar.
        patterns = _split_csv(getattr(config, "AUTOSELECT_CERTIFICATE_PATTERNS", ""))
        url_pattern = patterns[0] if patterns else "https://www.nfse.gov.br/*"
        if cert.cn:
            sucesso_reg = _set_chrome_autoselect_policy(cert.cn, url_pattern)
            if not sucesso_reg:
                log.warning(
                    "ATENCAO: politica de auto-selecao nao pode ser escrita no registro "
                    "(provavelmente seu ambiente tem GPO corporativa). O dialogo de "
                    "selecao de certificado vai aparecer e voce precisara clicar manualmente."
                )

        kwargs: dict = {
            "user_data_dir": str(user_data_dir),
            "headless": bool(getattr(config, "PLAYWRIGHT_HEADLESS", False)),
            "args": args,
            "accept_downloads": True,
            "downloads_path": str(output_dir),
            "timeout": self.timeout_ms,
            "slow_mo": int(getattr(config, "PLAYWRIGHT_SLOW_MO_MS", 0)),
            # CRITICO: Playwright passa --disable-extensions por default,
            # que desativa TODAS as extensoes (inclusive a NFSe instalada via Web Store).
            # Removemos esses flags para a extensao funcionar.
            "ignore_default_args": [
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
            ],
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
            "--no-first-run",
            "--no-default-browser-check",
            "--no-remote",  # processo Chrome proprio (nao reusa o aberto)
            # NOTA: --incognito foi removido porque bloqueia chrome-extension://
            # URLs (ERR_BLOCKED_BY_CLIENT no popup.html). O perfil dedicado
            # 'Chrome NFSe Automacao' ja garante isolamento de sessao por cliente.
        ]

        profile_dir = str(getattr(config, "CHROME_PROFILE_DIRECTORY", "")).strip()
        if profile_dir:
            args.append(f"--profile-directory={profile_dir}")

        # NOTA: a extensao 'Baixar NFSe' deve estar INSTALADA permanentemente no
        # perfil isolado (CHROME_USER_DATA_DIR). Use CONFIGURAR_EXTENSAO.bat para
        # instalar pela Chrome Web Store uma unica vez.
        # NAO usamos --load-extension porque:
        #  1. Chrome tem bug com paths que contem espacos (silenciosamente ignora).
        #  2. Politicas corporativas podem bloquear extensoes descompactadas.
        #  3. A extensao instalada via Web Store carrega de forma confiavel.

        patterns = _split_csv(getattr(config, "AUTOSELECT_CERTIFICATE_PATTERNS", ""))
        if not patterns:
            raise ValueError("AUTOSELECT_CERTIFICATE_PATTERNS nao configurado.")

        # Filtra apenas por SUBJECT.CN — SERIAL_NUMBER no topo do filtro e invalido
        # no Chrome e faz o Chrome rejeitar o filtro inteiro (exibindo todos os certs).
        # Campos validos: SUBJECT e ISSUER com sub-campos CN, O, OU, L.
        filtro: dict[str, object] = {}
        if cert.cn:
            filtro["SUBJECT"] = {"CN": cert.cn}

        policy = [{"pattern": pattern, "filter": filtro} for pattern in patterns]
        policy_arg = json.dumps(policy, ensure_ascii=True, separators=(",", ":"))
        args.append(f"--auto-select-certificate-for-urls={policy_arg}")

        log.info(
            "AutoSelectCertificateForUrls: CN='%s' | thumbprint %s | policy=%s",
            cert.cn,
            cert.thumbprint_sha1[:16],
            policy_arg[:120],
        )
        return args

    def _login_com_certificado(self, page: Page, cliente: Cliente, cert: CertificadoInfo) -> None:
        """Loga com o certificado. Se falhar, RECARREGA a pagina e tenta de
        novo, ate NFSE_LOGIN_MAX_TENTATIVAS (padrao 5). Evita travar o lote
        inteiro num certificado problematico."""
        login_url = str(getattr(config, "NFSE_LOGIN_URL", "")).strip()
        if not login_url:
            raise ValueError("NFSE_LOGIN_URL nao configurada.")

        max_tentativas = max(1, int(getattr(config, "NFSE_LOGIN_MAX_TENTATIVAS", 5)))
        ultimo_motivo = ""
        for tentativa in range(1, max_tentativas + 1):
            _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes do login.")
            try:
                self._login_uma_tentativa(page, cliente, cert)
                # Sucesso = saiu da tela de login E nao caiu numa pagina de erro
                # (ex.: 403 Forbidden em /EmissorNacional/Certificado).
                if self._is_nfse_nacional_login(page):
                    ultimo_motivo = "ainda na tela de login apos a tentativa"
                elif self._pagina_com_erro(page):
                    ultimo_motivo = "pagina de erro de acesso (403/Forbidden)"
                else:
                    log.info("[%s] Login OK na tentativa %d/%d.",
                             cliente.cnpj, tentativa, max_tentativas)
                    return
            except ExecucaoCancelada:
                raise
            except Exception as e:
                ultimo_motivo = str(e)
                log.warning("[%s] Login falhou (tentativa %d/%d): %s",
                            cliente.cnpj, tentativa, max_tentativas, ultimo_motivo[:200])

            if tentativa < max_tentativas:
                # Espera crescente (3s, 6s, 9s...) — da folga ao portal quando
                # ele esta instavel, em vez de martelar rapido.
                espera_ms = min(3000 * tentativa, 15000)
                log.info("[%s] Recarregando p/ nova tentativa de login em %ds...",
                         cliente.cnpj, espera_ms // 1000)
                try:
                    page.goto(login_url, wait_until="commit", timeout=30000)
                except Exception:
                    try:
                        page.reload(wait_until="commit", timeout=30000)
                    except Exception:
                        pass
                page.wait_for_timeout(espera_ms)

        raise RuntimeError(
            f"[{cliente.cnpj}] Nao foi possivel logar com o certificado apos "
            f"{max_tentativas} tentativas. Ultimo motivo: {ultimo_motivo}"
        )

    def _login_uma_tentativa(self, page: Page, cliente: Cliente, cert: CertificadoInfo) -> None:
        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada antes do login.")
        login_url = str(getattr(config, "NFSE_LOGIN_URL", "")).strip()
        if not login_url:
            raise ValueError("NFSE_LOGIN_URL nao configurada.")

        log.info("[%s] Acessando login com certificado: %s", cliente.cnpj, login_url)
        try:
            page.goto(login_url, wait_until="commit", timeout=30000)
        except Exception as nav_err:
            err_str = str(nav_err)
            # Chrome pode abortar/redirecionar durante selecao automatica de certificado —
            # nao e um erro real se a pagina ja saiu da tela de login.
            if any(k in err_str for k in ("ERR_ABORTED", "net::", "frame was detached")):
                log.debug("[%s] Navegacao abortada (possivel redirecionamento de cert): %s",
                          cliente.cnpj, err_str[:120])
                page.wait_for_timeout(2000)
                if "login" not in page.url.lower():
                    log.info("[%s] Redirecionado apos selecao de certificado -> %s",
                             cliente.cnpj, page.url)
                    log.info("[%s] Login concluido com certificado %s",
                             cliente.cnpj, cert.thumbprint_sha1[:16])
                    return
            else:
                raise

        _check_cancel(self.cancel_event, f"[{cliente.cnpj}] Execucao cancelada durante login.")

        # Portal NFS-e Nacional — tenta clicar no botao "Acesso com certificado digital".
        # Se o Chrome ja redirecionou automaticamente, o metodo retorna sem erro.
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
                page.wait_for_timeout(2500)

        log.info("[%s] Login concluido com certificado %s", cliente.cnpj, cert.thumbprint_sha1[:16])

    @staticmethod
    def _is_nfse_nacional_login(page: Page) -> bool:
        url = page.url.lower()
        return "nfse.gov.br/emissornacional/login" in url or "login.acesso.gov.br" in url

    @staticmethod
    def _pagina_com_erro(page: Page) -> bool:
        """Detecta paginas de erro do portal (ex.: '403 - Forbidden: Access is
        denied.', 'The service is unavailable.').

        IMPORTANTE: so deve dar positivo numa pagina de erro REAL — nunca na
        dashboard logada. Por isso usa apenas FRASES inequivocas (sem numeros
        soltos, que casariam com valores da pagina) e exige pagina CURTA para
        termos mais genericos (paginas de erro tem pouquissimo texto).
        """
        try:
            titulo = ""
            try:
                titulo = (page.title() or "")
            except Exception:
                pass
            corpo = ""
            try:
                corpo = page.locator("body").inner_text(timeout=2500)
            except Exception:
                pass
            t = f"{titulo}\n{corpo}".lower()

            # Frases inequivocas: nunca aparecem numa pagina normal do portal.
            frases = (
                "forbidden", "access is denied", "acesso negado",
                "you do not have permission",
                "the service is unavailable", "service is unavailable",
                "servico indisponivel", "serviço indisponível",
                "temporarily unavailable",
                "internal server error", "bad gateway", "gateway timeout",
            )
            achou = next((f for f in frases if f in t), None)

            # Termos genericos so contam se a pagina for CURTA (erro tem pouco
            # texto) — evita falso positivo na dashboard, que e longa.
            if achou is None and len(corpo.strip()) < 600 and (
                "server error" in t or "erro do servidor" in t
            ):
                achou = "server error"

            if achou:
                log.warning(
                    "Pagina de erro detectada (sinal '%s') | titulo=%r | url=%s | corpo[:120]=%r",
                    achou, titulo[:80], page.url, corpo.strip()[:120],
                )
                return True
            return False
        except Exception:
            return False

    def _recuperar_portal_se_erro(self, page: Page, cliente: Cliente, desc: str = "") -> bool:
        """Se o portal estiver mostrando pagina de erro (503/500/403) — o que
        acontece mesmo APOS o login, na hora de baixar —, RECARREGA a pagina
        ate o portal voltar a responder (ate NFSE_LOGIN_MAX_TENTATIVAS).

        Retorna True se o portal esta OK, False se seguiu com erro.
        """
        if not self._pagina_com_erro(page):
            return True
        max_t = max(1, int(getattr(config, "NFSE_LOGIN_MAX_TENTATIVAS", 5)))
        for tentativa in range(1, max_t + 1):
            _check_cancel(self.cancel_event,
                          f"[{cliente.cnpj}] Cancelado recuperando portal.")
            espera_ms = min(3000 * tentativa, 15000)
            log.warning("[%s] Portal indisponivel (%s). Recarregando %d/%d em %ds...",
                        cliente.cnpj, desc or page.url, tentativa, max_t, espera_ms // 1000)
            try:
                page.reload(wait_until="commit", timeout=30000)
            except Exception as e:
                log.debug("[%s] reload falhou: %s", cliente.cnpj, str(e)[:120])
            page.wait_for_timeout(espera_ms)
            if not self._pagina_com_erro(page):
                log.info("[%s] Portal voltou a responder.", cliente.cnpj)
                return True
        log.error("[%s] Portal seguiu indisponivel apos %d recargas.",
                  cliente.cnpj, max_t)
        return False

    def _acionar_login_certificado_nfse(self, page: Page, cliente: Cliente) -> None:
        # Se o Chrome ja redirecionou para fora da tela de login, nao ha nada a clicar.
        if not self._is_nfse_nacional_login(page):
            return

        # Aguarda a pagina carregar completamente antes de buscar o botao.
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Verifica novamente se ainda esta na tela de login apos carregamento
        if not self._is_nfse_nacional_login(page):
            return

        # ------------------------------------------------------------------
        # 1. Seletor configurado pelo usuario em config.py (prioridade maxima)
        # ------------------------------------------------------------------
        cfg_selector = str(getattr(config, "NFSE_SELECTOR_BOTAO_CERTIFICADO", "")).strip()
        if cfg_selector:
            try:
                alvo = page.locator(cfg_selector).first
                alvo.scroll_into_view_if_needed(timeout=3000)
                alvo.click(timeout=8000)
                log.info("[%s] Clique via seletor config '%s'.", cliente.cnpj, cfg_selector)
                page.wait_for_timeout(1500)
                return
            except Exception:
                pass

        # ------------------------------------------------------------------
        # 2. JavaScript: varre todas as <img> buscando 'cert' em alt/src/title
        #    e clica no <a> pai — mais confiavel que CSS selector
        # ------------------------------------------------------------------
        try:
            clicked = page.evaluate("""
                () => {
                    const kw = ['certificado', 'certificate', 'cert'];
                    const has = (s) => kw.some(k => (s||'').toLowerCase().includes(k));
                    for (const img of document.querySelectorAll('img')) {
                        if (has(img.alt) || has(img.src) || has(img.title)) {
                            const el = img.closest('a') || img.closest('button') || img;
                            el.click();
                            return 'img:' + (img.alt || img.src.slice(-30));
                        }
                    }
                    for (const a of document.querySelectorAll('a[href]')) {
                        if (has(a.href) || has(a.textContent)) {
                            a.click();
                            return 'a:' + a.href.slice(-40);
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                log.info("[%s] Clique no certificado via JavaScript (%s).", cliente.cnpj, clicked)
                page.wait_for_timeout(1500)
                return
        except Exception as js_err:
            log.debug("[%s] JS click falhou: %s", cliente.cnpj, js_err)

        # ------------------------------------------------------------------
        # 3. Seletores CSS de fallback
        # ------------------------------------------------------------------
        css_selectors = [
            "img[alt='Certificado Digital']",
            "img[alt*='Certificado']",
            "img[title*='Certificado']",
            "a:has(img[alt*='Certificado'])",
            "a:has(img[alt*='certificado'])",
            "a:has(img[src*='cert'])",
            "a[href*='Certificate']",
            "a[href*='certificate']",
            "a[href*='certificado']",
            "[class*='certificado']",
            "[class*='cert-']",
        ]
        for selector in css_selectors:
            try:
                alvo = page.locator(selector).first
                if alvo.count() == 0:
                    continue
                alvo.scroll_into_view_if_needed(timeout=3000)
                alvo.click(timeout=8000)
                log.info("[%s] Clique via CSS '%s'.", cliente.cnpj, selector)
                page.wait_for_timeout(1500)
                return
            except Exception:
                continue

        # ------------------------------------------------------------------
        # 4. Localizacao por texto visivel
        # ------------------------------------------------------------------
        for texto in ("Certificado Digital", "Acesso com certificado", "Certificado"):
            for locator in (
                page.get_by_role("link", name=re.compile(texto, re.IGNORECASE)),
                page.get_by_role("button", name=re.compile(texto, re.IGNORECASE)),
                page.get_by_text(re.compile(texto, re.IGNORECASE)).first,
            ):
                try:
                    if locator.count() == 0:
                        continue
                    locator.scroll_into_view_if_needed(timeout=3000)
                    locator.click(timeout=8000)
                    log.info("[%s] Clique via texto '%s'.", cliente.cnpj, texto)
                    page.wait_for_timeout(1500)
                    return
                except Exception:
                    continue

        # Diagnostico: loga imagens encontradas para ajudar a criar o seletor
        try:
            log.warning(
                "[%s] Botao de certificado nao encontrado. Titulo: '%s' | URL: %s",
                cliente.cnpj, page.title(), page.url,
            )
            imgs = page.evaluate("""
                () => Array.from(document.querySelectorAll('img')).slice(0, 10)
                    .map(i => ({alt: i.alt, src: i.src.slice(-40), id: i.id}))
            """)
            log.warning("[%s] Imagens na pagina: %s", cliente.cnpj, imgs)
        except Exception:
            pass

        raise RuntimeError(
            "Nao foi possivel localizar o botao de login por certificado no portal NFS-e. "
            "Verifique os logs acima (lista de imagens) e configure "
            "NFSE_SELECTOR_BOTAO_CERTIFICADO em config.py com o seletor correto."
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

    def _contar_notas(self, page: Page, cliente: Cliente, tipo: str = "emitidas") -> int:
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
            r"(\d+)\s+nota(?:s)?\s+recebida(?:s)?",
            r"(\d+)\s+resultado(?:s)?",
            r"(\d+)\s+registro(?:s)?",
        )
        for pattern in regexes:
            m = re.search(pattern, body_text, re.IGNORECASE)
            if m:
                return int(m.group(1))

        raise RuntimeError(
            f"[{cliente.cnpj}] Nao foi possivel detectar notas {tipo}. "
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
                        cliente.nome,
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


def _sanitizar_nome_pasta(nome: str) -> str:
    """Converte nome do cliente para nome de pasta válido no Windows."""
    nome = _html.unescape(nome)           # &amp; → &
    nome = re.sub(r'[<>:"/\\|?*]', '', nome)
    nome = nome.strip(". ")
    return nome[:120] or "sem_nome"


def _data_br_para_iso(data_br: str) -> str:
    """Converte DD/MM/YYYY para YYYY-MM-DD (formato de input[type='date'])."""
    partes = data_br.strip().split("/")
    if len(partes) == 3:
        return f"{partes[2]}-{partes[1]}-{partes[0]}"
    return data_br


def _extrair_zip(arquivo_zip: Path, destino: Path) -> None:
    """Extrai o ZIP no diretório destino, preservando subpastas (ex: Canceladas)."""
    try:
        with zipfile.ZipFile(arquivo_zip) as zf:
            zf.extractall(destino)
        log.info("ZIP extraído em: %s", destino)
    except Exception as exc:
        log.warning("Falha ao extrair %s: %s", arquivo_zip.name, exc)


def _contar_xmls_ativos_no_zip(arquivo: Path) -> int:
    """Conta XMLs ativos (fora de subpasta 'Canceladas') dentro do ZIP."""
    try:
        with zipfile.ZipFile(arquivo) as zf:
            count = 0
            for name in zf.namelist():
                if not name.lower().endswith(".xml"):
                    continue
                partes = name.replace("\\", "/").split("/")
                # Se qualquer pasta pai contiver "cancelad", pula
                if any("cancelad" in p.lower() for p in partes[:-1]):
                    continue
                count += 1
            return count
    except Exception:
        return 0


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


def _nome_download_cliente(nome_empresa: str, cnpj: str, suggested: str, tipo: str = "") -> str:
    """Nome do arquivo baixado com o NOME DA EMPRESA.

    Formato: '<EMPRESA>_<tipo>_<timestamp>.<ext>'. Usa o nome da empresa
    (sanitizado p/ nome de arquivo valido); cai para o CNPJ se nao houver nome.
    """
    suggested = (suggested or "").strip()
    suffix = Path(suggested).suffix or ".zip"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _sanitizar_nome_pasta(nome_empresa) if (nome_empresa or "").strip() else (cnpj or "nfse")
    partes = [p for p in (base, (tipo or "").strip(), stamp) if p]
    return f"{'_'.join(partes)}{suffix}"


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
    tipos: str | None = None,
) -> Parametros:
    """Monta parametros. Se nao houver datas, usa mes anterior."""
    if not data_inicio or not data_fim:
        data_inicio, data_fim = _mes_anterior()

    tipos_norm = str(tipos or "ambas").lower().strip()
    if tipos_norm not in ("emitidas", "recebidas", "ambas"):
        tipos_norm = "ambas"

    filtrados = None
    if cnpjs:
        vistos: set[str] = set()
        filtrados = []
        for item in cnpjs:
            cnpj = _normalizar_cnpj(item)
            if len(cnpj) == 14 and cnpj not in vistos:
                filtrados.append(cnpj)
                vistos.add(cnpj)

    def _resolver_path(valor: str) -> str:
        """Resolve caminho relativo em relacao ao diretorio de config.py."""
        if not valor:
            return valor
        p = Path(valor)
        if p.is_absolute():
            return valor
        config_dir = Path(getattr(config, "__file__", __file__)).parent
        return str(config_dir / p)

    params = Parametros(
        xlsx_path=_resolver_path(str(getattr(config, "XLSX_PATH", ""))),
        pasta_certs=str(getattr(config, "PASTA_CERTS", "")),
        pasta_saida=str(getattr(config, "PASTA_SAIDA", "")),
        data_inicio=data_inicio,
        data_fim=data_fim,
        cnpjs=filtrados,
        tipos=tipos_norm,
    )
    log.info(
        "Parametros: %s -> %s | CNPJs: %s | Tipos: %s",
        params.data_inicio,
        params.data_fim,
        params.cnpjs or "todos",
        params.tipos,
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


def _escolher_cert_mais_recente(candidatos: list) -> "CertificadoInfo":
    """Dentre certificados duplicados, retorna o com maior data de validade."""
    def _validade_key(c) -> date:
        try:
            partes = c.valido_ate.split("/")
            return date(int(partes[2]), int(partes[1]), int(partes[0]))
        except Exception:
            return date.min
    return max(candidatos, key=_validade_key)


def executar_local(
    params: Parametros,
    cancel_event: threading.Event | None = None,
) -> list[ResultadoCNPJ]:
    _check_cancel(cancel_event, "Execucao cancelada antes da leitura dos certificados.")
    certs = listar_certificados(params.pasta_certs)
    certs_unicos, duplicados = indexar_certificados_por_cnpj(certs)
    clientes_xlsx = _carregar_clientes_xlsx(params.xlsx_path)

    todos_cert_cnpjs = set(certs_unicos.keys()) | set(duplicados.keys())

    if params.cnpjs:
        alvo_cnpjs = list(params.cnpjs)
    elif clientes_xlsx:
        # XLSX como filtro; inclui tambem CNPJs com cert duplicado (resolvidos adiante)
        alvo_cnpjs = sorted(clientes_xlsx.keys())
        # Diagnostico: CNPJs do XLSX sem certificado correspondente
        sem_cert = sorted(set(alvo_cnpjs) - todos_cert_cnpjs)
        if sem_cert:
            log.warning(
                "ATENCAO: %d CNPJ(s) do XLSX nao tem certificado .pfx na pasta:",
                len(sem_cert),
            )
            for cnpj_faltante in sem_cert:
                # Busca CNPJs similares (primeiros 8 digitos = raiz do CNPJ)
                raiz = cnpj_faltante[:8]
                similares = [c for c in todos_cert_cnpjs if c[:8] == raiz]
                if similares:
                    log.warning(
                        "  CNPJ %s -> nao encontrado, mas existe SIMILAR: %s "
                        "(confira se o CNPJ na planilha esta correto)",
                        cnpj_faltante, ", ".join(similares),
                    )
                else:
                    log.warning(
                        "  CNPJ %s -> nao encontrado na pasta de certificados",
                        cnpj_faltante,
                    )
            # Se NENHUM CNPJ do XLSX tem cert, avisa mas respeita a planilha
            if len(sem_cert) == len(alvo_cnpjs):
                log.warning(
                    "Nenhum CNPJ do XLSX corresponde a um certificado na pasta de certs. "
                    "Verifique se PASTA_CERTS em config.py aponta para a pasta correta."
                )
    else:
        # Sem filtro: processa todos com cert valido (unicos + duplicados resolvidos)
        alvo_cnpjs = sorted(todos_cert_cnpjs)

    if not alvo_cnpjs:
        raise RuntimeError("Nenhum CNPJ encontrado para processar.")

    log.info(
        "Certificados lidos: %d | CNPJs unicos: %d | CNPJs duplicados: %d | CNPJs alvo: %d",
        len(certs),
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
            log.info(
                "[%d/%d] Cliente XLSX: '%s' (CNPJ %s) — buscando .pfx correspondente...",
                idx, len(alvo_cnpjs), nome, cnpj,
            )

            # Resolve certificado: unico ou o mais recente entre duplicados
            cert = certs_unicos.get(cnpj)
            if cert is None and cnpj in duplicados:
                candidatos = duplicados[cnpj]
                cert = _escolher_cert_mais_recente(candidatos)
                nomes_dup = ", ".join(c.arquivo.name for c in candidatos)
                log.warning(
                    "[%s] CNPJ possui %d .pfx duplicados (%s). "
                    "Usando o mais recente: %s (val. %s).",
                    cnpj, len(candidatos), nomes_dup,
                    cert.arquivo.name, cert.valido_ate,
                )
            if cert is not None:
                log.info(
                    "[%s] Pareado: '%s' -> %s (CN do certificado: %s)",
                    cnpj, nome, cert.arquivo.name, cert.cn,
                )

            if cert is None:
                # Diagnostico: verifica se ha algum cert com erro para este CNPJ
                msg = (
                    f"Nenhum certificado .pfx encontrado para o CNPJ {cnpj} "
                    f"em {params.pasta_certs}. "
                    "Verifique se o arquivo existe e se o nome segue o padrao "
                    "'NOME senha SENHA.pfx'."
                )
                log.error(msg)
                resultados.append(
                    ResultadoCNPJ(cnpj=cnpj, nome=nome, status="erro", erro=msg)
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

        # Pasta nomeada com o nome do cliente (sem subpastas emitidas/recebidas)
        dir_empresa = base_saida / _sanitizar_nome_pasta(resultado.nome)
        xmls_ativos = [
            p for p in dir_empresa.rglob("*.xml")
            if "cancelad" not in str(p.parent.name).lower()
        ] if dir_empresa.exists() else []

        if not xmls_ativos:
            log.info("[%s] Nenhum XML ativo para importar.", resultado.cnpj)
            continue

        try:
            log.info("[%s] Iniciando importacao no Dominio Web (%d XMLs)...", resultado.cnpj, len(xmls_ativos))
            ok = importer.importar(resultado.cnpj, resultado.nome, [dir_empresa])
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
