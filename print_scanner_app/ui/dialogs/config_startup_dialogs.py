"""Popups de configuración inicial (prefijo y serial de cámara)."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.application.session_naming import normalized_prefijo_archivo
from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs
from print_scanner_app.ui.i18n import bind_popup_tracking, t
from print_scanner_app.ui.textinput_focus import focus_text_input
from print_scanner_app.ui.textinput_paste import enable_ctrl_v_paste


def _text_popup(
    *,
    title: str,
    message: str,
    initial: str,
    on_confirm: Callable[[str], None],
    on_open: Callable[[object], None],
    validate_nonempty: bool = True,
) -> None:
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput

    from print_scanner_app.ui.widgets.menu_button import MenuButton

    box = BoxLayout(orientation="vertical", spacing=10, padding=12)
    lbl = Label(
        text=message,
        size_hint_y=None,
        height=72,
        halign="center",
        valign="middle",
    )
    lbl.bind(size=lambda inst, _val: setattr(inst, "text_size", (inst.width, None)))
    box.add_widget(lbl)
    ti = TextInput(text=initial, multiline=False, size_hint_y=None, height=40)
    enable_ctrl_v_paste(ti)
    row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
    b_ok = MenuButton(text=t("common.ok"), size_hint_x=1)
    row.add_widget(b_ok)
    box.add_widget(ti)
    box.add_widget(row)
    pop = Popup(title=title, content=box, size_hint=(None, None), size=(520, 280), auto_dismiss=False)
    bind_popup_tracking(pop)

    def on_ok(_inst=None):
        value = (ti.text or "").strip()
        if validate_nonempty and not value:
            ErrorDialogs.show_error(t("config.empty_value"), title=title)
            return

        def _after_dismiss(_popup, *_args):
            pop.unbind(on_dismiss=_after_dismiss)
            on_confirm(value)

        pop.bind(on_dismiss=_after_dismiss)
        pop.dismiss()

    b_ok.bind(on_release=on_ok)
    ti.bind(on_text_validate=lambda *_: on_ok(None))
    focus_text_input(ti)
    on_open(pop)


class ConfigStartupDialogs:
    @staticmethod
    def show_prefijo_popup(
        *,
        current: str,
        on_confirm: Callable[[str], None],
        on_open: Callable[[object], None],
    ) -> None:
        _text_popup(
            title=t("config.prefijo_title"),
            message=t("config.prefijo_message"),
            initial=current,
            on_confirm=lambda raw: on_confirm(normalized_prefijo_archivo(raw)),
            on_open=on_open,
        )

    @staticmethod
    def show_camara_popup(
        *,
        current: str,
        on_confirm: Callable[[str], None],
        on_open: Callable[[object], None],
    ) -> None:
        _text_popup(
            title=t("config.serial_title"),
            message=t("config.serial_message"),
            initial=current,
            on_confirm=lambda raw: on_confirm((raw or "").strip()),
            on_open=on_open,
        )
