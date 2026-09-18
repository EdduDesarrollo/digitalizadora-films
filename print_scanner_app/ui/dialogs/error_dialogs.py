"""Diálogos de error para UI Kivy (con fallback sin Kivy)."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.ui.i18n import bind_popup_tracking, t


def _with_kivy_or_fallback(
    on_ok: Callable[[], None],
    title: str,
    message: str,
    *,
    ok_label: str | None = None,
) -> bool:
    label = ok_label if ok_label is not None else t("common.ok")
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
    except Exception:  # noqa: BLE001
        on_ok()
        return False

    box = BoxLayout(orientation="vertical", spacing=8, padding=10)
    box.add_widget(Label(text=message, halign="left", text_size=(460, None)))
    btn = Button(text=label, size_hint_y=None, height=42)
    popup = Popup(title=title, content=box, size_hint=(None, None), size=(520, 250), auto_dismiss=False)
    bind_popup_tracking(popup)

    def close(_inst):
        popup.dismiss()
        on_ok()

    btn.bind(on_release=close)
    box.add_widget(btn)
    popup.open()
    return True


class ErrorDialogs:
    @staticmethod
    def show_error(
        message: str,
        *,
        title: str | None = None,
        on_ok: Callable[[], None] | None = None,
        ok_label: str | None = None,
    ) -> bool:
        cb = on_ok or (lambda: None)
        return _with_kivy_or_fallback(
            cb,
            title if title is not None else t("common.error"),
            message,
            ok_label=ok_label,
        )
