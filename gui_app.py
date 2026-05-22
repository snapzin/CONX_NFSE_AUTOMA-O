"""
gui_app.py - Interface principal da Automação NFSe.

Layout:
  Header (preto)  →  Stats (3 cards)  →  Controle Central  →
  Duas colunas (Configurações Rápidas | Logs)  →  Rodapé
"""
from __future__ import annotations

import sys
from pathlib import Path as _Path

# Quando empacotado pelo PyInstaller, garante que config.py
# seja lido da pasta do exe (não do bundle interno).
if getattr(sys, "frozen", False):
    _app_dir = str(_Path(sys.executable).parent)
    if _app_dir not in sys.path:
        sys.path.insert(0, _app_dir)

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk

import customtkinter as ctk
from tkcalendar import DateEntry

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

APP_TITLE  = "NFSe Automação"
APP_VER    = "2.4"
CONFIG_PATH = Path(__file__).resolve().with_name("config.py")
STATS_PATH  = Path(__file__).resolve().with_name("runtime_settings.json")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

if sys.platform == "darwin":
    FONT      = "Helvetica Neue"
    FONT_BOLD = "Helvetica Neue Bold"
    FONT_MONO = "Menlo"
else:
    FONT      = "Bahnschrift"
    FONT_BOLD = "Bahnschrift SemiBold"
    FONT_MONO = "Consolas"

# ── Paleta preto / branco / azul escuro ──────────────────────────────────────
@dataclass(frozen=True)
class Palette:
    header:        str = "#000000"
    bg_app:        str = "#09111E"
    bg_section:    str = "#0D1B2E"
    bg_card:       str = "#0F2040"
    accent:        str = "#0C447C"
    accent_hover:  str = "#0D5499"
    accent_light:  str = "#1565C0"
    badge_bg:      str = "#0C2D52"
    success:       str = "#22C55E"
    warning:       str = "#F59E0B"
    danger:        str = "#EF4444"
    text_primary:  str = "#FFFFFF"
    text_secondary:str = "#94A3B8"
    border:        str = "#1B3050"
    log_bg:        str = "#060E1A"

P = Palette()

LOG_COLORS = {
    "DEBUG":    "#64748B",
    "INFO":     "#CBD5E1",
    "WARNING":  "#F59E0B",
    "ERROR":    "#EF4444",
    "CRITICAL": "#FF3860",
    "OK":       "#22C55E",
}

TIPS = [
    "Configure PASTA_CERTS em Configurações antes de iniciar.",
    "A extensão 'Baixar NFSe' deve estar instalada no Chrome.",
    "Atalho Ctrl+Enter inicia a automação de qualquer página.",
    "Ative 'Importar no Domínio Web' para automatizar o lançamento fiscal.",
    "Use Ctrl+L para limpar os logs a qualquer momento.",
    "O atalho da extensão padrão é Ctrl+Shift+Y — verifique em chrome://extensions/shortcuts.",
]

# ── Handler de logs ──────────────────────────────────────────────────────────
class QueueLogHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[logging.LogRecord]") -> None:
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(record)


# ── Helpers de stats persistidas ─────────────────────────────────────────────
def _load_stats() -> dict:
    try:
        if STATS_PATH.exists():
            data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_stats(patch: dict) -> None:
    data = _load_stats()
    data.update(patch)
    try:
        STATS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# Janela principal
