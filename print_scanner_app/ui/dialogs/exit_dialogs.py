"""Diálogo de confirmación de salida."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.ui.i18n import bind_popup_tracking, t


class ExitDialogs:
    @staticmethod
    def confirm_exit(on_confirm: Callable[[], None], on_cancel: Callable[[], None] | None = None) -> bool:
        cancel_cb = on_cancel or (lambda: None)
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            on_confirm()
            return False

        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        box.add_widget(Label(text=t("exit.confirm_body"), halign="center"))
        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
        yes = Button(text=t("common.exit"))
        no = Button(text=t("common.cancel"))
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        popup = Popup(
            title=t("exit.confirm_title"),
            content=box,
            size_hint=(None, None),
            size=(420, 190),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)

        def do_yes(_inst):
            popup.dismiss()
            on_confirm()

        def do_no(_inst):
            popup.dismiss()
            cancel_cb()

        yes.bind(on_release=do_yes)
        no.bind(on_release=do_no)
        popup.open()
        return True

    @staticmethod
    def confirm_exit_with_pending(
        pending_count: int,
        on_save_and_exit: Callable[[], None],
        on_exit_without_saving: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> bool:
        cancel_cb = on_cancel or (lambda: None)
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            on_exit_without_saving()
            return False

        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        box.add_widget(
            Label(
                text=t("exit.pending_body", pending_count=pending_count),
                halign="center",
            )
        )
        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
        save_exit = Button(text=t("exit.save_and_exit"))
        exit_now = Button(text=t("exit.exit_without_saving"))
        cancel = Button(text=t("common.cancel"))
        row.add_widget(save_exit)
        row.add_widget(exit_now)
        row.add_widget(cancel)
        box.add_widget(row)
        popup = Popup(
            title=t("exit.pending_title"),
            content=box,
            size_hint=(None, None),
            size=(620, 230),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)

        def _save(_inst):
            popup.dismiss()
            on_save_and_exit()

        def _exit(_inst):
            popup.dismiss()
            on_exit_without_saving()

        def _cancel(_inst):
            popup.dismiss()
            cancel_cb()

        save_exit.bind(on_release=_save)
        exit_now.bind(on_release=_exit)
        cancel.bind(on_release=_cancel)
        popup.open()
        return True
