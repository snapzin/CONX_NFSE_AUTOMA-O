"""
ui_widgets.py - Widgets animados reutilizaveis para a GUI NFSe.
"""
from __future__ import annotations

import math
import time
from typing import Callable

import customtkinter as ctk  # type: ignore[import-untyped]
import tkinter as tk

from ui_animations import (
    Tween,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    ease_out_quart,
    fade_color,
    lerp_color,
    pulse_color,
    tween,
    tween_int,
)


# ============================================================================
# AnimatedStatCard - card com contador animado e hover lift
# ============================================================================
class AnimatedStatCard(ctk.CTkFrame):
    """
    Card de estatistica com:
      - barra superior colorida por acento
      - valor que anima numericamente quando e inteiro
      - borda/elevacao suaves no hover
    """

    def __init__(
        self,
        master,
        title: str,
        value: str = "-",
        accent: str = "#2aa889",
        *,
        bg_color: str = "#17243a",
        bg_hover: str = "#1d2d48",
        border_color: str = "#263753",
        text_primary: str = "#eef4ff",
        text_secondary: str = "#9db1ca",
        font_heading: str = "Bahnschrift SemiBold",
    ) -> None:
        super().__init__(
            master,
            fg_color=bg_color,
            corner_radius=14,
            border_width=2,
            border_color=border_color,
        )
        self._bg_base = bg_color
        self._bg_hover = bg_hover
        self._border_base = border_color
        self._border_accent = accent
        self._accent = accent
        self._value_cache: int | None = None
        self._value_tween: Tween | None = None

        top_line = ctk.CTkFrame(self, fg_color=accent, height=4, corner_radius=2)
        top_line.pack(fill="x", padx=10, pady=(10, 0))
        self._top_line = top_line

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(8, 12))

        self.title_label = ctk.CTkLabel(
            body,
            text=title.upper(),
            font=ctk.CTkFont(family=font_heading, size=10, weight="bold"),
            text_color=text_secondary,
            anchor="w",
        )
        self.title_label.pack(fill="x")

        self.value_label = ctk.CTkLabel(
            body,
            text=value,
            font=ctk.CTkFont(family=font_heading, size=24, weight="bold"),
            text_color=text_primary,
            anchor="w",
        )
        self.value_label.pack(fill="x")

        # Hover: lift visual (borda vira accent + leve troca de bg).
        for w in (self, body, top_line, self.title_label, self.value_label):
            w.bind("<Enter>", self._on_enter, add=True)
            w.bind("<Leave>", self._on_leave, add=True)

    def _on_enter(self, _e=None) -> None:
        fade_color(self, "fg_color", self._bg_base, self._bg_hover, 120)
        fade_color(self, "border_color", self._border_base, self._border_accent, 120)

    def _on_leave(self, _e=None) -> None:
        fade_color(self, "fg_color", self._bg_hover, self._bg_base, 140)
        fade_color(self, "border_color", self._border_accent, self._border_base, 140)

    def set_value(self, value: str) -> None:
        """Define o valor. Se for inteiro, anima a transicao numerica."""
        novo_int: int | None = None
        try:
            if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                novo_int = int(value)
        except AttributeError:
            novo_int = None

        if novo_int is not None and self._value_cache is not None:
            start = self._value_cache
            end = novo_int
            if start == end:
                self._value_cache = end
                self.value_label.configure(text=str(end))
                return
            if self._value_tween is not None:
                self._value_tween.cancel()
            self._value_tween = tween_int(
                self,
                duration_ms=500,
                start=start,
                end=end,
                on_update=lambda n: self.value_label.configure(text=str(n)),
                ease=ease_out_quart,
            )
            self._value_cache = end
        else:
            self._value_cache = novo_int
            self.value_label.configure(text=value)

    def set_accent_color(self, color: str) -> None:
        fade_color(self._top_line, "fg_color", self._accent, color, 240)
        self._accent = color
        self._border_accent = color


