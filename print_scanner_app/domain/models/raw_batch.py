from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RawBatchInfo:
    """Metadatos del lote actual (un clic de descarga)."""

    subfolder: str
    min_frame: Optional[int]
    max_frame: Optional[int]
