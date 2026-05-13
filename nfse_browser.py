"""
nfse_browser.py - Automação do portal nfse.gov.br via Selenium.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

log = logging.getLogger("nfse")

URL_LOGIN = "https://www.nfse.gov.br/EmissorNacional/Login"
TIMEOUT = 30


# ── Driver ────────────────────────────────────────────────────────────────────

def criar_driver(pasta_download: str) -> webdriver.Chrome:
    Path(pasta_download).mkdir(parents=True, exist_ok=True)

    options = Options()
    options.add_argument("--auto-select-client-certificate")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("prefs", {
        "download.default_directory": str(Path(pasta_download).resolve()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    })

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(5)
    return driver


def esperar(driver: webdriver.Chrome, by: str, valor: str, timeout: int = TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, valor))
    )


# ── Login ─────────────────────────────────────────────────────────────────────

def fazer_login(driver: webdriver.Chrome) -> bool:
    """Navega para a página de login e autentica via certificado digital."""
    log.info("Acessando portal NFSe...")
    driver.get(URL_LOGIN)

    try:
        # Clica no botão de login com certificado digital
        btn = esperar(
            driver, By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'certificado')]"
        )
        btn.click()
        log.info("Botão de certificado clicado.")
    except Exception:
        # Tenta alternativas (link, div clicável)
        try:
            btn = esperar(
                driver, By.XPATH,
                "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), 'certificado digital')]"
            )
            btn.click()
        except Exception as exc:
            log.error("Não encontrou botão de certificado: %s", exc)
            return False

    # Aguarda redirecionamento após autenticação
    try:
        WebDriverWait(driver, TIMEOUT).until(
            lambda d: "Login" not in d.title and d.current_url != URL_LOGIN
        )
        log.info("Login realizado. URL: %s", driver.current_url)
        return True
    except Exception:
        log.error("Timeout aguardando login. URL atual: %s", driver.current_url)
        return False


# ── Download ──────────────────────────────────────────────────────────────────

def abrir_painel_download(driver: webdriver.Chrome) -> bool:
    """Abre o painel lateral de download de NFS-e."""
    try:
        # Tenta encontrar o botão/ícone de download de NFS-e na barra lateral
        btn = esperar(
            driver, By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'baixar nfs')]"
        )
        btn.click()
        time.sleep(1)
        log.info("Painel de download aberto.")
        return True
    except Exception as exc:
        log.warning("Painel de download não encontrado automaticamente: %s", exc)
        return False


def preencher_datas(driver: webdriver.Chrome, data_inicio: str, data_fim: str) -> None:
    """Preenche os campos de data no painel de download."""
    wait = WebDriverWait(driver, TIMEOUT)

    # Campo data início — tenta pelos placeholders/labels mais comuns
    for seletor in [
        "//input[contains(@placeholder, 'nício') or contains(@placeholder, 'nicio')]",
        "//input[contains(@id, 'inicio') or contains(@name, 'inicio')]",
        "//label[contains(text(), 'nício')]/following::input[1]",
        "//label[contains(text(), 'Data inicial')]/following::input[1]",
    ]:
        try:
            campo = wait.until(EC.presence_of_element_located((By.XPATH, seletor)))
            campo.clear()
            campo.send_keys(data_inicio)
            log.info("Data início preenchida: %s", data_inicio)
            break
        except Exception:
            continue

    # Campo data fim
    for seletor in [
        "//input[contains(@placeholder, 'im') or contains(@placeholder, 'inal')]",
        "//input[contains(@id, 'fim') or contains(@name, 'fim')]",
        "//label[contains(text(), 'fim') or contains(text(), 'inal')]/following::input[1]",
    ]:
        try:
            campo = wait.until(EC.presence_of_element_located((By.XPATH, seletor)))
            campo.clear()
            campo.send_keys(data_fim)
            log.info("Data fim preenchida: %s", data_fim)
            break
        except Exception:
            continue


def selecionar_pdf(driver: webdriver.Chrome) -> None:
    """Seleciona o formato PDF se houver opção."""
    try:
        for seletor in [
            "//input[@type='radio' and contains(@value, 'PDF')]",
            "//input[@type='radio' and contains(@value, 'pdf')]",
            "//*[contains(text(), 'PDF')]/preceding::input[@type='radio'][1]",
        ]:
            elementos = driver.find_elements(By.XPATH, seletor)
            if elementos:
                elementos[0].click()
                log.info("Formato PDF selecionado.")
                break
    except Exception:
        pass  # Pode já estar selecionado por padrão


def clicar_baixar(driver: webdriver.Chrome) -> bool:
    """Clica no botão de download."""
    try:
        btn = esperar(
            driver, By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'baixar') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'download')]"
        )
        btn.click()
        log.info("Botão de download clicado.")
        return True
    except Exception as exc:
        log.error("Botão de download não encontrado: %s", exc)
        return False


def aguardar_download(pasta_download: str, timeout: int = 120) -> list[str]:
    """Aguarda os arquivos serem baixados. Retorna lista de arquivos baixados."""
    pasta = Path(pasta_download)
    arquivos_antes = set(pasta.glob("*"))
    inicio = time.monotonic()

    while time.monotonic() - inicio < timeout:
        time.sleep(2)
        # Verifica se há arquivos .crdownload (Chrome baixando)
        em_progresso = list(pasta.glob("*.crdownload"))
        novos = set(pasta.glob("*")) - arquivos_antes

        if novos and not em_progresso:
            arquivos = [str(f) for f in novos if f.is_file()]
            log.info("%d arquivo(s) baixado(s).", len(arquivos))
            return arquivos

    log.warning("Timeout aguardando download.")
    return []


def fazer_logout(driver: webdriver.Chrome) -> None:
    """Faz logout do portal."""
    try:
        btn = driver.find_element(
            By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'sair') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'logout')]"
        )
        btn.click()
        time.sleep(1)
        log.info("Logout realizado.")
    except Exception:
        pass


# ── Fluxo completo por cliente ────────────────────────────────────────────────

def processar_cliente(
    nome: str,
    pasta_download_cliente: str,
    data_inicio: str,
    data_fim: str,
) -> dict:
    """
    Executa o fluxo completo para um cliente já com o certificado instalado.
    Retorna dict com status e arquivos baixados.
    """
    driver = criar_driver(pasta_download_cliente)
    try:
        if not fazer_login(driver):
            return {"status": "erro", "erro": "Falha no login", "arquivos": []}

        time.sleep(2)

        if not abrir_painel_download(driver):
            return {"status": "erro", "erro": "Painel de download não encontrado", "arquivos": []}

        preencher_datas(driver, data_inicio, data_fim)
        selecionar_pdf(driver)

        if not clicar_baixar(driver):
            return {"status": "erro", "erro": "Botão de download não encontrado", "arquivos": []}

        arquivos = aguardar_download(pasta_download_cliente)
        fazer_logout(driver)

        return {"status": "ok", "erro": "", "arquivos": arquivos}

    except Exception as exc:
        log.error("Erro ao processar %s: %s", nome, exc, exc_info=True)
        return {"status": "erro", "erro": str(exc), "arquivos": []}
    finally:
        driver.quit()
