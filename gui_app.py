"""
gui_app.py - Interface grafica moderna para a Automacao NFSe.

Recursos:
  - Design moderno baseado em customtkinter (dark/light)
  - Navegacao lateral (Executar / Configuracoes / Sobre)
  - Seletor de datas com calendario
  - Painel de logs com filtro, cores por nivel e busca
  - Edicao visual do config.py com salvamento seguro
  - Indicadores de status em tempo real
"""
from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox
import tkinter as tk

import customtkinter as ctk  # type: ignore[import-untyped]
from tkcalendar import DateEntry  # type: ignore[import-untyped]

from cert_reader import indexar_certificados_por_cnpj, listar_certificados
from nfse_automacao import ExecucaoCancelada, executar
from ui_widgets import (
    AnimatedSidebarButton,
    AnimatedStatCard,
    GlowButton,
    PageTransitionBar,
    PulseBadge,
    SplashOverlay,
    Spinner,
    ToastManager,
)
import config


APP_TITLE = "NFSe Automacao"
APP_VERSION = "2.3"
CONFIG_PATH = Path(__file__).resolve().with_name("config.py")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

UI_FONT = "Bahnschrift"
UI_FONT_HEADING = "Bahnschrift SemiBold"
UI_FONT_MONO = "Consolas"


# ============================================================================
# Handler de logs
# ============================================================================
class QueueLogHandler(logging.Handler):
    """Encaminha logs para uma fila, consumida pela UI."""

    def __init__(self, output_queue: "queue.Queue[logging.LogRecord]") -> None:
        super().__init__()
        self.output_queue = output_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.output_queue.put(record)


# ============================================================================
# Paleta e estilos auxiliares
# ============================================================================
@dataclass(frozen=True)
class Palette:
    bg_sidebar: str = "#0f1724"
    bg_main: str = "#0b1220"
    bg_panel: str = "#111c2f"
    bg_card: str = "#17243a"
    accent: str = "#2aa889"
    accent_hover: str = "#249479"
    success: str = "#40cf84"
    warning: str = "#f1b34f"
    danger: str = "#e86a6a"
    text_primary: str = "#eef4ff"
    text_secondary: str = "#9db1ca"
    border: str = "#263753"


PALETTE = Palette()


LEVEL_COLORS = {
    "DEBUG": "#8b95a5",
    "INFO": "#e6edf3",
    "WARNING": "#f1c40f",
    "ERROR": "#ff6b6b",
    "CRITICAL": "#ff3860",
}


