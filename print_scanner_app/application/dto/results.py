from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SimpleOk:
    ok: bool = True
    error: Optional[str] = None


@dataclass
class RawDownloadBatchResult:
    """Salida de ``RawDownloadService.download_batch`` (una corrida A [+ B si no hubo aborto fatal])."""

    downloaded: List[str] = field(default_factory=list)
    not_found: List[str] = field(default_factory=list)
    batch_folder: str = ""
    missing_local_copy_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class DownloadRawsResult:
    """Resultado de una corrida de descarga de RAW pendientes."""

    downloaded: List[str] = field(default_factory=list)
    not_found: List[str] = field(default_factory=list)
    batch_folder: Optional[str] = None
    stopped_at: Optional[str] = None
    error: Optional[str] = None
    missing_local_copy_ids: List[str] = field(default_factory=list)


@dataclass
class CameraAssignResult:
    ok: bool
    usb_address: Optional[str] = None
    serial: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExitResult:
    ok: bool = True
