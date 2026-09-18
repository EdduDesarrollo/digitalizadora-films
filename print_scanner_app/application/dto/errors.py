from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ErrorCode(Enum):
    DISK_FULL = "disk_full"
    PERMISSION = "permission"
    READONLY_FS = "readonly_fs"
    CAMERA = "camera"
    PRINTER = "printer"
    RAW_DOWNLOAD = "raw_download"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorEnvelope:
    code: ErrorCode
    message: str
    cause: Optional[str] = None
    details: Optional[Any] = None
