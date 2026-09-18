from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CameraSession:
    """Cámara gphoto2 ya inicializada (`gp` + instancia) para descarga RAW."""

    gp: Any
    camera: Any
    usb_address: str
