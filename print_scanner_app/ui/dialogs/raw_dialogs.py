"""Diálogos de descarga RAW."""

from __future__ import annotations

from typing import Callable

from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs
from print_scanner_app.ui.i18n import bind_popup_tracking, t


# Convención carpeta de lote: ver docs/DESCARGAR_RAWS_BUG.md (NNNNN-MMMMM, ej. 00100-00100).
_BATCH_FOLDER_HINT = (
    " La subcarpeta del lote usa cinco dígitos por número (ej. 00100-00100 para el frame 100)."
)


class RawDialogs:
    @staticmethod
    def confirm_download(pending_count: int, on_confirm: Callable[[], None]) -> bool:
        try:
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
        except Exception:  # noqa: BLE001
            on_confirm()
            return False

        box = BoxLayout(orientation="vertical", spacing=8, padding=10)
        box.add_widget(
            Label(
                text=t("raw.confirm_body", pending_count=pending_count),
                halign="left",
                text_size=(460, None),
            )
        )
        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
        yes = Button(text=t("common.download"))
        no = Button(text=t("common.cancel"))
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        popup = Popup(
            title=t("raw.confirm_title"),
            content=box,
            size_hint=(None, None),
            size=(520, 220),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)

        def do_yes(_inst):
            popup.dismiss()
            on_confirm()

        def do_no(_inst):
            popup.dismiss()

        yes.bind(on_release=do_yes)
        no.bind(on_release=do_no)
        popup.open()
        return True

    @staticmethod
    def show_download_result(ok: bool, message: str) -> bool:
        title = t("raw.title") if ok else t("raw.title_error")
        return ErrorDialogs.show_error(message, title=title)

    @staticmethod
    def show_download_outcome(
        *,
        downloaded: int,
        not_found: int,
        batch_folder: str | None,
        error: str | None,
    ) -> None:
        """
        Mensajes alineados al resultado real: error, 0 descargados, parcial o éxito total.
        """
        batch = batch_folder or "—"
        if error:
            ErrorDialogs.show_error(error, title=t("raw.title_error"))
            return
        if downloaded == 0 and not_found > 0:
            ErrorDialogs.show_error(
                t("raw.none_downloaded", not_found=not_found, batch=batch),
                title=t("raw.title_none"),
            )
            return
        if downloaded > 0 and not_found > 0:
            ErrorDialogs.show_error(
                t("raw.partial", downloaded=downloaded, not_found=not_found, batch=batch),
                title=t("raw.title_partial"),
            )
            return
        ErrorDialogs.show_error(
            t("raw.success", downloaded=downloaded, batch=batch),
            title=t("raw.title"),
        )

    @staticmethod
    def format_missing_local_copy_message(ids: list[str]) -> str:
        """Texto del popup (máx. 5 ítems + «… y N más»), sin depender de Kivy."""
        base = t("raw.missing_local")
        if not ids:
            return base
        show = list(ids[:5])
        extra = len(ids) - len(show)
        lines = "\n".join(show)
        if extra > 0:
            lines = f"{lines}\n{t('raw.and_more', extra=extra)}"
        return f"{base}\n\n{lines}"

    @staticmethod
    def show_raw_pending_missing_local_copy(ids: list[str]) -> None:
        """
        Popup según `docs/ELIMINAR_JPG.md`: máximo 5 ítems y '… y N más'.
        """
        if not ids:
            return
        ErrorDialogs.show_error(
            RawDialogs.format_missing_local_copy_message(ids),
            title=t("raw.missing_local_title"),
            ok_label=t("common.accept"),
        )
