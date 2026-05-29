"""
ui_animations.py - Motor de animacoes para a GUI NFSe.

Recursos:
  - Easing functions (cubic, expo, back, elastic)
  - Interpolacao de cores (hex)
  - Funcao tween() generica baseada em widget.after() (~60fps)
  - Fade de cor em widgets customtkinter
  - Helpers para pulse, scale logico e counter numerico
"""
from __future__ import annotations

import time
from typing import Callable

# ==========================================================================
# Easing functions: entrada e saida em [0,1]
# ==========================================================================


def linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_quart(t: float) -> float:
    return 1 - (1 - t) ** 4


def ease_out_expo(t: float) -> float:
    if t >= 1:
        return 1.0
    return 1 - 2 ** (-10 * t)


def ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_out_back(t: float) -> float:
    c1 = 1.70158
    c2 = c1 * 1.525
    if t < 0.5:
        return ((2 * t) ** 2 * ((c2 + 1) * 2 * t - c2)) / 2
    return (((2 * t - 2) ** 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2


# ==========================================================================
# Cores
# ==========================================================================


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Interpola duas cores hex. t=0 retorna c1, t=1 retorna c2."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((
        r1 + (r2 - r1) * t,
        g1 + (g2 - g1) * t,
        b1 + (b2 - b1) * t,
    ))


# ==========================================================================
# Tween engine
# ==========================================================================


class Tween:
    """
    Animacao unica que chama on_update(t) em cada frame ate completar.
    Pode ser cancelada via cancel().
    """

    def __init__(
        self,
        widget,
        duration_ms: int,
        on_update: Callable[[float], None],
        *,
        ease: Callable[[float], float] = ease_out_cubic,
        on_complete: Callable[[], None] | None = None,
        delay_ms: int = 0,
        fps: int = 60,
    ) -> None:
        self._widget = widget
        self._duration = max(1, duration_ms)
        self._on_update = on_update
        self._on_complete = on_complete
        self._ease = ease
        self._frame_ms = max(1, int(1000 / fps))
        self._start: float | None = None
        self._after_id: str | None = None
        self._cancelled = False
        if delay_ms > 0:
            self._after_id = widget.after(delay_ms, self._begin)
        else:
            self._begin()

    def _begin(self) -> None:
        if self._cancelled:
            return
        self._start = time.perf_counter()
        self._tick()

    def _tick(self) -> None:
        if self._cancelled or self._start is None:
            return
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        t = min(1.0, elapsed_ms / self._duration)
        try:
            self._on_update(self._ease(t))
        except Exception:  # noqa: BLE001
            # Widget destruido no meio da animacao: aborta silenciosamente.
            self._cancelled = True
            return
        if t < 1.0:
            self._after_id = self._widget.after(self._frame_ms, self._tick)
        else:
            self._after_id = None
            if self._on_complete:
                try:
                    self._on_complete()
                except Exception:  # noqa: BLE001
                    pass

    def cancel(self) -> None:
        self._cancelled = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None


def tween(
    widget,
    duration_ms: int,
    on_update: Callable[[float], None],
    *,
    ease: Callable[[float], float] = ease_out_cubic,
    on_complete: Callable[[], None] | None = None,
    delay_ms: int = 0,
) -> Tween:
    """Atalho para criar e iniciar um Tween."""
    return Tween(
        widget,
        duration_ms,
        on_update,
        ease=ease,
        on_complete=on_complete,
        delay_ms=delay_ms,
    )


# ==========================================================================
# Helpers de alto nivel
# ==========================================================================


def fade_color(
    widget,
    key: str,
    from_color: str,
    to_color: str,
    duration_ms: int = 260,
    *,
    ease: Callable[[float], float] = ease_out_cubic,
    on_complete: Callable[[], None] | None = None,
) -> Tween:
    """
    Anima um atributo de cor de um widget customtkinter.
    key: 'fg_color', 'text_color', 'border_color', etc.
    """
    def _upd(t: float) -> None:
        widget.configure(**{key: lerp_color(from_color, to_color, t)})

    return tween(widget, duration_ms, _upd, ease=ease, on_complete=on_complete)


def pulse_color(
    widget,
    key: str,
    base: str,
    peak: str,
    period_ms: int = 1400,
) -> Tween:
    """
    Pulsa uma cor ciclicamente entre base e peak usando uma onda seno suave.
    Retorna o Tween; cancele-o para parar.
    """
    import math

    widget_ref = widget
    cancelled = [False]

    start = time.perf_counter()

    def step() -> None:
        if cancelled[0]:
            return
        elapsed = (time.perf_counter() - start) * 1000
        # seno entre 0 e 1, periodo total = period_ms
        phase = (elapsed % period_ms) / period_ms
        t = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
        try:
            widget_ref.configure(**{key: lerp_color(base, peak, t)})
        except Exception:  # noqa: BLE001
            cancelled[0] = True
            return
        widget_ref.after(32, step)

    # wrapper que respeita o contrato de Tween.cancel()
    class _PulseHandle:
        def cancel(self) -> None:
            cancelled[0] = True
            try:
                widget_ref.configure(**{key: base})
            except Exception:  # noqa: BLE001
                pass

    step()
    return _PulseHandle()  # type: ignore[return-value]


def tween_int(
    widget,
    duration_ms: int,
    start: int,
    end: int,
    on_update: Callable[[int], None],
    *,
    ease: Callable[[float], float] = ease_out_cubic,
    on_complete: Callable[[], None] | None = None,
) -> Tween:
    """Tween numerico inteiro, util para contadores."""
    delta = end - start

    def _upd(t: float) -> None:
        on_update(int(round(start + delta * t)))

    return tween(widget, duration_ms, _upd, ease=ease, on_complete=on_complete)