# ═════════════════════════════════════════════════════════════════════════════
class NFSEGuiApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} — v{APP_VER}")
        self.geometry("1140x820")
        self.minsize(920, 660)
        self.configure(fg_color=P.bg_app)

        self.log_queue: queue.Queue[logging.LogRecord] = queue.Queue()
        self.running   = False
        self.cancel_ev: threading.Event | None = None
        self._tip_idx  = 0
        self._log_filter = "ALL"

        # stats acumuladas
        s = _load_stats()
        self._stat_empresas = s.get("total_empresas", 0)
        self._stat_horas    = s.get("horas_economizadas", 0.0)
        self._stat_sucesso  = s.get("taxa_sucesso", 0)

        self._build_ui()
        self._setup_logging()
        self._poll_logs()
        self._rotate_tip()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-Return>", lambda _: self._on_run())
        self.bind("<Control-l>",      lambda _: self._clear_logs())

        self.toasts = ToastManager(
            self,
            palette={
                "bg": P.bg_card, "border": P.border,
                "text": P.text_primary, "text_secondary": P.text_secondary,
                "accent_info": P.accent_light, "accent_success": P.success,
                "accent_warning": P.warning,   "accent_error": P.danger,
            },
            font_family=FONT,
        )
        self.after(60, self._show_splash)

    # ── Splash ────────────────────────────────────────────────────────────────
    def _show_splash(self) -> None:
        s = SplashOverlay(
            self,
            title=APP_TITLE,
            subtitle=f"v{APP_VER}  ·  pronto para processar",
            bg=P.bg_app, accent=P.accent_light,
            text_primary=P.text_primary, text_secondary=P.text_secondary,
            font_heading=FONT_BOLD, font=FONT,
        )
        s.play(900, on_done=lambda: self.toasts.show(
            "Interface pronta",
            "Configure o período e clique em Iniciar.",
            kind="info", duration_ms=3200,
        ))

    # ── Construção da UI ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # Páginas empilhadas
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._page_main   = self._make_main_page()
        self._page_config = self._make_config_page()
        self._page_sobre  = self._make_sobre_page()

        for p in (self._page_main, self._page_config, self._page_sobre):
            p.grid(row=0, column=0, sticky="nsew")

        self._page_main.tkraise()
        self._current_page = "main"

    # ══════════════════════════════════════════════════════════════════════════
    # PÁGINA PRINCIPAL
    # ══════════════════════════════════════════════════════════════════════════
    def _make_main_page(self) -> ctk.CTkFrame:
        root = ctk.CTkScrollableFrame(self, fg_color=P.bg_app, scrollbar_button_color=P.border)
        root.grid_columnconfigure(0, weight=1)

        self._build_header(root)
        self._build_stats(root)
        self._build_control(root)
        self._build_bottom(root)
        self._build_footer(root)

        return root

    # ── 1. HEADER ─────────────────────────────────────────────────────────────
    def _build_header(self, parent: ctk.CTkScrollableFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color=P.header, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        # Logo + nome
        logo_box = ctk.CTkFrame(header, fg_color="transparent")
        logo_box.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        accent_bar = ctk.CTkFrame(logo_box, fg_color=P.accent, width=4, corner_radius=2)
        accent_bar.pack(side="left", fill="y", padx=(0, 10))

        name_box = ctk.CTkFrame(logo_box, fg_color="transparent")
        name_box.pack(side="left")
        ctk.CTkLabel(
            name_box, text=APP_TITLE,
            font=ctk.CTkFont(family=FONT_BOLD, size=18, weight="bold"),
            text_color=P.text_primary,
        ).pack(anchor="w")
        ctk.CTkLabel(
            name_box, text=f"v{APP_VER}  ·  CONX Contabilidade",
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=P.text_secondary,
        ).pack(anchor="w")

        # Botões direita
        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.grid(row=0, column=2, sticky="e", padx=16, pady=12)

        def _hbtn(text: str, cmd, accent: bool = False) -> ctk.CTkButton:
            return ctk.CTkButton(
                btn_box, text=text, command=cmd,
                height=34, width=110,
                font=ctk.CTkFont(family=FONT, size=12),
                fg_color=P.accent if accent else "transparent",
                hover_color=P.accent_hover if accent else P.bg_card,
                border_width=0 if accent else 1,
                border_color=P.border,
                text_color=P.text_primary,
                corner_radius=8,
            )

        # status badge no header
        self._hdr_badge_frame = ctk.CTkFrame(btn_box, fg_color="transparent")
        self._hdr_badge_frame.pack(side="left", padx=(0, 14))
        self._hdr_pulse = PulseBadge(self._hdr_badge_frame, color=P.success, size=12, bg=P.header)
        self._hdr_pulse.pack(side="left", padx=(0, 6))
        self._hdr_status_lbl = ctk.CTkLabel(
            self._hdr_badge_frame, text="Pronto",
            font=ctk.CTkFont(family=FONT_BOLD, size=12, weight="bold"),
            text_color=P.success,
        )
        self._hdr_status_lbl.pack(side="left")

        _hbtn("Configurações", lambda: self._nav("config")).pack(side="left", padx=4)
        _hbtn("Sobre",         lambda: self._nav("sobre")).pack(side="left", padx=4)

    # ── 2. STATS CARDS ────────────────────────────────────────────────────────
    def _build_stats(self, parent: ctk.CTkScrollableFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=24, pady=(20, 0))
        for i in range(3):
            row.grid_columnconfigure(i, weight=1, uniform="stat")

        kw = dict(
            bg_color=P.bg_card, bg_hover="#122848",
            border_color=P.border,
            text_primary=P.text_primary, text_secondary=P.text_secondary,
            font_heading=FONT_BOLD,
        )
        self._card_empresas = AnimatedStatCard(
            row, "Empresas Processadas",
            str(self._stat_empresas), P.accent_light, **kw,
        )
        self._card_empresas.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._card_horas = AnimatedStatCard(
            row, "Tempo Economizado",
            f"{self._stat_horas:.1f}h", P.accent_light, **kw,
        )
        self._card_horas.grid(row=0, column=1, sticky="ew", padx=8)

        self._card_sucesso = AnimatedStatCard(
            row, "Taxa de Sucesso",
            f"{self._stat_sucesso}%", P.accent_light, **kw,
        )
        self._card_sucesso.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    # ── 3. PAINEL CENTRAL DE CONTROLE ─────────────────────────────────────────
    def _build_control(self, parent: ctk.CTkScrollableFrame) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=P.bg_section,
            corner_radius=16,
            border_width=1, border_color=P.border,
        )
        card.grid(row=2, column=0, sticky="ew", padx=24, pady=16)
        card.grid_columnconfigure(0, weight=1)

        # Badge de status
        badge_row = ctk.CTkFrame(card, fg_color="transparent")
        badge_row.grid(row=0, column=0, pady=(18, 8))

        self._status_badge_bg = ctk.CTkFrame(
            badge_row,
            fg_color=P.badge_bg,
            corner_radius=20,
        )
        self._status_badge_bg.pack()
        self._status_dot = PulseBadge(
            self._status_badge_bg, color=P.success, size=10, bg=P.badge_bg,
        )
        self._status_dot.pack(side="left", padx=(14, 6), pady=8)
        self._status_txt = ctk.CTkLabel(
            self._status_badge_bg,
            text="Pronto para iniciar",
            font=ctk.CTkFont(family=FONT_BOLD, size=12, weight="bold"),
            text_color=P.success,
        )
        self._status_txt.pack(side="left", padx=(0, 14), pady=8)

        # Botão grande
        btn_area = ctk.CTkFrame(card, fg_color="transparent")
        btn_area.grid(row=1, column=0, pady=4)

        self._run_btn = GlowButton(
            btn_area,
            text="  Iniciar Automação  ",
            command=self._on_run,
            height=52,
            font=ctk.CTkFont(family=FONT_BOLD, size=16, weight="bold"),
            fg_color=P.accent,
            hover_color=P.accent_hover,
            border_color=P.accent,
            corner_radius=12,
            glow_color=P.accent_light,
        )
        self._run_btn.pack(side="left")
        self._run_btn.start_glow(base=P.accent, peak=P.accent_light)

        self._spinner = Spinner(btn_area, size=28, thickness=3, color=P.accent_light, bg=P.bg_section)

        self._cancel_btn = ctk.CTkButton(
            btn_area,
            text="Cancelar",
            command=self._on_cancel,
            height=52, width=130,
            font=ctk.CTkFont(family=FONT_BOLD, size=13, weight="bold"),
            fg_color=P.danger, hover_color="#B91C1C",
            corner_radius=12, state="disabled",
        )
        self._cancel_btn.pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            card,
            text="Baixa notas emitidas e recebidas para todos os CNPJs, depois importa no Domínio Web.",
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=P.text_secondary,
        ).grid(row=2, column=0, pady=(2, 12))

        # Barra de progresso
        self._progress = ctk.CTkProgressBar(
            card, height=6,
            progress_color=P.accent_light, fg_color=P.bg_card, corner_radius=4,
        )
        self._progress.grid(row=3, column=0, sticky="ew", padx=60, pady=(0, 8))
        self._progress.set(0)

        # Seletor de período
        sep = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep.grid(row=4, column=0, sticky="ew", padx=24, pady=(4, 12))

        periodo = ctk.CTkFrame(card, fg_color="transparent")
        periodo.grid(row=5, column=0, pady=(0, 16))

        self._use_prev_month = tk.BooleanVar(value=True)
        sw = ctk.CTkSwitch(
            periodo,
            text="Usar mês anterior automaticamente",
            variable=self._use_prev_month,
            onvalue=True, offvalue=False,
            command=self._toggle_dates,
            progress_color=P.accent_light,
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=P.text_secondary,
        )
        sw.pack(side="left", padx=(0, 20))

        date_style = dict(
            date_pattern="dd/mm/yyyy", locale="pt_BR", width=11,
            background=P.accent, foreground="white", borderwidth=0,
            font=(FONT, 11),
        )
        ctk.CTkLabel(
            periodo, text="Início:", font=ctk.CTkFont(family=FONT, size=11),
            text_color=P.text_secondary,
        ).pack(side="left")
        self._dt_start = DateEntry(periodo, **date_style)
        self._dt_start.pack(side="left", padx=(4, 14))

        ctk.CTkLabel(
            periodo, text="Fim:", font=ctk.CTkFont(family=FONT, size=11),
            text_color=P.text_secondary,
        ).pack(side="left")
        self._dt_end = DateEntry(periodo, **date_style)
        self._dt_end.pack(side="left", padx=(4, 0))

        self._toggle_dates()

    # ── 4. DUAS COLUNAS (Settings | Logs) ────────────────────────────────────
    def _build_bottom(self, parent: ctk.CTkScrollableFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=2)
        row.grid_rowconfigure(0, weight=1)

        self._build_settings_col(row)
        self._build_logs_col(row)

    def _build_settings_col(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=P.bg_section,
            corner_radius=14, border_width=1, border_color=P.border,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Configurações Rápidas",
            font=ctk.CTkFont(family=FONT_BOLD, size=13, weight="bold"),
            text_color=P.text_primary, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        sep = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        chk_kw = dict(
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=P.text_secondary,
            checkmark_color=P.accent_light,
            fg_color=P.accent,
        )

        # Notificações por e-mail
        self._chk_email = tk.BooleanVar(value=bool(getattr(config, "ZOHO_EMAIL_TO", "")))
        ctk.CTkCheckBox(
            card, text="Notificações por e-mail",
            variable=self._chk_email, **chk_kw,
        ).grid(row=2, column=0, sticky="w", padx=16, pady=4)

        # Importar no Domínio Web
        self._chk_dominio = tk.BooleanVar(
            value=bool(getattr(config, "DOMINIO_WEB_IMPORTAR", True))
        )
        ctk.CTkCheckBox(
            card, text="Importar no Domínio Web",
            variable=self._chk_dominio,
            command=self._on_dominio_toggle,
            **chk_kw,
        ).grid(row=3, column=0, sticky="w", padx=16, pady=4)

        # Modo debug (mostra browser)
        self._chk_debug = tk.BooleanVar(
            value=not bool(getattr(config, "PLAYWRIGHT_HEADLESS", False))
        )
        ctk.CTkCheckBox(
            card, text="Mostrar navegador (modo debug)",
            variable=self._chk_debug, **chk_kw,
        ).grid(row=4, column=0, sticky="w", padx=16, pady=4)

        sep2 = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep2.grid(row=5, column=0, sticky="ew", padx=16, pady=(10, 6))

        # Slider: intervalo entre empresas
        ctk.CTkLabel(
            card, text="Intervalo entre empresas",
            font=ctk.CTkFont(family=FONT_BOLD, size=11, weight="bold"),
            text_color=P.text_secondary, anchor="w",
        ).grid(row=6, column=0, sticky="w", padx=16, pady=(0, 4))

        self._slider_var = tk.IntVar(value=int(getattr(config, "PLAYWRIGHT_SLOW_MO_MS", 0) / 1000))
        slider_row = ctk.CTkFrame(card, fg_color="transparent")
        slider_row.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 6))
        slider_row.grid_columnconfigure(0, weight=1)

        ctk.CTkSlider(
            slider_row,
            from_=0, to=10,
            variable=self._slider_var,
            number_of_steps=10,
            progress_color=P.accent_light,
            button_color=P.accent_light,
            button_hover_color=P.accent,
        ).grid(row=0, column=0, sticky="ew")

        self._slider_lbl = ctk.CTkLabel(
            slider_row,
            text=f"{self._slider_var.get()}s",
            font=ctk.CTkFont(family=FONT_BOLD, size=11, weight="bold"),
            text_color=P.accent_light, width=32,
        )
        self._slider_lbl.grid(row=0, column=1, padx=(8, 0))
        self._slider_var.trace_add("write", lambda *_: self._slider_lbl.configure(
            text=f"{self._slider_var.get()}s"
        ))

        sep3 = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep3.grid(row=8, column=0, sticky="ew", padx=16, pady=(6, 8))

        # Botões de ação extras
        btn_kw = dict(
            font=ctk.CTkFont(family=FONT, size=11),
            fg_color="transparent", border_width=1, border_color=P.border,
            text_color=P.text_secondary, hover_color=P.bg_card,
            corner_radius=8, height=32,
        )
        ctk.CTkButton(
            card, text="Abrir pasta de saída",
            command=self._open_output, **btn_kw,
        ).grid(row=9, column=0, sticky="ew", padx=16, pady=3)
        ctk.CTkButton(
            card, text="Limpar logs (Ctrl+L)",
            command=self._clear_logs, **btn_kw,
        ).grid(row=10, column=0, sticky="ew", padx=16, pady=(3, 14))

        # CNPJs
        sep4 = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep4.grid(row=11, column=0, sticky="ew", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            card, text="CNPJs específicos (opcional)",
            font=ctk.CTkFont(family=FONT_BOLD, size=11, weight="bold"),
            text_color=P.text_secondary, anchor="w",
        ).grid(row=12, column=0, sticky="w", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            card, text="Deixe vazio para todos. Separe por vírgula ou linha.",
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=P.text_secondary, anchor="w", wraplength=260, justify="left",
        ).grid(row=13, column=0, sticky="w", padx=16)
        self._cnpjs_box = ctk.CTkTextbox(
            card, height=72,
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            fg_color=P.log_bg, border_color=P.border, border_width=1, corner_radius=8,
        )
        self._cnpjs_box.grid(row=14, column=0, sticky="ew", padx=16, pady=(4, 16))

    def _build_logs_col(self, parent: ctk.CTkFrame) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=P.bg_section,
            corner_radius=14, border_width=1, border_color=P.border,
        )
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        # Header dos logs
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        hdr.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            hdr, text="Logs em Tempo Real",
            font=ctk.CTkFont(family=FONT_BOLD, size=13, weight="bold"),
            text_color=P.text_primary,
        ).grid(row=0, column=0, sticky="w")

        self._log_filter_btn = ctk.CTkSegmentedButton(
            hdr,
            values=["ALL", "INFO", "ERRO"],
            command=self._set_log_filter,
            fg_color=P.bg_card,
            selected_color=P.accent,
            selected_hover_color=P.accent_hover,
            font=ctk.CTkFont(family=FONT, size=11),
        )
        self._log_filter_btn.set("ALL")
        self._log_filter_btn.grid(row=0, column=1, padx=(12, 0))

        ctk.CTkButton(
            hdr, text="Copiar",
            command=self._copy_logs,
            width=68, height=28,
            font=ctk.CTkFont(family=FONT, size=11),
            fg_color="transparent", border_width=1, border_color=P.border,
            text_color=P.text_secondary, hover_color=P.bg_card, corner_radius=6,
        ).grid(row=0, column=3, sticky="e")

        sep = ctk.CTkFrame(card, fg_color=P.border, height=1)
        sep.grid(row=1, column=0, sticky="ew", padx=14)

        # Área de texto dos logs
        self._logs_txt = ctk.CTkTextbox(
            card,
            fg_color=P.log_bg, border_width=0,
            font=ctk.CTkFont(family=FONT_MONO, size=11),
        )
        self._logs_txt.grid(row=2, column=0, sticky="nsew", padx=14, pady=(6, 12))
        self._logs_txt.configure(state="disabled")

        inner = self._logs_txt._textbox
        for lv, clr in LOG_COLORS.items():
            inner.tag_configure(lv, foreground=clr)
        inner.tag_configure("TS", foreground=P.text_secondary)

    # ── 5. RODAPÉ COM DICA ────────────────────────────────────────────────────
    def _build_footer(self, parent: ctk.CTkScrollableFrame) -> None:
        footer = ctk.CTkFrame(
            parent,
            fg_color=P.badge_bg,
            corner_radius=10,
            border_width=1, border_color=P.accent,
        )
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 20))
        footer.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            footer, text="💡",
            font=ctk.CTkFont(size=16), text_color=P.accent_light,
        ).grid(row=0, column=0, padx=(14, 6), pady=12)

        self._tip_lbl = ctk.CTkLabel(
            footer,
            text=TIPS[0],
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=P.text_secondary,
            anchor="w",
        )
        self._tip_lbl.grid(row=0, column=1, sticky="w", pady=12)

    # ══════════════════════════════════════════════════════════════════════════
    # PÁGINA CONFIGURAÇÕES
    # ══════════════════════════════════════════════════════════════════════════
    def _make_config_page(self) -> ctk.CTkFrame:
        root = ctk.CTkFrame(self, fg_color=P.bg_app)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # Mini-header
        hdr = ctk.CTkFrame(root, fg_color=P.header, height=56, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="← Configurações",
            font=ctk.CTkFont(family=FONT_BOLD, size=16, weight="bold"),
            text_color=P.text_primary,
        ).grid(row=0, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkButton(
            hdr, text="Voltar",
            command=lambda: self._nav("main"),
            height=34, width=90,
            font=ctk.CTkFont(family=FONT, size=12),
            fg_color="transparent", border_width=1, border_color=P.border,
            text_color=P.text_secondary, hover_color=P.bg_card, corner_radius=8,
        ).grid(row=0, column=2, padx=16, pady=12)

        # Conteúdo scrollável
        scroll = ctk.CTkScrollableFrame(root, fg_color=P.bg_app)
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        self._cfg_vars: dict[str, tk.StringVar] = {}

        sections = [
            ("Caminhos Locais", [
                ("PASTA_CERTS",        "Pasta de Certificados", "dir"),
                ("PASTA_SAIDA",        "Pasta de Saída",        "dir"),
                ("CHROME_USER_DATA_DIR","Perfil Chrome",        "dir"),
                ("CHROME_EXTENSION_DIR","Pasta da Extensão",   "dir"),
                ("XLSX_PATH",          "Planilha de Clientes",  "path"),
            ]),
            ("Portal NFSe / Playwright", [
                ("NFSE_LOGIN_URL",                  "URL de Login",          "text"),
                ("NFSE_EMITIDAS_URL",               "URL Notas Emitidas",    "text"),
                ("NFSE_RECEBIDAS_URL",              "URL Notas Recebidas",   "text"),
                ("NFSE_ATALHO_EXTENSAO",            "Atalho da Extensão",    "text"),
                ("AUTOSELECT_CERTIFICATE_PATTERNS", "AutoSelect Cert Patterns","text"),
                ("PLAYWRIGHT_LOGIN_TIMEOUT_S",      "Timeout Login (s)",     "int"),
                ("PLAYWRIGHT_DOWNLOAD_TIMEOUT_S",   "Timeout Download (s)",  "int"),
                ("PLAYWRIGHT_HEADLESS",             "Headless (True/False)", "text"),
            ]),
            ("Domínio Web", [
                ("DOMINIO_WEB_URL",    "URL Domínio Web",    "text"),
                ("DOMINIO_WEB_MODULO", "Módulo",             "text"),
                ("DOMINIO_WEB_IMPORTAR","Importar (True/False)","text"),
            ]),
            ("E-mail (Zoho SMTP)", [
                ("ZOHO_SMTP_HOST",     "Host SMTP",      "text"),
                ("ZOHO_SMTP_PORT",     "Porta",          "int"),
                ("ZOHO_SMTP_USER",     "Usuário",        "text"),
                ("ZOHO_SMTP_PASSWORD", "Senha",          "secret"),
                ("ZOHO_EMAIL_FROM",    "Remetente",      "text"),
                ("ZOHO_EMAIL_TO",      "Destinatário(s)","text"),
            ]),
        ]

        r = 0
        for titulo, campos in sections:
            sec = ctk.CTkFrame(
                scroll, fg_color=P.bg_section,
                corner_radius=12, border_width=1, border_color=P.border,
            )
            sec.grid(row=r, column=0, sticky="ew", pady=(0, 12))
            sec.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                sec, text=titulo,
                font=ctk.CTkFont(family=FONT_BOLD, size=13, weight="bold"),
                text_color=P.text_primary, anchor="w",
            ).grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 6))

            for i, (key, label, kind) in enumerate(campos, start=1):
                ctk.CTkLabel(
                    sec, text=label,
                    font=ctk.CTkFont(family=FONT, size=11),
                    text_color=P.text_secondary, anchor="w", width=200,
                ).grid(row=i, column=0, sticky="w", padx=(16, 8), pady=3)

                var = tk.StringVar(value=str(getattr(config, key, "")))
                self._cfg_vars[key] = var

                entry = ctk.CTkEntry(
                    sec, textvariable=var,
                    fg_color=P.bg_card, border_color=P.border, height=30,
                    font=ctk.CTkFont(family=FONT, size=11),
                    show="•" if kind == "secret" else None,
                )
                entry.grid(row=i, column=1, sticky="ew", padx=8, pady=3)

                if kind in ("dir", "path"):
                    ctk.CTkButton(
                        sec, text="…", width=30, height=30,
                        fg_color="transparent", border_width=1, border_color=P.border,
                        text_color=P.text_secondary, hover_color=P.bg_card,
                        command=lambda k=key, t=kind: self._browse(k, t),
                    ).grid(row=i, column=2, padx=(0, 16), pady=3)
                elif kind == "secret":
                    ctk.CTkButton(
                        sec, text="ver", width=30, height=30,
                        fg_color="transparent", border_width=1, border_color=P.border,
                        text_color=P.text_secondary, hover_color=P.bg_card,
                        command=lambda e=entry: e.configure(show="" if e.cget("show") else "•"),
                    ).grid(row=i, column=2, padx=(0, 16), pady=3)

            ctk.CTkFrame(sec, fg_color="transparent", height=6).grid(
                row=len(campos) + 1, column=0, columnspan=3
            )
            r += 1

        # Botões de salvar
        save_row = ctk.CTkFrame(scroll, fg_color="transparent")
        save_row.grid(row=r, column=0, sticky="ew", pady=(4, 20))
        for text, cmd, clr, hov in [
            ("Salvar alterações",    self._save_config,   P.success,  "#16A34A"),
            ("Recarregar do disco",  self._reload_config, "transparent", P.bg_card),
            ("Abrir no editor",      self._open_config,   "transparent", P.bg_card),
        ]:
            ctk.CTkButton(
                save_row, text=text, command=cmd,
                height=38, fg_color=clr, hover_color=hov,
                border_width=0 if clr not in ("transparent",) else 1,
                border_color=P.border,
                text_color=P.text_primary,
                font=ctk.CTkFont(family=FONT_BOLD, size=12, weight="bold"),
                corner_radius=8,
            ).pack(side="left", padx=(0, 8))

        return root

    # ══════════════════════════════════════════════════════════════════════════
    # PÁGINA SOBRE
    # ══════════════════════════════════════════════════════════════════════════
    def _make_sobre_page(self) -> ctk.CTkFrame:
        root = ctk.CTkFrame(self, fg_color=P.bg_app)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(root, fg_color=P.header, height=56, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(
            hdr, text="Sobre",
            font=ctk.CTkFont(family=FONT_BOLD, size=16, weight="bold"),
            text_color=P.text_primary,
        ).grid(row=0, column=0, padx=20, pady=12)
        ctk.CTkButton(
            hdr, text="Voltar",
            command=lambda: self._nav("main"),
            height=34, width=90,
            fg_color="transparent", border_width=1, border_color=P.border,
            text_color=P.text_secondary, hover_color=P.bg_card, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=12),
        ).grid(row=0, column=1, padx=16, pady=12)

        card = ctk.CTkFrame(
            root, fg_color=P.bg_section,
            corner_radius=18, border_width=1, border_color=P.border,
        )
        card.grid(row=1, column=0, padx=140, pady=50, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text=APP_TITLE,
            font=ctk.CTkFont(family=FONT_BOLD, size=32, weight="bold"),
            text_color=P.accent_light,
        ).pack(pady=(40, 4))
        ctk.CTkLabel(
            card, text=f"v{APP_VER}",
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=P.text_secondary,
        ).pack()

        ctk.CTkLabel(
            card,
            text=(
                "Automação de download de NFS-e (emitidas + recebidas)\n"
                "e importação no Domínio Web, empresa por empresa.\n\n"
                "© CONX Contabilidade"
            ),
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=P.text_secondary, justify="center",
        ).pack(pady=(16, 20))

        diag = ctk.CTkFrame(card, fg_color=P.bg_card, corner_radius=10)
        diag.pack(padx=40, pady=(0, 40), fill="x")
        ctk.CTkLabel(
            diag,
            text=(
                f"Python          {sys.version.split()[0]}\n"
                f"Portal NFSe     {getattr(config, 'NFSE_LOGIN_URL', '-')}\n"
                f"Pasta de saída  {getattr(config, 'PASTA_SAIDA', '-')}\n"
                f"Data/hora       {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            ),
            font=ctk.CTkFont(family=FONT_MONO, size=11),
            text_color=P.text_secondary, justify="left", anchor="w",
        ).pack(padx=18, pady=14, anchor="w")

        return root

    # ── Navegação ─────────────────────────────────────────────────────────────
    def _nav(self, page: str) -> None:
        m = {"main": self._page_main, "config": self._page_config, "sobre": self._page_sobre}
        if page in m:
            m[page].tkraise()
            self._current_page = page

    # ══════════════════════════════════════════════════════════════════════════
    # LÓGICA DE EXECUÇÃO
    # ══════════════════════════════════════════════════════════════════════════
    def _on_run(self) -> None:
        if self.running:
            return
        try:
            if self._use_prev_month.get():
                dt_ini = dt_fim = None
            else:
                dt_ini = self._dt_start.get_date().strftime("%d/%m/%Y")
                dt_fim = self._dt_end.get_date().strftime("%d/%m/%Y")
                if datetime.strptime(dt_ini, "%d/%m/%Y") > datetime.strptime(dt_fim, "%d/%m/%Y"):
                    raise ValueError("Data início maior que data fim.")
            cnpjs = self._parse_cnpjs()
        except ValueError as exc:
            messagebox.showerror("Validação", str(exc), parent=self)
            return

        # Aplica opções rápidas ao config em memória
        config.PLAYWRIGHT_HEADLESS = not self._chk_debug.get()  # type: ignore[attr-defined]
        config.DOMINIO_WEB_IMPORTAR = self._chk_dominio.get()   # type: ignore[attr-defined]

        self.cancel_ev = threading.Event()
        self._set_running(True)
        self._set_status("Executando NFSe...", P.accent_light)
        self.toasts.show("Automação iniciada", "Processando em segundo plano.", kind="info")
        logging.getLogger("nfse.gui").info("Automação iniciada pela interface.")

        threading.Thread(
            target=self._worker, args=(dt_ini, dt_fim, cnpjs), daemon=True
        ).start()

    def _worker(self, dt_ini, dt_fim, cnpjs) -> None:
        status = "ok"
        total = ok = 0
        try:
            from nfse_automacao import preparar_parametros, executar_local
            params = preparar_parametros(dt_ini, dt_fim, cnpjs)
            resultados = executar_local(params, cancel_event=self.cancel_ev)
            total = len(resultados)
            ok    = sum(1 for r in resultados if r.status == "ok")

            if self._chk_email.get():
                from nfse_automacao import montar_mensagem, notificar_email
                msg = montar_mensagem(resultados, params)
                notificar_email(msg["assunto"], msg["mensagem"])

        except ExecucaoCancelada:
            status = "cancelado"
        except Exception:
            status = "erro"
            logging.getLogger("nfse.gui").exception("Erro na automação.")
        finally:
            self.after(0, lambda: self._on_done(status, total, ok))

    def _on_done(self, status: str, total: int, ok: int) -> None:
        self._set_running(False)

        if status == "ok" and total > 0:
            # Atualiza stats
            s = _load_stats()
            s["total_empresas"]      = s.get("total_empresas", 0) + ok
            s["horas_economizadas"]  = round(s.get("horas_economizadas", 0.0) + ok * 0.25, 1)
            s["taxa_sucesso"]        = round((ok / total) * 100) if total else 0
            _save_stats(s)
            self._card_empresas.set_value(str(s["total_empresas"]))
            self._card_horas.set_value(f"{s['horas_economizadas']:.1f}h")
            self._card_sucesso.set_value(f"{s['taxa_sucesso']}%")

            self._set_status("Concluído", P.success)
            self._progress.set(1)
            self.toasts.show("Automação concluída", f"{ok}/{total} empresas processadas.", kind="success")
        elif status == "cancelado":
            self._set_status("Cancelado", P.warning)
            self._progress.set(0)
            self.toasts.show("Cancelado", "Interrompido pelo usuário.", kind="warning")
        else:
            self._set_status("Erro", P.danger)
            self._progress.set(0)
            self.toasts.show("Falha", "Verifique os logs para detalhes.", kind="error")

    def _on_cancel(self) -> None:
        if self.cancel_ev:
            self.cancel_ev.set()
        self._set_status("Cancelando...", P.warning)
        self._cancel_btn.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        self.running = running
        self._run_btn.configure(
            state="disabled" if running else "normal",
            text="  Executando...  " if running else "  Iniciar Automação  ",
        )
        self._cancel_btn.configure(state="normal" if running else "disabled")
        if running:
            self._progress.configure(mode="indeterminate")
            self._progress.start()
            self._spinner.pack(side="left", padx=(10, 0))
            self._spinner.start()
            self._run_btn.stop_glow()
        else:
            self._progress.stop()
            self._progress.configure(mode="determinate")
            self._spinner.stop()
            self._spinner.pack_forget()
            self._run_btn.start_glow(base=P.accent, peak=P.accent_light)
            self.cancel_ev = None

    def _set_status(self, text: str, color: str) -> None:
        self._status_txt.configure(text=text, text_color=color)
        self._status_dot.set_color(color)
        self._hdr_status_lbl.configure(text=text, text_color=color)
        self._hdr_pulse.set_color(color)

    # ══════════════════════════════════════════════════════════════════════════
    # LOGS
    # ══════════════════════════════════════════════════════════════════════════
    def _setup_logging(self) -> None:
        h = QueueLogHandler(self.log_queue)
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S"))
        self._log_handler = h
        logging.getLogger().addHandler(h)
        logging.getLogger().setLevel(logging.INFO)
        self.after(200, lambda: self._insert_log("Interface pronta.", "INFO"))

    _MAX_LINES = 4000
    _TRIM_CHUNK = 400

    def _poll_logs(self) -> None:
        chunks: list[tuple[str, str]] = []
        try:
            while True:
                rec = self.log_queue.get_nowait()
                if not self._passes_filter(rec):
                    continue
                chunks.append((self._log_handler.format(rec), rec.levelname))
        except queue.Empty:
            pass
        if chunks:
            self._flush(chunks)
        self.after(120, self._poll_logs)

    def _passes_filter(self, rec: logging.LogRecord) -> bool:
        if self._log_filter == "ALL":
            return True
        if self._log_filter == "ERRO":
            return rec.levelno >= logging.ERROR
        return rec.levelno >= logging.INFO

    def _flush(self, chunks: list[tuple[str, str]]) -> None:
        inner = self._logs_txt._textbox
        self._logs_txt.configure(state="normal")
        for msg, lv in chunks:
            sep = msg.find("  ")
            if sep > 0:
                inner.insert("end", msg[:sep + 2], "TS")
                inner.insert("end", msg[sep + 2:] + "\n", lv)
            else:
                inner.insert("end", msg + "\n", lv)
        total = int(inner.index("end-1c").split(".")[0])
        if total > self._MAX_LINES + self._TRIM_CHUNK:
            inner.delete("1.0", f"{total - self._MAX_LINES}.0")
        self._logs_txt.configure(state="disabled")
        inner.see("end")

    def _insert_log(self, msg: str, lv: str = "INFO") -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self._flush([(f"{now}  {lv:<8}  {msg}", lv)])

    def _clear_logs(self) -> None:
        self._logs_txt.configure(state="normal")
        self._logs_txt._textbox.delete("1.0", "end")
        self._logs_txt.configure(state="disabled")

    def _copy_logs(self) -> None:
        txt = self._logs_txt._textbox.get("1.0", "end").strip()
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt)

    def _set_log_filter(self, val: str) -> None:
        self._log_filter = val

    # ══════════════════════════════════════════════════════════════════════════
    # CONFIGURAÇÕES
    # ══════════════════════════════════════════════════════════════════════════
    def _save_config(self) -> None:
        if not CONFIG_PATH.exists():
            messagebox.showerror("Erro", "config.py não encontrado.", parent=self)
            return
        original = CONFIG_PATH.read_text(encoding="utf-8")
        novo = original
        try:
            for key, var in self._cfg_vars.items():
                val = var.get()
                atual = getattr(config, key, "")
                if isinstance(atual, bool):
                    lit = "True" if val.strip().lower() in ("true", "1", "sim") else "False"
                elif isinstance(atual, int) and not isinstance(atual, bool):
                    int(val)
                    lit = val.strip()
                else:
                    lit = f'r"{val}"' if "\\" in val and '"' not in val else f'"{val.replace(chr(34), chr(92)+chr(34))}"'
                novo = re.sub(
                    rf"^({re.escape(key)}\s*=\s*)(.+?)(\s*(?:#.*)?)$",
                    lambda m, l=lit: f"{m.group(1)}{l}{m.group(3)}",
                    novo, count=1, flags=re.MULTILINE,
                )
        except ValueError as exc:
            messagebox.showerror("Validação", str(exc), parent=self)
            return
        CONFIG_PATH.with_suffix(".py.bak").write_text(original, encoding="utf-8")
        CONFIG_PATH.write_text(novo, encoding="utf-8")
        try:
            import importlib; importlib.reload(config)
        except Exception:
            pass
        messagebox.showinfo("Configurações", "Salvo com sucesso.", parent=self)

    def _reload_config(self) -> None:
        try:
            import importlib; importlib.reload(config)
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)
            return
        for key, var in self._cfg_vars.items():
            var.set(str(getattr(config, key, "")))

    def _open_config(self) -> None:
        try:
            os.startfile(str(CONFIG_PATH))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)

    def _browse(self, key: str, kind: str) -> None:
        var = self._cfg_vars[key]
        cur = var.get()
        if kind == "dir":
            val = filedialog.askdirectory(parent=self, initialdir=cur or None)
        else:
            val = filedialog.askopenfilename(
                parent=self, initialdir=str(Path(cur).parent) if cur else None,
                filetypes=[("Planilhas", "*.xlsx *.xls"), ("Todos", "*.*")],
            )
        if val:
            var.set(val)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _toggle_dates(self) -> None:
        st = "disabled" if self._use_prev_month.get() else "normal"
        self._dt_start.configure(state=st)
        self._dt_end.configure(state=st)

    def _on_dominio_toggle(self) -> None:
        v = self._chk_dominio.get()
        self._insert_log(
            f"Importação no Domínio Web: {'ativada' if v else 'desativada'}.", "INFO"
        )

    def _parse_cnpjs(self) -> list[str] | None:
        raw = self._cnpjs_box.get("1.0", "end").strip()
        if not raw:
            return None
        partes = [p for p in re.split(r"[\s,;]+", raw) if p]
        result, bad = [], []
        for p in partes:
            d = re.sub(r"\D", "", p)
            if len(d) == 14:
                result.append(d)
            else:
                bad.append(p)
        if bad:
            raise ValueError(f"CNPJ inválido: {', '.join(bad[:3])}")
        return result or None

    def _open_output(self) -> None:
        pasta = Path(getattr(config, "PASTA_SAIDA", ""))
        if not pasta.exists():
            messagebox.showwarning("Pasta não encontrada", str(pasta), parent=self)
            return
        try:
            os.startfile(str(pasta))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)

    def _rotate_tip(self) -> None:
        self._tip_idx = (self._tip_idx + 1) % len(TIPS)
        try:
            self._tip_lbl.configure(text=TIPS[self._tip_idx])
        except Exception:
            pass
        self.after(12_000, self._rotate_tip)

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("Sair", "Automação em andamento. Sair mesmo assim?", parent=self):
                return
            if self.cancel_ev:
                self.cancel_ev.set()
        logging.getLogger().removeHandler(self._log_handler)
        self.destroy()


# ── Entrypoint ────────────────────────────────────────────────────────────────
def main() -> None:
    app = NFSEGuiApp()
    app.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
