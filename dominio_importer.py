"""
dominio_importer.py - Automação de importação de NFS-e XML no Domínio Web (browser).

Fluxo por empresa:
  1. Abre browser com sessão persistente (login automático pelo Domínio Web)
  2. Aguarda tela de seleção de módulos
  3. Clica em "Escrita Fiscal"
  4. Popup pede usuário/senha da empresa (ou lê de config)
  5. Navega: Utilitários → Importação → Importação Padrão → NFS-E XML - Padrão Nacional
  6. Faz upload dos XMLs e confirma
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import config

log = logging.getLogger("nfse")

# Pasta onde o Playwright salva o perfil do Domínio Web (mantém sessão entre execuções)
_DOMINIO_PROFILE_DIR = Path(config.PASTA_SAIDA).parent / "dominio-profile"


# ── Popup de credenciais ──────────────────────────────────────────────────────

def pedir_credenciais(empresa_nome: str, cnpj: str) -> tuple[str, str] | None:
    """
    Exibe janela tkinter pedindo usuário/senha da empresa no Domínio Web.
    Retorna (usuario, senha) ou None se o usuário pular.
    """
    resultado: queue.Queue[tuple[str, str] | None] = queue.Queue()

    def _run() -> None:
        raiz = tk.Tk()
        raiz.withdraw()

        janela = tk.Toplevel(raiz)
        janela.title("Domínio Web — Login da Empresa")
        janela.resizable(False, False)
        janela.grab_set()
        janela.focus_force()

        w, h = 400, 270
        x = (raiz.winfo_screenwidth() - w) // 2
        y = (raiz.winfo_screenheight() - h) // 2
        janela.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(
            janela,
            text="Login — Domínio Web",
            font=("Segoe UI", 12, "bold"),
        ).pack(pady=(18, 4))

        tk.Label(
            janela,
            text=f"Empresa: {empresa_nome}\nCNPJ: {cnpj}",
            font=("Segoe UI", 9),
            justify="center",
        ).pack()

        frame = tk.Frame(janela)
        frame.pack(pady=14, padx=28, fill="x")

        tk.Label(frame, text="Usuário:", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        var_usuario = tk.StringVar()
        entry_usuario = ttk.Entry(frame, textvariable=var_usuario, width=26)
        entry_usuario.grid(row=0, column=1, padx=8)

        tk.Label(frame, text="Senha:", anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        var_senha = tk.StringVar()
        entry_senha = ttk.Entry(frame, textvariable=var_senha, show="*", width=26)
        entry_senha.grid(row=1, column=1, padx=8)

        entry_usuario.focus_set()

        def confirmar(event: object = None) -> None:
            usuario = var_usuario.get().strip()
            if not usuario:
                entry_usuario.focus_set()
                return
            resultado.put((usuario, var_senha.get()))
            janela.destroy()
            raiz.destroy()

        def pular() -> None:
            resultado.put(None)
            janela.destroy()
            raiz.destroy()

        btn_frame = tk.Frame(janela)
        btn_frame.pack(pady=4)
        ttk.Button(btn_frame, text="Entrar", command=confirmar, width=12).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="Pular empresa", command=pular, width=14).pack(side="left", padx=8)

        janela.bind("<Return>", confirmar)
        janela.bind("<Escape>", lambda _: pular())
        janela.protocol("WM_DELETE_WINDOW", pular)

        raiz.mainloop()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()

    try:
        return resultado.get_nowait()
    except queue.Empty:
        return None


# ── Importador principal ──────────────────────────────────────────────────────

class DominioImporter:
    """Automatiza a importação de XMLs NFS-e no Domínio Web via Playwright."""

    def importar(
        self,
        cnpj: str,
        empresa_nome: str,
        pastas_xml: list[Path],
    ) -> bool:
        """
        Importa os XMLs de `pastas_xml` no Domínio Web para a empresa.
        Retorna True se concluído com sucesso.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        xmls = self._coletar_xmls(pastas_xml)
        if not xmls:
            log.info("[%s] Nenhum XML nas pastas — importacao ignorada.", cnpj)
            return True

        # Credenciais: tenta config primeiro, depois pede popup
        creds_cfg = getattr(config, "DOMINIO_WEB_CREDENCIAIS", {})
        if cnpj in creds_cfg:
            usuario = creds_cfg[cnpj].get("usuario", "")
            senha = creds_cfg[cnpj].get("senha", "")
        else:
            creds = pedir_credenciais(empresa_nome, cnpj)
            if creds is None:
                log.info("[%s] Importacao no Dominio Web pulada pelo usuario.", cnpj)
                return False
            usuario, senha = creds

        url = str(getattr(config, "DOMINIO_WEB_URL", "https://www.dominioweb.com.br/")).rstrip("/") + "/"
        modulo = str(getattr(config, "DOMINIO_WEB_MODULO", "Escrita Fiscal")).strip()

        # Garante pasta de perfil persistente
        _DOMINIO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        log.info("[%s] Abrindo Dominio Web (%d XML(s))...", cnpj, len(xmls))

        with sync_playwright() as pw:
            # Usa perfil persistente para manter sessão/login automático
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(_DOMINIO_PROFILE_DIR),
                headless=False,
                slow_mo=300,
                accept_downloads=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(30_000)

            try:
                # 1. Acessa URL — login automático deve ocorrer
                page.goto(url, wait_until="domcontentloaded")

                # 2. Aguarda e clica no módulo "Escrita Fiscal"
                log.info("[%s] Aguardando selecao de modulo...", cnpj)
                self._selecionar_modulo(page, modulo, cnpj)

                # 3. Preenche login da empresa (aparece após selecionar módulo)
                log.info("[%s] Fazendo login da empresa...", cnpj)
                self._fazer_login_empresa(page, usuario, senha, cnpj)

                # 4. Navega para Utilitários → Importação
                log.info("[%s] Navegando para menu de importacao...", cnpj)
                self._navegar_importacao(page, cnpj)

                # 5. Faz upload dos XMLs e confirma
                log.info("[%s] Enviando %d XML(s)...", cnpj, len(xmls))
                self._upload_xmls(page, xmls, cnpj)

                # 6. Volta para a tela inicial (pronto para próxima empresa)
                page.goto(url, wait_until="domcontentloaded")

                log.info("[%s] Importacao no Dominio Web concluida.", cnpj)
                return True

            except PWTimeout as exc:
                log.error("[%s] Timeout no Dominio Web: %s", cnpj, exc)
                # Tenta voltar para o início mesmo em caso de erro
                try:
                    page.goto(url, wait_until="domcontentloaded")
                except Exception:
                    pass
                return False
            except Exception as exc:
                log.error("[%s] Erro no Dominio Web: %s", cnpj, exc, exc_info=True)
                try:
                    page.goto(url, wait_until="domcontentloaded")
                except Exception:
                    pass
                return False
            finally:
                ctx.close()

    # ── Etapas ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coletar_xmls(pastas: list[Path]) -> list[Path]:
        xmls: list[Path] = []
        for pasta in pastas:
            if pasta.exists():
                xmls.extend(pasta.glob("*.xml"))
        return xmls

    @staticmethod
    def _selecionar_modulo(page: object, modulo: str, cnpj: str) -> None:
        """Aguarda a tela de seleção de módulos e clica no módulo desejado."""
        from playwright.sync_api import Page
        p: Page = page  # type: ignore[assignment]

        candidatos = [
            f"button:has-text('{modulo}')",
            f"a:has-text('{modulo}')",
            f"div[role='button']:has-text('{modulo}')",
            f"li:has-text('{modulo}')",
            f"span:has-text('{modulo}')",
            f"text={modulo}",
        ]
        for sel in candidatos:
            try:
                elem = p.locator(sel).first
                # wait_for garante que o elemento apareça após o login automático
                elem.wait_for(state="visible", timeout=20_000)
                elem.click()
                p.wait_for_load_state("domcontentloaded")
                log.info("[%s] Modulo '%s' selecionado.", cnpj, modulo)
                return
            except Exception:
                continue

        log.warning("[%s] Modulo '%s' nao localizado — prosseguindo.", cnpj, modulo)

    @staticmethod
    def _fazer_login_empresa(page: object, usuario: str, senha: str, cnpj: str) -> None:
        """Preenche usuário/senha da empresa que aparece após selecionar o módulo."""
        from playwright.sync_api import Page
        p: Page = page  # type: ignore[assignment]

        seletores_usuario = [
            "input[name*='user' i]",
            "input[name*='login' i]",
            "input[name*='usuario' i]",
            "input[placeholder*='usu' i]",
            "input[type='text']",
        ]
        preencheu = False
        for sel in seletores_usuario:
            try:
                campo = p.locator(sel).first
                campo.wait_for(state="visible", timeout=10_000)
                campo.fill(usuario)
                preencheu = True
                break
            except Exception:
                continue

        if not preencheu:
            raise RuntimeError(
                f"[{cnpj}] Campo de usuario nao encontrado no login da empresa no Dominio Web."
            )

        for sel in ["input[type='password']", "input[name*='senha' i]", "input[name*='pass' i]"]:
            try:
                campo = p.locator(sel).first
                if campo.count() > 0:
                    campo.fill(senha)
                    break
            except Exception:
                continue

        for sel in [
            "button[type='submit']",
            "button:has-text('Entrar')",
            "button:has-text('Login')",
            "button:has-text('Acessar')",
            "input[type='submit']",
        ]:
            try:
                btn = p.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    p.wait_for_load_state("domcontentloaded")
                    return
            except Exception:
                continue

        p.keyboard.press("Enter")
        p.wait_for_load_state("domcontentloaded")

    @staticmethod
    def _navegar_importacao(page: object, cnpj: str) -> None:
        """
        Navega: Utilitários → Importação → Importação Padrão → NFS-E XML - Padrão Nacional
        """
        from playwright.sync_api import Page
        p: Page = page  # type: ignore[assignment]

        etapas = [
            ("Utilitários", [
                "text=Utilitários",
                "a:has-text('Utilitários')",
                "button:has-text('Utilitários')",
                "li:has-text('Utilitários')",
            ]),
            ("Importação", [
                "text=Importação",
                "a:has-text('Importação')",
                "li:has-text('Importação')",
            ]),
            ("Importação Padrão", [
                "text=Importação Padrão",
                "a:has-text('Importação Padrão')",
            ]),
            ("NFS-E XML - Padrão Nacional", [
                "text=NFS-E XML",
                "a:has-text('NFS-E XML')",
                "text=Padrão Nacional",
                "a:has-text('Padrão Nacional')",
            ]),
        ]

        for nome_etapa, seletores in etapas:
            clicou = False
            for sel in seletores:
                try:
                    elem = p.locator(sel).first
                    if elem.count() > 0:
                        elem.click()
                        p.wait_for_timeout(600)
                        clicou = True
                        log.debug("[%s] Menu: '%s'", cnpj, nome_etapa)
                        break
                except Exception:
                    continue
            if not clicou:
                raise RuntimeError(
                    f"[{cnpj}] Item '{nome_etapa}' nao encontrado no menu do Dominio Web."
                )

    @staticmethod
    def _upload_xmls(page: object, xmls: list[Path], cnpj: str) -> None:
        """Localiza o campo de upload e envia os XMLs."""
        from playwright.sync_api import Page
        p: Page = page  # type: ignore[assignment]

        caminhos = [str(x) for x in xmls]

        # Tentativa 1: input[type=file] direto
        for sel in ["input[type='file']", "input[accept*='xml' i]"]:
            try:
                inp = p.locator(sel).first
                if inp.count() > 0:
                    inp.set_input_files(caminhos)
                    p.wait_for_timeout(500)
                    _confirmar(p, cnpj)
                    return
            except Exception:
                continue

        # Tentativa 2: botão "Selecionar" abre file chooser nativo
        for sel in [
            "button:has-text('Selecionar')",
            "button:has-text('Procurar')",
            "button:has-text('Browse')",
            "button:has-text('Escolher arquivo')",
            "button:has-text('Adicionar')",
        ]:
            try:
                btn = p.locator(sel).first
                if btn.count() > 0:
                    with p.expect_file_chooser() as fc_info:
                        btn.click()
                    fc_info.value.set_files(caminhos)
                    p.wait_for_timeout(500)
                    _confirmar(p, cnpj)
                    return
            except Exception:
                continue

        raise RuntimeError(
            f"[{cnpj}] Campo de upload nao encontrado no Dominio Web. "
            "Abra manualmente e inspecione o seletor com F12."
        )


def _confirmar(page: object, cnpj: str) -> None:
    """Clica em Importar / Confirmar / OK após selecionar os arquivos."""
    from playwright.sync_api import Page
    p: Page = page  # type: ignore[assignment]

    for sel in [
        "button:has-text('Importar')",
        "button:has-text('Confirmar')",
        "button:has-text('Processar')",
        "button:has-text('OK')",
        "button[type='submit']",
    ]:
        try:
            btn = p.locator(sel).first
            if btn.count() > 0:
                btn.click()
                p.wait_for_load_state("domcontentloaded")
                log.info("[%s] Importacao confirmada.", cnpj)
                return
        except Exception:
            continue

    log.warning("[%s] Botao de confirmacao nao localizado — verifique manualmente.", cnpj)
