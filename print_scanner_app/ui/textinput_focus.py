"""Focus automático en TextInput de popups (cursor al final)."""

from __future__ import annotations

from typing import Any


def focus_text_input(text_input: Any, *, delay: float = 0) -> None:
    """Programa ``focus=True`` en el próximo frame de Kivy (o tras ``delay``)."""
    from kivy.clock import Clock

    def _focus(_dt):
        text_input.focus = True
        try:
            text_input.cursor = (len(text_input.text or ""), 0)
        except Exception:  # noqa: BLE001
            pass

    Clock.schedule_once(_focus, delay)
