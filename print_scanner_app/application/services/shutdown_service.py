from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from print_scanner_app.infrastructure.system.process_tools import kill_processes_using_device


class ShutdownService:
    def __init__(self, *, logger: Optional[logging.Logger] = None):
        self._log = logger or logging.getLogger(__name__)

    def release_printer(self, device_path: Path | str = "/dev/usb/lp0") -> None:
        killed = kill_processes_using_device(str(device_path))
        self._log.debug("PIDs kill impresora: %s", killed)