# ============================================================================
# GlowButton - botao principal com pulse de borda quando em destaque
# ============================================================================
class GlowButton(ctk.CTkButton):
    """
    Botao que pulsa a borda ciclicamente quando start_glow() eh chamado.
    Usado como CTA principal ("Executar agora").
    """

    def __init__(self, *args, glow_color: str = "#40cf84", **kwargs) -> None:
        kwargs.setdefault("border_width", 2)
        kwargs.setdefault("border_color", kwargs.get("fg_color", glow_color))
        super().__init__(*args, **kwargs)
        self._glow_color = glow_color
        self._glow_base = kwargs.get("border_color", glow_color)
        self._pulse_handle = None

    def start_glow(self, base: str | None = None, peak: str | None = None) -> None:
        self.stop_glow()
        self._pulse_handle = pulse_color(
            self,
            "border_color",
            base or self._glow_base,
            peak or self._glow_color,
            period_ms=1400,
        )

    def stop_glow(self) -> None:
        if self._pulse_handle is not None:
            self._pulse_handle.cancel()
            self._pulse_handle = None


# ============================================================================
# Spinner - indicador circular animado via Canvas
# ============================================================================
class Spinner(tk.Canvas):
    """
    Spinner circular animado. Usa Canvas e arc() com rotacao constante.
    Visivel so quando start() eh chamado.
    """

    def __init__(
        self,
        master,
        *,
        size: int = 22,
        thickness: int = 3,
        color: str = "#40cf84",
        bg: str = "#0b1220",
    ) -> None:
        super().__init__(
            master,
            width=size,
            height=size,
            highlightthickness=0,
            bd=0,
            bg=bg,
        )
        self._size = size
        self._thickness = thickness
        self._color = color
        self._angle = 0
        self._after_id: str | None = None
        self._arc = None

    def start(self) -> None:
        self.stop()
        pad = self._thickness
        self._arc = self.create_arc(
            pad,
            pad,
            self._size - pad,
            self._size - pad,
            start=0,
            extent=90,
            style="arc",
            outline=self._color,
            width=self._thickness,
        )
        self._tick()

    def _tick(self) -> None:
        if self._arc is None:
            return
        self._angle = (self._angle + 12) % 360
        try:
            self.itemconfigure(self._arc, start=self._angle)
        except tk.TclError:
            return
        self._after_id = self.after(32, self._tick)

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None
        if self._arc is not None:
            try:
                self.delete(self._arc)
            except tk.TclError:
                pass
            self._arc = None


# ============================================================================
# PulseBadge - pequeno circulo que pulsa (indicador de status)
# ============================================================================
class PulseBadge(tk.Canvas):
    """
    Circulo pequeno com animacao de pulse (anel expandindo e fading).
    Simula o efeito de "live indicator".
    """

    def __init__(
        self,
        master,
        *,
        color: str = "#40cf84",
        size: int = 14,
        bg: str = "#0b1220",
    ) -> None:
        super().__init__(
            master,
            width=size,
            height=size,
            highlightthickness=0,
            bd=0,
            bg=bg,
        )
        self._size = size
        self._color = color
        self._bg = bg
        self._center = size / 2
        self._core_r = size * 0.28
        self._after_id: str | None = None
        self._cancelled = False

        self._draw_core()
        self._pulse_start = time.perf_counter()
        self._tick()

    def _draw_core(self) -> None:
        self.delete("core")
        r = self._core_r
        self.create_oval(
            self._center - r,
            self._center - r,
            self._center + r,
            self._center + r,
            fill=self._color,
            outline="",
            tags="core",
        )

    def set_color(self, color: str) -> None:
        self._color = color
        self._draw_core()

    def _tick(self) -> None:
        if self._cancelled:
            return
        elapsed = (time.perf_counter() - self._pulse_start) * 1000
        period = 1600
        t = (elapsed % period) / period
        # raio do anel cresce de core_r ate size/2
        max_r = self._size / 2
        r = self._core_r + (max_r - self._core_r) * t
        # alpha do anel: comeca opaco (no core) e fade ao chegar na borda
        alpha = 1 - t
        ring_color = lerp_color(self._color, self._bg, 1 - alpha * 0.6)
        self.delete("ring")
        self.create_oval(
            self._center - r,
            self._center - r,
            self._center + r,
            self._center + r,
            outline=ring_color,
            width=1,
            tags="ring",
        )
        # re-desenha core para ficar acima do anel
        self._draw_core()
        try:
            self._after_id = self.after(32, self._tick)
        except tk.TclError:
            self._cancelled = True

    def destroy(self) -> None:  # noqa: D401
        self._cancelled = True
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
        super().destroy()


