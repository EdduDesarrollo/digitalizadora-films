from dataclasses import dataclass
from typing import Optional


@dataclass
class PrinterState:
    device_path: str = "/dev/usb/lp0"
    connected: bool = False
    last_error: Optional[str] = None
