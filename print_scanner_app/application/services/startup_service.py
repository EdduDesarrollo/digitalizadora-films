from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from print_scanner_app.application.services.camera_service import CameraService
from print_scanner_app.application.services.printer_service import PrinterService
from print_scanner_app.infrastructure.system.mount_tools import unmount_camera_mounts
from print_scanner_app.infrastructure.system.usb_tools import reset_usb_camara_e_impresora


@dataclass
class StartupOutcome:
    camera_assigned: bool
    printer_ok: bool
    usb_resets: int


class StartupService:
    """Orden de arranque sin Kivy: desmontaje → reset USB opcional → cámara → impresora."""

    def __init__(
        self,
        *,
        camera: CameraService,
        printer: PrinterService,
        logger: Optional[logging.Logger] = None,
    ):
        self._camera = camera
        self._printer = printer
        self._log = logger or logging.getLogger(__name__)

    def run(
        self,
        *,
        expected_serial: str,
        config_camera_json: Mapping[str, Any],
        reset_usb_first: bool = True,
    ) -> StartupOutcome:
        unmount_camera_mounts()
        n_reset = 0
        if reset_usb_first:
            n_reset = reset_usb_camara_e_impresora()
            time.sleep(4.0)

        cam_ok = self._camera.assign_camera(expected_serial, config_camera_json).ok
        pr_ok = self._printer.connect()
        return StartupOutcome(camera_assigned=cam_ok, printer_ok=pr_ok, usb_resets=n_reset)
