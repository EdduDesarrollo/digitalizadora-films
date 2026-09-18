"""Diálogos del flujo Ajustes / Entangle."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.ui.i18n import bind_popup_tracking, t

# Literales ES de referencia (tests); la UI usa ``t()``.
ENTANGLE_SAVE_FAILURE_MESSAGE = (
    "Error al guardar configuración de la camara. ¿Desea continuar igualmente?"
)
ENTANGLE_SAVING_MESSAGE = "Espere… Guardando configuración de la cámara…"
CAMERA_SETTINGS_BLOCKED_MESSAGE = "Pausá la digitación (P) antes de abrir Ajustes."


class CameraSettingsDialogs:
    _saving_popup = None

    @classmethod
    def show_blocked_active_digitization(
        cls,
        *,
        on_ok: Callable[[], None] | None = None,
    ) -> bool:
        from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs

        return ErrorDialogs.show_error(
            t("settings.blocked"),
            title=t("settings.title"),
            on_ok=on_ok,
        )

    @classmethod
    def show_entangle_not_found(cls, *, on_ok: Callable[[], None] | None = None) -> bool:
        from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs

        return ErrorDialogs.show_error(
            t("settings.entangle_not_found"),
            title=t("common.error"),
            on_ok=on_ok,
        )

    @classmethod
    def show_entangle_error(cls, message: str, *, on_ok: Callable[[], None] | None = None) -> bool:
        from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs

        return ErrorDialogs.show_error(message, title=t("common.error"), on_ok=on_ok)

    @classmethod
    def show_saving(cls) -> bool:
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            return False

        if cls._saving_popup is not None:
            return True

        box = BoxLayout(orientation="vertical", padding=20, spacing=10)
        box.add_widget(Label(text=t("settings.saving_message"), font_size=16))
        popup = Popup(
            title=t("settings.saving_title"),
            content=box,
            size_hint=(None, None),
            size=(500, 150),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)
        cls._saving_popup = popup
        popup.open()
        return True

    @classmethod
    def dismiss_saving(cls) -> None:
        popup = cls._saving_popup
        cls._saving_popup = None
        if popup is None:
            return
        try:
            popup.dismiss()
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def show_save_failed_choice(
        cls,
        *,
        on_yes: Callable[[], None],
        on_no: Callable[[], None],
    ) -> bool:
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            on_no()
            return False

        box = BoxLayout(orientation="vertical", padding=20, spacing=10)
        box.add_widget(
            Label(
                text=t("settings.save_failure"),
                halign="left",
                valign="middle",
                text_size=(460, None),
            )
        )
        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
        btn_yes = Button(text=t("common.yes"), size_hint_x=0.5)
        btn_no = Button(text=t("common.no"), size_hint_x=0.5)
        row.add_widget(btn_yes)
        row.add_widget(btn_no)
        box.add_widget(row)
        popup = Popup(
            title=t("common.error"),
            content=box,
            size_hint=(None, None),
            size=(520, 220),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)

        def do_yes(_inst):
            popup.dismiss()
            on_yes()

        def do_no(_inst):
            popup.dismiss()
            on_no()

        btn_yes.bind(on_release=do_yes)
        btn_no.bind(on_release=do_no)
        popup.open()
        return True
