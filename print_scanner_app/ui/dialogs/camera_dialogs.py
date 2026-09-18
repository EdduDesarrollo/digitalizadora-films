"""Diálogos de cámara para feedback de operaciones."""

from __future__ import annotations

from print_scanner_app.ui.dialogs.error_dialogs import ErrorDialogs
from print_scanner_app.ui.i18n import t


class CameraDialogs:
    @staticmethod
    def show_retry_result(ok: bool, message: str) -> bool:
        title = t("camera.title") if ok else t("camera.title_error")
        return ErrorDialogs.show_error(message, title=title)