# ============================================================================
# Aplicacao principal
# ============================================================================
class NFSEGuiApp(ctk.CTk):
    """Janela principal da automacao NFSe."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} - v{APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 660)
        self.configure(fg_color=PALETTE.bg_main)

        self.log_queue: "queue.Queue[logging.LogRecord]" = queue.Queue()
        self.running = False
        self.cancel_event: threading.Event | None = None
        self.current_page: str | None = None
        self._log_filter_level = "ALL"
        self._log_search = ""

        self._build_layout()
        self._configure_logging()
        self._drain_log_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_page("executar")

        # atalhos
        self.bind("<Control-Return>", lambda _e: self._on_executar())
        self.bind("<Control-l>", lambda _e: self._limpar_logs())

        self.toasts = ToastManager(
            self,
            palette={
                "bg": PALETTE.bg_card,
                "border": PALETTE.border,
                "text": PALETTE.text_primary,
                "text_secondary": PALETTE.text_secondary,
                "accent_info": PALETTE.accent,
                "accent_success": PALETTE.success,
                "accent_warning": PALETTE.warning,
                "accent_error": PALETTE.danger,
            },
            font_family=UI_FONT,
        )

        self.after(50, self._play_splash)

    def _play_splash(self) -> None:
        splash = SplashOverlay(
            self,
            title="NFSe Automacao",
            subtitle=f"v{APP_VERSION} · pronto para emitir",
            bg=PALETTE.bg_main,
            accent=PALETTE.accent,
            text_primary=PALETTE.text_primary,
            text_secondary=PALETTE.text_secondary,
            font_heading=UI_FONT_HEADING,
            font=UI_FONT,
        )
        splash.play(
            total_ms=1000,
            on_done=lambda: self.toasts.show(
                "Tudo pronto",
                "Clique em 'Executar agora' para começar.",
                kind="success",
                duration_ms=3000,
            ),
        )

    # ----------------------------------------------------------------- layout
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.main_area = ctk.CTkFrame(self, fg_color=PALETTE.bg_main, corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(2, weight=1)

        self._build_topbar()
        self._build_transition_bar()
        self._build_pages()
        self._build_statusbar()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self,
            width=220,
            fg_color=PALETTE.bg_sidebar,
            corner_radius=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        header = ctk.CTkFrame(sidebar, fg_color="transparent", height=110)
        header.pack(fill="x", padx=18, pady=(24, 12))

        ctk.CTkLabel(
            header,
            text="NFSe",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=26, weight="bold"),
            text_color=PALETTE.text_primary,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            header,
            text="Automacao",
            font=ctk.CTkFont(family=UI_FONT, size=13),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            header,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(family=UI_FONT, size=10),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        separator = ctk.CTkFrame(sidebar, fg_color=PALETTE.border, height=1)
        separator.pack(fill="x", padx=18, pady=(6, 10))

        self.nav_buttons: dict[str, AnimatedSidebarButton] = {}
        nav_items = [
            ("executar", "Executar", ""),
            ("config", "Configuracoes", ""),
            ("sobre", "Sobre", ""),
        ]
        for key, label, icon in nav_items:
            btn = AnimatedSidebarButton(
                sidebar,
                text=label,
                icon=icon,
                command=lambda k=key: self._show_page(k),
                accent=PALETTE.accent,
                bg=PALETTE.bg_sidebar,
                bg_hover=PALETTE.bg_panel,
                bg_active=PALETTE.bg_panel,
                text_primary=PALETTE.text_primary,
                text_secondary=PALETTE.text_secondary,
                font_heading=UI_FONT_HEADING,
            )
            btn.pack(fill="x", padx=12, pady=4)
            self.nav_buttons[key] = btn

        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            footer,
            text="Tema",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=11, weight="bold"),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).pack(fill="x")

        self.theme_selector = ctk.CTkSegmentedButton(
            footer,
            values=["Escuro", "Claro"],
            command=self._on_theme_change,
            fg_color=PALETTE.bg_panel,
            selected_color=PALETTE.accent,
            selected_hover_color=PALETTE.accent_hover,
            font=ctk.CTkFont(family=UI_FONT, size=12),
        )
        self.theme_selector.set("Escuro")
        self.theme_selector.pack(fill="x", pady=(4, 0))

    def _build_topbar(self) -> None:
        topbar = ctk.CTkFrame(
            self.main_area,
            fg_color=PALETTE.bg_sidebar,
            height=68,
            corner_radius=0,
            border_width=1,
            border_color=PALETTE.border,
        )
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)

        self.page_title_var = tk.StringVar(value="Executar")
        title = ctk.CTkLabel(
            topbar,
            textvariable=self.page_title_var,
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=20, weight="bold"),
            text_color=PALETTE.text_primary,
        )
        title.pack(side="left", padx=24, pady=16)

        status_box = ctk.CTkFrame(topbar, fg_color="transparent")
        status_box.pack(side="right", padx=24, pady=16)

        self.topbar_status = ctk.CTkLabel(
            status_box,
            text="Pronto",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=12, weight="bold"),
            text_color=PALETTE.success,
        )
        self.topbar_status.pack(side="right")

        self.status_badge = PulseBadge(
            status_box,
            color=PALETTE.success,
            size=14,
            bg=PALETTE.bg_sidebar,
        )
        self.status_badge.pack(side="right", padx=(0, 8))

    def _build_transition_bar(self) -> None:
        self.transition_bar = PageTransitionBar(
            self.main_area,
            color=PALETTE.accent,
            height=2,
            bg=PALETTE.bg_main,
        )
        self.transition_bar.grid(row=1, column=0, sticky="ew")

    def _build_pages(self) -> None:
        self.page_container = ctk.CTkFrame(self.main_area, fg_color=PALETTE.bg_main, corner_radius=0)
        self.page_container.grid(row=2, column=0, sticky="nsew")
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.pages["executar"] = self._build_page_executar()
        self.pages["config"] = self._build_page_config()
        self.pages["sobre"] = self._build_page_sobre()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_area,
            fg_color=PALETTE.bg_sidebar,
            height=30,
            corner_radius=0,
            border_width=1,
            border_color=PALETTE.border,
        )
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_propagate(False)

        self.statusbar_var = tk.StringVar(value="Pronto para executar.")
        ctk.CTkLabel(
            bar,
            textvariable=self.statusbar_var,
            font=ctk.CTkFont(family=UI_FONT, size=11),
            text_color=PALETTE.text_secondary,
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            bar,
            text="Ctrl+Enter: executar  |  Ctrl+L: limpar logs",
            font=ctk.CTkFont(family=UI_FONT, size=11),
            text_color=PALETTE.text_secondary,
        ).pack(side="right", padx=16)

    # ---------------------------------------------------------------- pagina executar
    def _build_page_executar(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_container, fg_color=PALETTE.bg_main)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        # ---- cards
        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 10))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="card")

        card_kwargs = dict(
            bg_color=PALETTE.bg_card,
            bg_hover="#1d2d48",
            border_color=PALETTE.border,
            text_primary=PALETTE.text_primary,
            text_secondary=PALETTE.text_secondary,
            font_heading=UI_FONT_HEADING,
        )

        self.card_status = AnimatedStatCard(cards, "Status", "Pronto", PALETTE.success, **card_kwargs)
        self.card_status.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.card_periodo = AnimatedStatCard(
            cards, "Periodo", self._periodo_padrao_str(), PALETTE.accent, **card_kwargs
        )
        self.card_periodo.grid(row=0, column=1, sticky="ew", padx=8)

        self.card_cnpjs = AnimatedStatCard(cards, "CNPJs Filtro", "Todos", PALETTE.warning, **card_kwargs)
        self.card_cnpjs.grid(row=0, column=2, sticky="ew", padx=8)

        self.card_ultima = AnimatedStatCard(
            cards, "Ultima execucao", "-", PALETTE.text_secondary, **card_kwargs
        )
        self.card_ultima.grid(row=0, column=3, sticky="ew", padx=(8, 0))

        # ---- formulario
        form = ctk.CTkFrame(
            page,
            fg_color=PALETTE.bg_panel,
            corner_radius=14,
            border_width=1,
            border_color=PALETTE.border,
        )
        form.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form,
            text="Parametros de execucao",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=15, weight="bold"),
            text_color=PALETTE.text_primary,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            form,
            text="Defina o periodo e, opcionalmente, restrinja os CNPJs a serem processados.",
            font=ctk.CTkFont(family=UI_FONT, size=11),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=16)

        # periodo
        periodo_box = ctk.CTkFrame(
            form,
            fg_color=PALETTE.bg_card,
            corner_radius=12,
            border_width=1,
            border_color=PALETTE.border,
        )
        periodo_box.grid(row=2, column=0, sticky="nsew", padx=(16, 8), pady=12)
        periodo_box.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            periodo_box,
            text="PERIODO",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=10, weight="bold"),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 0))

        self.usar_mes_anterior = tk.BooleanVar(value=True)
        self.sw_mes_anterior = ctk.CTkSwitch(
            periodo_box,
            text="Usar mes anterior automaticamente",
            variable=self.usar_mes_anterior,
            onvalue=True,
            offvalue=False,
            command=self._toggle_data_entries,
            progress_color=PALETTE.accent,
            font=ctk.CTkFont(family=UI_FONT, size=12),
        )
        self.sw_mes_anterior.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 10))

        ctk.CTkLabel(
            periodo_box,
            text="Data inicio",
            font=ctk.CTkFont(family=UI_FONT, size=11),
            text_color=PALETTE.text_secondary,
        ).grid(row=2, column=0, sticky="w", padx=12)
        ctk.CTkLabel(
            periodo_box,
            text="Data fim",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE.text_secondary,
        ).grid(row=2, column=1, sticky="w", padx=12)

        self.data_inicio_entry = DateEntry(
            periodo_box,
            date_pattern="dd/mm/yyyy",
            locale="pt_BR",
            width=14,
            background=PALETTE.accent,
            foreground="white",
            borderwidth=0,
            font=(UI_FONT, 11),
        )
        self.data_inicio_entry.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 12))

        self.data_fim_entry = DateEntry(
            periodo_box,
            date_pattern="dd/mm/yyyy",
            locale="pt_BR",
            width=14,
            background=PALETTE.accent,
            foreground="white",
            borderwidth=0,
            font=(UI_FONT, 11),
        )
        self.data_fim_entry.grid(row=3, column=1, sticky="ew", padx=12, pady=(2, 12))

        self._toggle_data_entries()

        # cnpjs
        cnpjs_box = ctk.CTkFrame(
            form,
            fg_color=PALETTE.bg_card,
            corner_radius=12,
            border_width=1,
            border_color=PALETTE.border,
        )
        cnpjs_box.grid(row=2, column=1, sticky="nsew", padx=(8, 16), pady=12)
        cnpjs_box.grid_columnconfigure(0, weight=1)
        cnpjs_box.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            cnpjs_box,
            text="CNPJs (opcional)",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=10, weight="bold"),
            text_color=PALETTE.text_secondary,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))

        ctk.CTkLabel(
            cnpjs_box,
            text="Deixe em branco para processar todos. Separe por espaco, virgula ou linha.",
            font=ctk.CTkFont(family=UI_FONT, size=10),
            text_color=PALETTE.text_secondary,
            anchor="w",
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

        self.cnpjs_text = ctk.CTkTextbox(
            cnpjs_box,
            height=90,
            font=ctk.CTkFont(family=UI_FONT_MONO, size=11),
            fg_color=PALETTE.bg_main,
            border_color=PALETTE.border,
            border_width=1,
            corner_radius=8,
        )
        self.cnpjs_text.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.cnpjs_text.bind("<KeyRelease>", lambda _e: self._update_cnpj_card())

        # acoes
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))

        self.executar_btn = GlowButton(
            actions,
            text="Executar agora",
            command=self._on_executar,
            height=42,
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=14, weight="bold"),
            fg_color=PALETTE.accent,
            hover_color=PALETTE.accent_hover,
            border_color=PALETTE.accent,
            corner_radius=10,
            glow_color=PALETTE.success,
        )
        self.executar_btn.pack(side="left")
        self.executar_btn.start_glow(base=PALETTE.accent, peak=PALETTE.success)

        self.exec_spinner = Spinner(
            actions,
            size=26,
            thickness=3,
            color=PALETTE.success,
            bg=PALETTE.bg_panel,
        )

        self.cancelar_btn = ctk.CTkButton(
            actions,
            text="Cancelar",
            command=self._on_cancelar,
            height=42,
            width=120,
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=12, weight="bold"),
            fg_color=PALETTE.danger,
            hover_color="#c0392b",
            corner_radius=10,
            state="disabled",
        )
        self.cancelar_btn.pack(side="left", padx=(8, 0))

        self.contar_certs_btn = ctk.CTkButton(
            actions,
            text="Contar certificados",
            command=self._on_contar_certificados,
            height=42,
            width=170,
            font=ctk.CTkFont(family=UI_FONT, size=12),
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            corner_radius=10,
        )
        self.contar_certs_btn.pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            actions,
            text="Limpar logs",
            command=self._limpar_logs,
            height=42,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            corner_radius=10,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            actions,
            text="Abrir pasta de saida",
            command=self._abrir_pasta_saida,
            height=42,
            width=160,
            font=ctk.CTkFont(family=UI_FONT, size=12),
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            corner_radius=10,
        ).pack(side="left", padx=(8, 0))

        self.progress = ctk.CTkProgressBar(
            actions,
            height=12,
            progress_color=PALETTE.accent,
            fg_color=PALETTE.bg_main,
            corner_radius=6,
        )
        self.progress.pack(side="right", fill="x", expand=True, padx=(12, 0))
        self.progress.set(0)

        # ---- logs
        self._build_logs_panel(page)
        return page

    def _build_logs_panel(self, parent: ctk.CTkFrame) -> None:
        logs_frame = ctk.CTkFrame(
            parent,
            fg_color=PALETTE.bg_panel,
            corner_radius=14,
            border_width=1,
            border_color=PALETTE.border,
        )
        logs_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(8, 16))
        logs_frame.grid_columnconfigure(0, weight=1)
        logs_frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(logs_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        header.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            header,
            text="Logs de execucao",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=13, weight="bold"),
            text_color=PALETTE.text_primary,
        ).grid(row=0, column=0, sticky="w")

        self.log_level_filter = ctk.CTkSegmentedButton(
            header,
            values=["ALL", "INFO", "WARNING", "ERROR"],
            command=lambda v: self._set_log_filter(v),
            fg_color=PALETTE.bg_card,
            selected_color=PALETTE.accent,
            selected_hover_color=PALETTE.accent_hover,
            font=ctk.CTkFont(family=UI_FONT, size=11),
        )
        self.log_level_filter.set("ALL")
        self.log_level_filter.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.log_search_entry = ctk.CTkEntry(
            header,
            placeholder_text="Buscar nos logs...",
            height=28,
            fg_color=PALETTE.bg_card,
            border_color=PALETTE.border,
            font=ctk.CTkFont(family=UI_FONT, size=11),
        )
        self.log_search_entry.grid(row=0, column=2, sticky="ew", padx=12)
        self.log_search_entry.bind("<KeyRelease>", lambda _e: self._on_log_search())

        ctk.CTkButton(
            header,
            text="Copiar",
            command=self._copiar_logs,
            width=72,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            font=ctk.CTkFont(family=UI_FONT, size=11),
        ).grid(row=0, column=3, sticky="e")

        self.logs_text = ctk.CTkTextbox(
            logs_frame,
            fg_color=PALETTE.bg_main,
            border_width=0,
            corner_radius=8,
            font=ctk.CTkFont(family=UI_FONT_MONO, size=11),
        )
        self.logs_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.logs_text.configure(state="disabled")

        inner = self.logs_text._textbox  # type: ignore[attr-defined]  # tk.Text real
        for level, color in LEVEL_COLORS.items():
            inner.tag_configure(level, foreground=color)  # type: ignore[no-untyped-call]
        inner.tag_configure("TIMESTAMP", foreground=PALETTE.text_secondary)  # type: ignore[no-untyped-call]
        inner.tag_configure("MATCH", background="#3a4b6b")  # type: ignore[no-untyped-call]

    # ---------------------------------------------------------------- pagina config
    def _build_page_config(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_container, fg_color=PALETTE.bg_main)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            page,
            fg_color=PALETTE.bg_main,
            label_text="",
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        self.config_fields: dict[str, tk.StringVar] = {}
        self.config_widgets: dict[str, ctk.CTkBaseClass] = {}

        secoes = [
            (
                "Caminhos locais",
                "",
                [
                    ("XLSX_PATH", "Planilha de clientes", "path"),
                    ("PASTA_CERTS", "Pasta de certificados", "dir"),
                    ("PASTA_SAIDA", "Pasta de saida", "dir"),
                    ("CHROME_USER_DATA_DIR", "Perfil Chrome", "dir"),
                    ("CHROME_EXTENSION_DIR", "Pasta da extensao", "dir"),
                ],
            ),
            (
                "Portal NFSe / Playwright",
                "",
                [
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
            ),
            (
                "Seletores e extensao",
                "",
                [
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
            ),
            (
                "E-mail (Zoho SMTP)",
                "",
                [
                    ("ZOHO_SMTP_HOST", "Host SMTP", "text"),
                    ("ZOHO_SMTP_PORT", "Porta SMTP", "int"),
                    ("ZOHO_SMTP_USER", "Usuario", "text"),
                    ("ZOHO_SMTP_PASSWORD", "Senha", "secret"),
                    ("ZOHO_EMAIL_FROM", "Remetente", "text"),
                    ("ZOHO_EMAIL_TO", "Destinatario(s)", "text"),
                ],
            ),
        ]

        row = 0
        for titulo, icone, campos in secoes:
            section = ctk.CTkFrame(
                scroll,
                fg_color=PALETTE.bg_panel,
                corner_radius=14,
                border_width=1,
                border_color=PALETTE.border,
            )
            section.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            section.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                section,
                text=titulo,
                font=ctk.CTkFont(family=UI_FONT_HEADING, size=14, weight="bold"),
                text_color=PALETTE.text_primary,
                anchor="w",
            ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 8))

            for i, (chave, label, tipo) in enumerate(campos, start=1):
                ctk.CTkLabel(
                    section,
                    text=label,
                    font=ctk.CTkFont(family=UI_FONT, size=11),
                    text_color=PALETTE.text_secondary,
                    anchor="w",
                    width=180,
                ).grid(row=i, column=0, sticky="w", padx=(16, 8), pady=4)

                var = tk.StringVar(value=str(getattr(config, chave, "")))
                self.config_fields[chave] = var

                entry = ctk.CTkEntry(
                    section,
                    textvariable=var,
                    fg_color=PALETTE.bg_card,
                    border_color=PALETTE.border,
                    height=32,
                    font=ctk.CTkFont(family=UI_FONT, size=11),
                    show="•" if tipo == "secret" else None,
                )
                entry.grid(row=i, column=1, sticky="ew", padx=8, pady=4)
                self.config_widgets[chave] = entry

                if tipo in ("path", "dir"):
                    ctk.CTkButton(
                        section,
                        text="…",
                        width=32,
                        height=32,
                        fg_color="transparent",
                        border_width=1,
                        border_color=PALETTE.border,
                        text_color=PALETTE.text_secondary,
                        hover_color=PALETTE.bg_card,
                        command=lambda k=chave, t=tipo: self._browse_path(k, t),
                    ).grid(row=i, column=2, sticky="e", padx=(0, 16), pady=4)
                elif tipo == "secret":
                    ctk.CTkButton(
                        section,
                        text="Ver",
                        width=32,
                        height=32,
                        fg_color="transparent",
                        border_width=1,
                        border_color=PALETTE.border,
                        text_color=PALETTE.text_secondary,
                        hover_color=PALETTE.bg_card,
                        command=lambda e=entry: self._toggle_secret(e),
                    ).grid(row=i, column=2, sticky="e", padx=(0, 16), pady=4)

            ctk.CTkFrame(section, fg_color="transparent", height=8).grid(
                row=len(campos) + 1, column=0, columnspan=3
            )
            row += 1

        # rodape
        footer = ctk.CTkFrame(scroll, fg_color="transparent")
        footer.grid(row=row, column=0, sticky="ew", pady=(4, 20))

        ctk.CTkButton(
            footer,
            text="Salvar alteracoes",
            command=self._salvar_config,
            height=40,
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=13, weight="bold"),
            fg_color=PALETTE.success,
            hover_color="#27ae60",
            corner_radius=10,
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            text="Recarregar do disco",
            command=self._recarregar_config,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            corner_radius=10,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            footer,
            text="Abrir no editor",
            command=self._abrir_config,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=PALETTE.border,
            text_color=PALETTE.text_secondary,
            hover_color=PALETTE.bg_card,
            corner_radius=10,
        ).pack(side="left", padx=(8, 0))

        return page

    # ---------------------------------------------------------------- pagina sobre
    def _build_page_sobre(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_container, fg_color=PALETTE.bg_main)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(
            page,
            fg_color=PALETTE.bg_panel,
            corner_radius=18,
            border_width=1,
            border_color=PALETTE.border,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=120, pady=60)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="NFSe",
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=34, weight="bold"),
        ).pack(pady=(40, 4))

        ctk.CTkLabel(
            card,
            text=APP_TITLE,
            font=ctk.CTkFont(family=UI_FONT_HEADING, size=24, weight="bold"),
            text_color=PALETTE.text_primary,
        ).pack()

        ctk.CTkLabel(
            card,
            text=f"Versão {APP_VERSION}",
            font=ctk.CTkFont(family=UI_FONT, size=13),
            text_color=PALETTE.text_secondary,
        ).pack(pady=(0, 20))

        info = (
            "Automatiza o download de NFSe para multiplos clientes\n"
            "via Playwright local, sem dependencia de API externa.\n\n"
            "(c) CONX Contabilidade"
        )
        ctk.CTkLabel(
            card,
            text=info,
            font=ctk.CTkFont(family=UI_FONT, size=12),
            text_color=PALETTE.text_secondary,
            justify="center",
        ).pack(pady=(0, 20))

        diag = ctk.CTkFrame(card, fg_color=PALETTE.bg_card, corner_radius=10)
        diag.pack(padx=40, pady=(0, 30), fill="x")

        diag_texto = (
            f"Python          {sys.version.split()[0]}\n"
            f"Portal NFSe     {getattr(config, 'NFSE_LOGIN_URL', '-')}\n"
            f"Extensao        {getattr(config, 'CHROME_EXTENSION_DIR', '-')}\n"
            f"Pasta de saida  {getattr(config, 'PASTA_SAIDA', '-')}\n"
            f"Data atual      {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        ctk.CTkLabel(
            diag,
            text=diag_texto,
            font=ctk.CTkFont(family=UI_FONT_MONO, size=11),
            text_color=PALETTE.text_secondary,
            justify="left",
            anchor="w",
        ).pack(padx=18, pady=14, anchor="w")

        return page

    # ----------------------------------------------------------------- helpers UI
    def _periodo_padrao_str(self) -> str:
        hoje = date.today()
        if hoje.month == 1:
            mes, ano = 12, hoje.year - 1
        else:
            mes, ano = hoje.month - 1, hoje.year
        return f"{mes:02d}/{ano}"

    def _show_page(self, name: str) -> None:
        if name not in self.pages:
            return
        self.pages[name].tkraise()
        self.current_page = name
        for key, btn in self.nav_buttons.items():
            btn.set_active(key == name)
        titles = {"executar": "Executar", "config": "Configurações", "sobre": "Sobre"}
        self.page_title_var.set(titles.get(name, name))
        try:
            self.transition_bar.play()
        except Exception:  # noqa: BLE001
            pass

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode("dark" if value == "Escuro" else "light")  # type: ignore[no-untyped-call]

    def _toggle_data_entries(self) -> None:
        if self.usar_mes_anterior.get():
            self.data_inicio_entry.configure(state="disabled")
            self.data_fim_entry.configure(state="disabled")
            self.card_periodo.set_value(self._periodo_padrao_str())
        else:
            self.data_inicio_entry.configure(state="normal")
            self.data_fim_entry.configure(state="normal")
            self._atualizar_card_periodo()

    def _atualizar_card_periodo(self) -> None:
        try:
            ini = self.data_inicio_entry.get_date().strftime("%d/%m/%Y")
            fim = self.data_fim_entry.get_date().strftime("%d/%m/%Y")
            self.card_periodo.set_value(f"{ini} → {fim}")
        except Exception:  # noqa: BLE001
            self.card_periodo.set_value("-")

    def _update_cnpj_card(self) -> None:
        raw = self.cnpjs_text.get("1.0", "end").strip()
        if not raw:
            self.card_cnpjs.set_value("Todos")
            return
        partes = [p for p in re.split(r"[\s,;]+", raw) if p]
        self.card_cnpjs.set_value(f"{len(partes)} CNPJ(s)")

    def _toggle_secret(self, entry: ctk.CTkEntry) -> None:
        current = entry.cget("show")
        entry.configure(show="" if current else "•")

    def _browse_path(self, chave: str, tipo: str) -> None:
        from tkinter import filedialog

        var = self.config_fields[chave]
        atual = var.get()
        if tipo == "dir":
            value = filedialog.askdirectory(
                parent=self,
                initialdir=atual if atual and Path(atual).exists() else None,
                title="Selecione a pasta",
            )
        else:
            value = filedialog.askopenfilename(
                parent=self,
                initialdir=str(Path(atual).parent) if atual else None,
                title="Selecione o arquivo",
                filetypes=[("Planilhas", "*.xlsx *.xls"), ("Todos", "*.*")],
            )
        if value:
            var.set(value)

    # ----------------------------------------------------------------- logs
    def _configure_logging(self) -> None:
        self.log_handler = QueueLogHandler(self.log_queue)
        self.log_handler.setLevel(logging.INFO)
        self.log_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)
        logging.getLogger("nfse.gui").info("Painel de logs inicializado.")
        self.after(150, lambda: self._append_log_direct("Interface pronta para uso.", "INFO"))

    # Limite de linhas no painel para nao degradar a UI em execucoes longas.
    _MAX_LOG_LINES = 5000
    # Quantas linhas podar de uma vez quando ultrapassar o limite (evita poda a cada tick).
    _LOG_TRIM_CHUNK = 500

    def _drain_log_queue(self) -> None:
        """Consome toda a fila num unico tick e renderiza em lote."""
        chunks: list[tuple[str, str]] = []
        try:
            while True:
                record = self.log_queue.get_nowait()
                if not self._log_passes_filter(record):
                    continue
                msg = self.log_handler.format(record)
                if self._log_search and self._log_search.lower() not in msg.lower():
                    continue
                chunks.append((msg, record.levelname))
        except queue.Empty:
            pass
        except Exception as exc:  # noqa: BLE001
            chunks.append((f"Falha ao processar log: {exc}", "ERROR"))

        if chunks:
            self._flush_log_chunks(chunks)
        self.after(120, self._drain_log_queue)

    def _log_passes_filter(self, record: logging.LogRecord) -> bool:
        if self._log_filter_level == "ALL":
            return True
        if self._log_filter_level == "INFO":
            return record.levelno >= logging.INFO
        return record.levelname == self._log_filter_level

    def _flush_log_chunks(self, chunks: list[tuple[str, str]]) -> None:
        """
        Aplica um lote de mensagens no textbox com um unico toggle de estado
        e uma unica chamada a see("end"). Poda linhas antigas se passar do limite.
        """
        inner = self.logs_text._textbox  # type: ignore[attr-defined]
        self.logs_text.configure(state="normal")
        for msg, levelname in chunks:
            ts_end = msg.find("  ")
            if ts_end > 0:
                inner.insert("end", msg[: ts_end + 2], "TIMESTAMP")
                inner.insert("end", msg[ts_end + 2 :] + "\n", levelname)
            else:
                inner.insert("end", msg + "\n", levelname)

        # Poda em bloco: a ultima linha vazia do Text nao conta.
        total_lines = int(inner.index("end-1c").split(".")[0])
        if total_lines > self._MAX_LOG_LINES + self._LOG_TRIM_CHUNK:
            excesso = total_lines - self._MAX_LOG_LINES
            inner.delete("1.0", f"{excesso + 1}.0")

        self.logs_text.configure(state="disabled")
        inner.see("end")

    def _append_log_direct(self, message: str, levelname: str = "INFO") -> None:
        """Insere uma linha direto no painel (fallback, sem passar pela fila)."""
        now = datetime.now().strftime("%H:%M:%S")
        linha = f"{now}  {levelname:<8}  nfse.gui  {message}"
        self._flush_log_chunks([(linha, levelname)])

    def _limpar_logs(self) -> None:
        self.logs_text.configure(state="normal")
        self.logs_text._textbox.delete("1.0", "end")  # type: ignore[attr-defined]
        self.logs_text.configure(state="disabled")

    def _copiar_logs(self) -> None:
        conteudo = self.logs_text._textbox.get("1.0", "end").strip()  # type: ignore[attr-defined]
        if not conteudo:
            return
        self.clipboard_clear()
        self.clipboard_append(conteudo)
        self.statusbar_var.set("Logs copiados para a área de transferência.")

    def _set_log_filter(self, level: str) -> None:
        self._log_filter_level = level

    def _on_log_search(self) -> None:
        self._log_search = self.log_search_entry.get().strip()

    def _on_cancelar(self) -> None:
        if not self.running:
            return
        if self.cancel_event:
            self.cancel_event.set()
        logging.getLogger("nfse.gui").warning("Cancelamento solicitado pelo usuario.")
        self.card_status.set_value("Cancelando...")
        self.card_status.value_label.configure(text_color=PALETTE.warning)
        self.card_status.set_accent_color(PALETTE.warning)
        self.topbar_status.configure(text="Cancelando", text_color=PALETTE.warning)
        self.status_badge.set_color(PALETTE.warning)
        self.statusbar_var.set("Cancelando execucao em andamento...")
        self.cancelar_btn.configure(state="disabled")

    def _on_contar_certificados(self) -> None:
        if self.running:
            return
        self._show_page("executar")
        self.statusbar_var.set("Contando certificados...")
        threading.Thread(
            target=self._contar_certificados_worker,
            daemon=True,
        ).start()

    def _contar_certificados_worker(self) -> None:
        logger = logging.getLogger("nfse.gui")
        try:
            pasta_raw = str(getattr(config, "PASTA_CERTS", "")).strip()
            if not pasta_raw:
                raise ValueError("PASTA_CERTS nao configurada.")

            pasta = Path(pasta_raw)
            if not pasta.exists():
                raise FileNotFoundError(f"Pasta nao encontrada: {pasta}")
            if not pasta.is_dir():
                raise NotADirectoryError(f"Caminho nao e uma pasta: {pasta}")

            certs = listar_certificados(pasta)
            mapa_unico, duplicados = indexar_certificados_por_cnpj(certs)
            validos = [cert for cert in certs if not cert.erro]
            ok = len(validos)
            erro = len(certs) - ok
            ecnpj = sum(1 for cert in validos if len(cert.documento) == 14)
            ecpf = sum(1 for cert in validos if len(cert.documento) == 11)
            sem_doc = sum(1 for cert in validos if len(cert.documento) not in (11, 14))
            duplicados_arquivos = sum(len(itens) for itens in duplicados.values())

            logger.info("Pasta de certificados: %s", pasta)
            logger.info(
                "Tipos certificados: a1_arquivos=%d | e_cnpj=%d | e_cpf=%d | sem_doc=%d",
                len(certs),
                ecnpj,
                ecpf,
                sem_doc,
            )
            logger.info(
                "Resumo certificados: total=%d | ok=%d | erro=%d | cnpjs_unicos=%d | cnpjs_duplicados=%d | arquivos_duplicados=%d",
                len(certs),
                ok,
                erro,
                len(mapa_unico),
                len(duplicados),
                duplicados_arquivos,
            )

            if erro:
                for cert in [c for c in certs if c.erro][:10]:
                    logger.warning("Certificado com erro: %s | %s", cert.arquivo.name, cert.erro)

            self.after(
                0,
                lambda: self.statusbar_var.set(
                    f"A1: {len(certs)} | e-CNPJ: {ecnpj} | e-CPF: {ecpf} | erros: {erro}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao contar certificados: %s", exc)
            self.after(0, lambda: self.statusbar_var.set("Falha ao contar certificados."))

    # ----------------------------------------------------------------- execucao
    def _parse_cnpjs(self) -> list[str] | None:
        raw = self.cnpjs_text.get("1.0", "end").strip()
        if not raw:
            return None
        partes = [p for p in re.split(r"[\s,;]+", raw) if p]
        cnpjs: list[str] = []
        invalidos: list[str] = []
        for parte in partes:
            somente = re.sub(r"\D", "", parte)
            if len(somente) == 14:
                cnpjs.append(somente)
            else:
                invalidos.append(parte)
        if invalidos:
            raise ValueError(
                f"CNPJ inválido: {', '.join(invalidos[:3])}. "
                "Use somente CNPJs com 14 dígitos."
            )
        return cnpjs or None

    def _on_executar(self) -> None:
        if self.running:
            return
        try:
            if self.usar_mes_anterior.get():
                data_inicio = None
                data_fim = None
            else:
                data_inicio = self.data_inicio_entry.get_date().strftime("%d/%m/%Y")
                data_fim = self.data_fim_entry.get_date().strftime("%d/%m/%Y")
                inicio_dt = datetime.strptime(data_inicio, "%d/%m/%Y")
                fim_dt = datetime.strptime(data_fim, "%d/%m/%Y")
                if inicio_dt > fim_dt:
                    raise ValueError("Data início não pode ser maior que data fim.")
                self._atualizar_card_periodo()
            cnpjs = self._parse_cnpjs()
        except ValueError as exc:
            messagebox.showerror("Validação", str(exc), parent=self)
            return

        self.cancel_event = threading.Event()
        self._set_running(True)
        self._show_page("executar")
        self.card_status.set_value("Executando")
        self.card_status.value_label.configure(text_color=PALETTE.accent)
        self.card_status.set_accent_color(PALETTE.accent)
        self.card_ultima.set_value(datetime.now().strftime("%d/%m %H:%M"))
        self.statusbar_var.set("Execução em andamento...")
        self.topbar_status.configure(text="Executando", text_color=PALETTE.accent)
        self.status_badge.set_color(PALETTE.accent)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.exec_spinner.pack(side="left", padx=(10, 0))
        self.exec_spinner.start()
        self.executar_btn.stop_glow()
        self.toasts.show(
            "Execução iniciada",
            "Processando portal NFSe em segundo plano.",
            kind="info",
            duration_ms=2800,
        )
        logging.getLogger("nfse.gui").info("Execução iniciada pela interface gráfica.")

        threading.Thread(
            target=self._run_automacao,
            args=(data_inicio, data_fim, cnpjs),
            daemon=True,
        ).start()

    def _run_automacao(
        self,
        data_inicio: str | None,
        data_fim: str | None,
        cnpjs: list[str] | None,
    ) -> None:
        resultado = "ok"
        try:
            self._contar_certificados_worker()
            if self.cancel_event and self.cancel_event.is_set():
                raise ExecucaoCancelada("Cancelada antes do inicio da automacao.")
            executar(
                data_inicio=data_inicio,
                data_fim=data_fim,
                cnpjs=cnpjs,
                cancel_event=self.cancel_event,
            )
        except ExecucaoCancelada:
            resultado = "cancelado"
            logging.getLogger("nfse.gui").warning("Execucao cancelada pelo usuario.")
        except Exception:  # noqa: BLE001
            resultado = "erro"
            logging.getLogger("nfse.gui").exception("Erro inesperado na execucao.")
        finally:
            self.after(0, lambda r=resultado: self._on_execucao_finalizada(r))

    def _on_execucao_finalizada(self, resultado: str) -> None:
        self._set_running(False)
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.cancel_event = None
        self.exec_spinner.stop()
        self.exec_spinner.pack_forget()
        self.executar_btn.start_glow(base=PALETTE.accent, peak=PALETTE.success)

        if resultado == "ok":
            self.progress.set(1)
            self.card_status.set_value("Concluido")
            self.card_status.value_label.configure(text_color=PALETTE.success)
            self.card_status.set_accent_color(PALETTE.success)
            self.topbar_status.configure(text="Pronto", text_color=PALETTE.success)
            self.status_badge.set_color(PALETTE.success)
            self.statusbar_var.set("Execucao finalizada.")
            self.toasts.show(
                "Execução concluída",
                "Todos os certificados foram processados.",
                kind="success",
                duration_ms=4200,
            )
        elif resultado == "cancelado":
            self.progress.set(0)
            self.card_status.set_value("Cancelado")
            self.card_status.value_label.configure(text_color=PALETTE.warning)
            self.card_status.set_accent_color(PALETTE.warning)
            self.topbar_status.configure(text="Cancelado", text_color=PALETTE.warning)
            self.status_badge.set_color(PALETTE.warning)
            self.statusbar_var.set("Execucao cancelada.")
            self.toasts.show(
                "Execução cancelada",
                "Cancelada pelo usuário antes do término.",
                kind="warning",
                duration_ms=3600,
            )
        else:
            self.progress.set(0)
            self.card_status.set_value("Erro")
            self.card_status.value_label.configure(text_color=PALETTE.danger)
            self.card_status.set_accent_color(PALETTE.danger)
            self.topbar_status.configure(text="Erro", text_color=PALETTE.danger)
            self.status_badge.set_color(PALETTE.danger)
            self.statusbar_var.set("Execucao finalizada com erro.")
            self.toasts.show(
                "Falha na execução",
                "Confira o painel de logs para detalhes.",
                kind="error",
                duration_ms=5000,
            )

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.executar_btn.configure(
            state="disabled" if running else "normal",
            text="Executando..." if running else "Executar agora",
        )
        self.cancelar_btn.configure(state="normal" if running else "disabled")
        self.contar_certs_btn.configure(state="disabled" if running else "normal")
        self.sw_mes_anterior.configure(state="disabled" if running else "normal")
        if running:
            self.data_inicio_entry.configure(state="disabled")
            self.data_fim_entry.configure(state="disabled")
            self.cnpjs_text.configure(state="disabled")
        else:
            self._toggle_data_entries()
            self.cnpjs_text.configure(state="normal")

    # ----------------------------------------------------------------- config
    def _salvar_config(self) -> None:
        if not CONFIG_PATH.exists():
            messagebox.showerror("Erro", "config.py não encontrado.", parent=self)
            return

        original = CONFIG_PATH.read_text(encoding="utf-8")
        novo = original
        try:
            for chave, var in self.config_fields.items():
                valor = var.get()
                atual = getattr(config, chave, "")
                if isinstance(atual, bool):
                    literal = "True" if valor.strip().lower() in ("true", "1", "sim") else "False"
                elif isinstance(atual, int) and not isinstance(atual, bool):
                    int(valor)  # valida
                    literal = valor.strip()
                else:
                    literal = self._python_string_literal(valor)

                novo = self._replace_config_assignment(novo, chave, literal)
        except ValueError as exc:
            messagebox.showerror("Validação", f"Valor inválido: {exc}", parent=self)
            return

        backup = CONFIG_PATH.with_suffix(".py.bak")
        backup.write_text(original, encoding="utf-8")
        CONFIG_PATH.write_text(novo, encoding="utf-8")

        try:
            import importlib
            importlib.reload(config)
        except Exception:  # noqa: BLE001
            pass

        self.statusbar_var.set(f"Configurações salvas. Backup: {backup.name}")
        messagebox.showinfo(
            "Configurações",
            "Configurações salvas com sucesso.\nUm backup foi gerado em config.py.bak.",
            parent=self,
        )

    def _recarregar_config(self) -> None:
        try:
            import importlib
            importlib.reload(config)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Erro", f"Falha ao recarregar: {exc}", parent=self)
            return
        for chave, var in self.config_fields.items():
            var.set(str(getattr(config, chave, "")))
        self.statusbar_var.set("Configurações recarregadas do disco.")

    @staticmethod
    def _python_string_literal(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'r"{value}"' if ("\\" in value and '"' not in value) else f'"{escaped}"'

    @staticmethod
    def _replace_config_assignment(source: str, chave: str, literal: str) -> str:
        pattern = re.compile(
            rf"^(?P<prefix>{re.escape(chave)}\s*=\s*)(?P<value>.+?)(?P<suffix>\s*(?:#.*)?)$",
            re.MULTILINE,
        )

        def repl(m: re.Match[str]) -> str:
            return f"{m.group('prefix')}{literal}{m.group('suffix')}"

        novo, n = pattern.subn(repl, source, count=1)
        if n == 0:
            novo = source.rstrip() + f"\n{chave} = {literal}\n"
        return novo

    def _abrir_config(self) -> None:
        if not CONFIG_PATH.exists():
            messagebox.showerror("Erro", "config.py não encontrado.", parent=self)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(CONFIG_PATH))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(CONFIG_PATH)], check=False)
            else:
                subprocess.run(["xdg-open", str(CONFIG_PATH)], check=False)
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível abrir: {exc}", parent=self)

    def _abrir_pasta_saida(self) -> None:
        pasta = Path(getattr(config, "PASTA_SAIDA", ""))
        if not pasta.exists():
            messagebox.showwarning(
                "Pasta não encontrada",
                f"A pasta de saída não existe:\n{pasta}",
                parent=self,
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(pasta))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(pasta)], check=False)
            else:
                subprocess.run(["xdg-open", str(pasta)], check=False)
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível abrir: {exc}", parent=self)

    # ----------------------------------------------------------------- close
    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno(
                "Confirmar",
                "Uma execução está em andamento. Deseja realmente sair?",
                parent=self,
            ):
                return
            if self.cancel_event:
                self.cancel_event.set()
        logging.getLogger().removeHandler(self.log_handler)
        self.destroy()


def main() -> None:
    app = NFSEGuiApp()
    app.mainloop()


if __name__ == "__main__":
    # Necessario para que ProcessPoolExecutor nao re-abra a GUI nos workers
    # quando o app esta empacotado pelo PyInstaller (cada worker spawn reexecuta o .exe).
    import multiprocessing

    multiprocessing.freeze_support()
    main()