# ============================================================================
# Toast - notificacao deslizante no canto inferior direito
# ============================================================================
class ToastManager:
    """
    Gerencia notificacoes empilhadas no canto inferior direito da root window.
    Cada toast desliza da direita, permanece e desliza de volta.
    """

    def __init__(
        self,
        root,
        *,
        palette: dict[str, str] | None = None,
        font_family: str = "Bahnschrift",
    ) -> None:
        self._root = root
        self._toasts: list[ctk.CTkFrame] = []
        self._palette = palette or {
            "bg": "#17243a",
            "border": "#263753",
            "text": "#eef4ff",
            "text_secondary": "#9db1ca",
            "accent_info": "#2aa889",
            "accent_success": "#40cf84",
            "accent_warning": "#f1b34f",
            "accent_error": "#e86a6a",
        }
        self._font_family = font_family

    def show(
        self,
        title: str,
        message: str = "",
        *,
        kind: str = "info",
        duration_ms: int = 3600,
    ) -> None:
        accent = {
            "info": self._palette["accent_info"],
            "success": self._palette["accent_success"],
            "warning": self._palette["accent_warning"],
            "error": self._palette["accent_error"],
        }.get(kind, self._palette["accent_info"])

        # Toplevel invisivel, sem decoracao, fundo transparente, overrideredirect.
        # Em Tk no Windows a combinacao override-redirect + attributes -alpha funciona.
        top = tk.Toplevel(self._root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        top.configure(bg=self._palette["bg"])

        container = ctk.CTkFrame(
            top,
            fg_color=self._palette["bg"],
            border_width=1,
            border_color=self._palette["border"],
            corner_radius=12,
        )
        container.pack(fill="both", expand=True, padx=0, pady=0)

        accent_bar = ctk.CTkFrame(container, fg_color=accent, width=4, corner_radius=2)
        accent_bar.pack(side="left", fill="y", padx=(10, 0), pady=10)

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        ctk.CTkLabel(
            body,
            text=title,
            font=ctk.CTkFont(family=self._font_family, size=13, weight="bold"),
            text_color=self._palette["text"],
            anchor="w",
            justify="left",
        ).pack(fill="x")

        if message:
            ctk.CTkLabel(
                body,
                text=message,
                font=ctk.CTkFont(family=self._font_family, size=11),
                text_color=self._palette["text_secondary"],
                anchor="w",
                justify="left",
                wraplength=280,
            ).pack(fill="x", pady=(2, 0))

        # Geometria: empilha no canto inferior direito da root.
        self._root.update_idletasks()
        top.update_idletasks()

        width = max(280, top.winfo_reqwidth())
        height = max(56, top.winfo_reqheight())
        top.geometry(f"{width}x{height}")

        root_x = self._root.winfo_rootx()
        root_y = self._root.winfo_rooty()
        root_w = self._root.winfo_width()
        root_h = self._root.winfo_height()

        margin = 18
        stack_offset = sum(t.winfo_height() + 10 for t in self._toasts if t.winfo_exists())
        target_x = root_x + root_w - width - margin
        target_y = root_y + root_h - height - margin - stack_offset

        start_x = root_x + root_w + 20  # fora da tela, a direita
        top.geometry(f"{width}x{height}+{start_x}+{target_y}")

        self._toasts.append(top)

        def update_pos(t: float) -> None:
            x = int(start_x + (target_x - start_x) * t)
            try:
                top.geometry(f"{width}x{height}+{x}+{target_y}")
                top.attributes("-alpha", t)
            except tk.TclError:
                pass

        tween(top, 320, update_pos, ease=ease_out_cubic)

        def dismiss() -> None:
            def slide_out(t: float) -> None:
                x = int(target_x + (start_x - target_x) * t)
                try:
                    top.geometry(f"{width}x{height}+{x}+{target_y}")
                    top.attributes("-alpha", 1 - t)
                except tk.TclError:
                    pass

            def _destroy() -> None:
                try:
                    top.destroy()
                except tk.TclError:
                    pass
                if top in self._toasts:
                    self._toasts.remove(top)

            tween(top, 260, slide_out, ease=ease_out_cubic, on_complete=_destroy)

        top.after(duration_ms, dismiss)
        # Click no toast tambem dispensa.
        for w in (top, container, body, accent_bar):
            w.bind("<Button-1>", lambda _e: dismiss())


# ============================================================================
# PageTransitionBar - barra superior que anima ao trocar de pagina
# ============================================================================
class PageTransitionBar(ctk.CTkFrame):
    """
    Barra fina horizontal que cresce da esquerda para a direita ao trocar de pagina.
    Retorna ao inicio apos pequena pausa. Serve como "indicador de carregamento".
    """

    def __init__(
        self,
        master,
        *,
        color: str = "#2aa889",
        height: int = 2,
        bg: str = "#0b1220",
    ) -> None:
        super().__init__(master, fg_color=bg, height=height, corner_radius=0)
        self._color = color
        self._bg = bg
        self._fill = ctk.CTkFrame(self, fg_color=color, corner_radius=0)
        self._fill.place(relx=0, rely=0, relwidth=0, relheight=1)
        self._running = False

    def play(self) -> None:
        if self._running:
            return
        self._running = True

        def grow(t: float) -> None:
            self._fill.place_configure(relwidth=t)

        def shrink(t: float) -> None:
            # desliza para a direita e some
            self._fill.place_configure(relx=t, relwidth=1 - t)

        def _reset() -> None:
            self._fill.place_configure(relx=0, relwidth=0)
            self._running = False

        def _shrink_phase() -> None:
            tween(self, 240, shrink, ease=ease_out_cubic, on_complete=_reset)

        tween(self, 320, grow, ease=ease_out_expo, on_complete=_shrink_phase)


# ============================================================================
# AnimatedSidebarButton - botao de nav com indicador lateral animado
# ============================================================================
class AnimatedSidebarButton(ctk.CTkFrame):
    """
    Item de navegacao com:
      - pilula de fundo que fade in/out no ativo
      - barra vertical lateral esquerda que cresce quando ativo
      - texto que transita de secundario para primario
    """

    def __init__(
        self,
        master,
        text: str,
        command: Callable[[], None],
        *,
        icon: str = "",
        width: int = 196,
        height: int = 44,
        accent: str = "#2aa889",
        bg: str = "#0f1724",
        bg_hover: str = "#17243a",
        bg_active: str = "#17243a",
        text_primary: str = "#eef4ff",
        text_secondary: str = "#9db1ca",
        font_heading: str = "Bahnschrift SemiBold",
    ) -> None:
        super().__init__(master, fg_color=bg, corner_radius=10, height=height)
        self.grid_propagate(False)
        self._bg = bg
        self._bg_hover = bg_hover
        self._bg_active = bg_active
        self._accent = accent
        self._text_primary = text_primary
        self._text_secondary = text_secondary
        self._active = False
        self._command = command

        # Barra vertical animada a esquerda
        self._indicator = ctk.CTkFrame(self, fg_color=bg, width=3, corner_radius=2)
        self._indicator.place(relx=0, rely=0.2, relheight=0.6, x=6)

        self._label = ctk.CTkLabel(
            self,
            text=f"{icon}   {text}".strip() if icon else f"   {text}",
            font=ctk.CTkFont(family=font_heading, size=13, weight="bold"),
            text_color=text_secondary,
            anchor="w",
        )
        self._label.place(relx=0, rely=0.5, anchor="w", x=16)

        for w in (self, self._label):
            w.bind("<Enter>", self._on_enter, add=True)
            w.bind("<Leave>", self._on_leave, add=True)
            w.bind("<Button-1>", self._on_click, add=True)

    def _on_click(self, _e=None) -> None:
        try:
            self._command()
        except Exception:  # noqa: BLE001
            pass

    def _on_enter(self, _e=None) -> None:
        if self._active:
            return
        fade_color(self, "fg_color", self._bg, self._bg_hover, 140)
        fade_color(self._label, "text_color", self._text_secondary, self._text_primary, 140)

    def _on_leave(self, _e=None) -> None:
        if self._active:
            return
        fade_color(self, "fg_color", self._bg_hover, self._bg, 200)
        fade_color(self._label, "text_color", self._text_primary, self._text_secondary, 200)

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        if active:
            fade_color(self, "fg_color", self._bg, self._bg_active, 220)
            fade_color(self._indicator, "fg_color", self._bg, self._accent, 220)
            fade_color(self._label, "text_color", self._text_secondary, self._text_primary, 220)
        else:
            fade_color(self, "fg_color", self._bg_active, self._bg, 220)
            fade_color(self._indicator, "fg_color", self._accent, self._bg, 220)
            fade_color(self._label, "text_color", self._text_primary, self._text_secondary, 220)


# ============================================================================
# SplashOverlay - overlay de boas-vindas com fade
# ============================================================================
class SplashOverlay(ctk.CTkFrame):
    """
    Overlay opaco que cobre toda a janela por alguns ms na inicializacao,
    exibe logo grande e entao faz fade out revelando a UI.
    """

    def __init__(
        self,
        master,
        *,
        title: str = "NFSe Automacao",
        subtitle: str = "Inicializando...",
        bg: str = "#0b1220",
        accent: str = "#2aa889",
        text_primary: str = "#eef4ff",
        text_secondary: str = "#9db1ca",
        font_heading: str = "Bahnschrift SemiBold",
        font: str = "Bahnschrift",
    ) -> None:
        super().__init__(master, fg_color=bg, corner_radius=0)
        self.place(relx=0, rely=0, relwidth=1, relheight=1)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo tipografico com acento
        self._title_lbl = ctk.CTkLabel(
            center,
            text=title,
            font=ctk.CTkFont(family=font_heading, size=46, weight="bold"),
            text_color=bg,
        )
        self._title_lbl.pack()

        bar_container = ctk.CTkFrame(center, fg_color="transparent", height=3)
        bar_container.pack(fill="x", pady=(10, 0))
        self._bar = ctk.CTkFrame(bar_container, fg_color=accent, corner_radius=2, height=3)
        self._bar.place(relx=0.5, rely=0, anchor="n", relwidth=0)

        self._subtitle_lbl = ctk.CTkLabel(
            center,
            text=subtitle,
            font=ctk.CTkFont(family=font, size=12),
            text_color=bg,
        )
        self._subtitle_lbl.pack(pady=(14, 0))

        self._bg = bg
        self._accent = accent
        self._text_primary = text_primary
        self._text_secondary = text_secondary

    def play(self, total_ms: int = 900, on_done: Callable[[], None] | None = None) -> None:
        fade_color(self._title_lbl, "text_color", self._bg, self._text_primary, 320, ease=ease_out_cubic)
        fade_color(self._subtitle_lbl, "text_color", self._bg, self._text_secondary, 380, ease=ease_out_cubic)

        def grow_bar(t: float) -> None:
            self._bar.place_configure(relwidth=t * 0.7)

        tween(self, int(total_ms * 0.6), grow_bar, ease=ease_out_expo)

        def fade_out() -> None:
            fade_color(self._title_lbl, "text_color", self._text_primary, self._bg, 240)
            fade_color(self._subtitle_lbl, "text_color", self._text_secondary, self._bg, 240)

            def finish() -> None:
                try:
                    self.destroy()
                except Exception:  # noqa: BLE001
                    pass
                if on_done:
                    on_done()

            self.after(280, finish)

        self.after(total_ms, fade_out)
