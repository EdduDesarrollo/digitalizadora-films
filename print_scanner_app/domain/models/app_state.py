from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from print_scanner_app.domain.models.camera_state import CameraState
from print_scanner_app.domain.models.printer_state import PrinterState


@dataclass
class RawDownloadState:
    """Estado en memoria de la cola RAW (par con el archivo de pendientes)."""

    pending: List[List[str]] = field(default_factory=list)  # [raw_name, dest_basename]


@dataclass
class AppState:
    """Estado global de la aplicación (sin dependencias de Kivy)."""

    digitalizing: bool = False
    pause_digitization: bool = False
    pause_pending: bool = False  # pausa solicitada durante tick crítico; se finaliza al terminar ese tick
    frame_count: int = 0
    camera: CameraState = field(default_factory=CameraState)
    printer: PrinterState = field(default_factory=PrinterState)
    raw_download: RawDownloadState = field(default_factory=RawDownloadState)

    def to_serializable_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppState":
        cam = CameraState(**data.get("camera", {}))
        prn = PrinterState(**data.get("printer", {}))
        rd = RawDownloadState(pending=data.get("raw_download", {}).get("pending", []))
        return cls(
            digitalizing=data.get("digitalizing", False),
            pause_digitization=data.get("pause_digitization", False),
            pause_pending=data.get("pause_pending", False),
            frame_count=data.get("frame_count", 0),
            camera=cam,
            printer=prn,
            raw_download=rd,
        )
