from __future__ import annotations

import re
from typing import List, Optional, Tuple

from print_scanner_app.domain.models.raw_batch import RawBatchInfo

# Archivos tipo {NOMBRE}-%05d.jpg -> basename ...-00042.cr3
_FRAME_SUFFIX_RE = re.compile(r"-(\d{4,6})\.(?:cr3|cr2|jpg|jpeg)$", re.IGNORECASE)
_FRAME_FALLBACK_RE = re.compile(r"(\d{4,6})\.(?:cr3|cr2|jpg|jpeg)$", re.IGNORECASE)


def extract_frame_from_basename(name: str) -> Optional[int]:
    """Obtiene número de frame desde el basename destino (ej. UY-xxx-0042.cr3)."""
    if not name:
        return None
    m = _FRAME_SUFFIX_RE.search(name.strip())
    if m:
        return int(m.group(1))
    m2 = _FRAME_FALLBACK_RE.search(name.strip())
    if m2:
        return int(m2.group(1))
    return None


def batch_subfolder_for_download(dest_basenames: List[str]) -> RawBatchInfo:
    """
    Calcula nombre de subcarpeta m-n para un único clic de descarga.
    Usa min/max de frames detectados en los basenames del lote actual.

    Convención de producto (5 dígitos por extremo): p. ej. un solo frame 100 → ``00100-00100``.
    Documentado en ``docs/DESCARGAR_RAWS_BUG.md`` para evitar confusión con 4 dígitos.
    """
    frames = [extract_frame_from_basename(b) for b in dest_basenames]
    valid = [f for f in frames if f is not None]
    if not valid:
        return RawBatchInfo(subfolder="sin_rango_descarga", min_frame=None, max_frame=None)
    lo, hi = min(valid), max(valid)
    return RawBatchInfo(subfolder=f"{lo:05d}-{hi:05d}", min_frame=lo, max_frame=hi)


def format_batch_dir_name(info: RawBatchInfo) -> str:
    return info.subfolder
