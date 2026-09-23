"""Selección de directorio de salida (mismo flujo que «Cambiar Dir» en kivy_app)."""

from __future__ import annotations

import os
import shutil
import sys
import threading
from typing import Callable

from print_scanner_app.ui.presenters.app_presenter import AppPresenter


def prompt_output_directory(
    presenter: AppPresenter,
    *,
    on_success: Callable[[], None],
    on_open_popup: Callable[[object], None],
    refresh_status: Callable[[], None] | None = None,
) -> None:
    """
    Zenity en Linux (hilo de fondo para no bloquear la UI); popup Kivy en fallback.
    Si el usuario cancela, repite el diálogo.
    """
    if sys.platform == "linux" and shutil.which("zenity"):
        _prompt_output_directory_zenity_async(
            presenter,
            on_success=on_success,
            on_open_popup=on_open_popup,
            refresh_status=refresh_status,
        )
        return

    _prompt_output_directory_kivy(
        presenter,
        on_success=on_success,
        on_open_popup=on_open_popup,
        refresh_status=refresh_status,
    )


def _prompt_output_directory_zenity_async(
    presenter: AppPresenter,
    *,
    on_success: Callable[[], None],
    on_open_popup: Callable[[object], None],
    refresh_status: Callable[[], None] | None,
) -> None:
    from kivy.clock import Clock

    from print_scanner_app.infrastructure.system.native_directory_dialog import (
        pick_directory_ubuntu_zenity,
    )

    def work() -> None:
        picked = pick_directory_ubuntu_zenity(presenter.current_directory())

        def on_ui(_dt) -> None:
            if picked:
                if presenter.set_directory(picked):
                    if refresh_status:
                        refresh_status()
                    on_success()
                else:
                    prompt_output_directory(
                        presenter,
                        on_success=on_success,
                        on_open_popup=on_open_popup,
                        refresh_status=refresh_status,
                    )
                return
            prompt_output_directory(
                presenter,
                on_success=on_success,
                on_open_popup=on_open_popup,
                refresh_status=refresh_status,
            )

        Clock.schedule_once(on_ui, 0)

    threading.Thread(target=work, daemon=True).start()


def _prompt_output_directory_kivy(
    presenter: AppPresenter,
    *,
    on_success: Callable[[], None],
    on_open_popup: Callable[[object], None],
    refresh_status: Callable[[], None] | None,
) -> None:
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput

    from print_scanner_app.ui.i18n import bind_popup_tracking, t
    from print_scanner_app.ui.textinput_focus import focus_text_input
    from print_scanner_app.ui.widgets.custom_file_chooser import CustomFileChooser
    from print_scanner_app.ui.widgets.menu_button import MenuButton

    chooser_cls = CustomFileChooser if CustomFileChooser is not None else FileChooserListView
    box = BoxLayout(orientation="vertical", spacing=8, padding=10)
    chooser = chooser_cls(
        path=presenter.current_directory() or os.path.expanduser("~"),
        dirselect=True,
    )
    chooser.size_hint_y = 1
    path_hint = TextInput(
        text=presenter.current_directory(),
        multiline=False,
        size_hint_y=None,
        height=38,
    )
    row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
    b_ok = MenuButton(text=t("common.save"), size_hint_x=1)
    b_cancel = MenuButton(text=t("common.cancel"), size_hint_x=1)
    row.add_widget(b_ok)
    row.add_widget(b_cancel)
    box.add_widget(path_hint)
    box.add_widget(chooser)
    box.add_widget(row)
    pop = Popup(
        title=t("dir.change_title"),
        content=box,
        size_hint=(None, None),
        size=(820, 560),
    )
    bind_popup_tracking(pop)

    def sync_selected(_inst, selection):
        if selection:
            path_hint.text = selection[0]

    def save_dir(_x):
        if presenter.set_directory(path_hint.text):
            pop.dismiss()
            if refresh_status:
                refresh_status()
            on_success()
        else:
            from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs

            ErrorDialogs.show_error(
                t("dir.invalid"),
                title=t("dir.change_title"),
            )

    def cancel_dir(_x):
        pop.dismiss()
        _prompt_output_directory_kivy(
            presenter,
            on_success=on_success,
            on_open_popup=on_open_popup,
            refresh_status=refresh_status,
        )

    chooser.bind(selection=sync_selected)
    b_ok.bind(on_release=save_dir)
    b_cancel.bind(on_release=cancel_dir)
    focus_text_input(path_hint)
    on_open_popup(pop)
