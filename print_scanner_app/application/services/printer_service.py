from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from print_scanner_app.domain.policies.retry_policy import RetryConfig, run_with_retries
from print_scanner_app.infrastructure.printer.escpos_client import EscposClient
from print_scanner_app.infrastructure.printer.printer_device import (
    describe_device_permissions,
    device_is_writable,
    first_lp_device,
    lp_permission_hint,
)
from print_scanner_app.infrastructure.system.usb_tools import reset_usb_camara_e_impresora


class PrinterService:
    def __init__(self, *, logger: Optional[logging.Logger] = None):
        self._log = logger or logging.getLogger(__name__)
        self._client: EscposClient | None = None

    @property
    def client(self) -> EscposClient | None:
        return self._client

    def connect(self, device_path: Path | None = None, *, retries: RetryConfig | None = None) -> bool:
        path = device_path or first_lp_device()
        if not path:
            self._log.warning("No hay dispositivo /dev/usb/lp*")
            return False
        if not device_is_writable(path):
            self._log.error(describe_device_permissions(path))
            self._log.error("%s", lp_permission_hint(path))
            return False

        def open_printer():
            self._client = EscposClient.open(path)
            self._client.reset()
            return True

        try:
            run_with_retries(
                open_printer,
                should_retry=lambda e: isinstance(e, OSError),
                config=retries or RetryConfig(max_attempts=2, delay_seconds=4.0),
            )
            return True
        except Exception as e:  # noqa: BLE001
            self._log.error("Impresora: %s", e)
            reset_usb_camara_e_impresora()
            return False

    def ensure_connected(self) -> bool:
        return self._client is not None or self.connect()

    def move_film(self, pixels: int, *, retries: RetryConfig | None = None) -> bool:
        cfg = retries or RetryConfig(max_attempts=2, delay_seconds=1.0)
        for attempt in range(1, cfg.max_attempts + 1):
            try:
                if not self.ensure_connected():
                    raise RuntimeError("Impresora no disponible")
                assert self._client is not None
                self._client.advance_pixels(max(int(pixels), 1))
                return True
            except Exception as e:  # noqa: BLE001
                self._log.warning(
                    "Error moviendo film (intento %s/%s): %s",
                    attempt,
                    cfg.max_attempts,
                    e,
                )
                if attempt >= cfg.max_attempts:
                    self._log.error("No se pudo mover film tras reintentos")
                    return False
                reset_usb_camara_e_impresora()
                self._client = None
                time.sleep(cfg.delay_seconds)
                self.connect(retries=RetryConfig(max_attempts=1, delay_seconds=0))
        return False

    def send_image(self, image, *, retries: RetryConfig | None = None) -> bool:
        cfg = retries or RetryConfig(max_attempts=2, delay_seconds=1.0)
        for attempt in range(1, cfg.max_attempts + 1):
            try:
                if not self.ensure_connected():
                    raise RuntimeError("Impresora no disponible")
                assert self._client is not None
                self._client.send_image(image)
                return True
            except Exception as e:  # noqa: BLE001
                self._log.warning(
                    "Error enviando imagen a impresora (intento %s/%s): %s",
                    attempt,
                    cfg.max_attempts,
                    e,
                )
                if attempt >= cfg.max_attempts:
                    self._log.error("No se pudo imprimir imagen tras reintentos")
                    return False
                reset_usb_camara_e_impresora()
                self._client = None
                time.sleep(cfg.delay_seconds)
                self.connect(retries=RetryConfig(max_attempts=1, delay_seconds=0))
        return False
