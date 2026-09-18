"""Cursor de sistema durante trabajo en segundo plano (hilo principal de Kivy)."""

from __future__ import annotations

from typing import Any


class KivyBusyCursor:
    """
    Activa ``wait`` y restaura ``arrow`` vía ``Clock.schedule_once`` (obligatorio para Window).
    Reutilizable en otros flujos largos además de la descarga RAW.
    """

    # __weakref__: Kivy Clock guarda weakrefs del callback; sin esto falla al programar métodos de instancia.
    __slots__ = ("_clock", "_window", "__weakref__")

    def __init__(self, clock: Any, window: Any) -> None:
        self._clock = clock
        self._window = window

    def show_wait(self) -> None:
        self._clock.schedule_once(self._set_wait, 0)

    def clear(self) -> None:
        self._clock.schedule_once(self._set_arrow, 0)

    def _set_wait(self, _dt: float) -> None:
        try:
            self._window.set_system_cursor("wait")
        except Exception:  # noqa: BLE001
            pass

    def _set_arrow(self, _dt: float) -> None:
        try:
            self._window.set_system_cursor("arrow")
        except Exception:  # noqa: BLE001
            pass
