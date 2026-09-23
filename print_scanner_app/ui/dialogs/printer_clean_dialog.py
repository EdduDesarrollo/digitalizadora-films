"""Popup de aviso: limpieza de impresora cada N frames (`docs/PAUSAR_500_FRAMES.md` §3.13)."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.ui.i18n import bind_popup_tracking, t

# Literales ES de referencia (tests / docs); la UI usa ``t()``.
PRINTER_CLEAN_POPUP_TITLE = "Digitalización pausada"
PRINTER_CLEAN_POPUP_MESSAGE = "Debe de limpiar la zona de captura!"
PRINTER_CLEAN_POPUP_BUTTON = "Cerrar"


class PrinterCleanDialogs:
    @staticmethod
    def show(*, on_open: Callable[..., None] | None = None) -> None:
        """
        Muestra el popup informativo. La digitación ya debe estar pausada.

        `on_open`: si se pasa, se llama como `on_open(popup)` en lugar de `popup.open()`
        (p. ej. `_open_popup_disabling_hotkeys` en kivy_app).
        """
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            return

        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        box.add_widget(
            Label(
                text=t("printer_clean.message"),
                valign="middle",
                halign="center",
                text_size=(360, None),
            )
        )
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=48)
        btn = Button(text=t("printer_clean.button"), size_hint_x=1)
        row.add_widget(btn)
        box.add_widget(row)
        popup = Popup(
            title=t("printer_clean.title"),
            content=box,
            size_hint=(None, None),
            size=(400, 200),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)
        btn.bind(on_release=lambda *_inst: popup.dismiss())
        if on_open is not None:
            on_open(popup)
        else:
            popup.open()
