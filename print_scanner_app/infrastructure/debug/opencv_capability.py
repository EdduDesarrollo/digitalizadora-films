"""
Detección de capacidad para ventanas OpenCV (debug de alineación).

En Linux sin `DISPLAY`/`WAYLAND_DISPLAY`, HighGUI no puede abrir ventanas aunque `cv2` esté instalado.
"""

from __future__ import annotations

import os
import sys


def alignment_debug_unavailable_reason() -> str | None:
    """Si no hay soporte de ventanas, retorna mensaje corto para UI/log; si OK, None."""
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as e:
        return f"sin OpenCV/numpy ({e})"
    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return "sin DISPLAY/WAYLAND (entorno gráfico)"
    return None


def alignment_debug_visual_available() -> bool:
    """True si se puede intentar `cv2.imshow` con expectativa razonable de éxito."""
    return alignment_debug_unavailable_reason() is None
