from dataclasses import dataclass
from typing import Optional


@dataclass
class CameraState:
    selected_serial: str = ""
    usb_address: str = ""  # ej. usb:001,025
    initialized: bool = False
    last_error: Optional[str] = None
