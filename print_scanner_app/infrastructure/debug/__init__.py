"""Herramientas de depuración opcionales (p. ej. OpenCV HighGUI)."""

from print_scanner_app.infrastructure.debug.opencv_capability import (
    alignment_debug_unavailable_reason,
    alignment_debug_visual_available,
)
from print_scanner_app.infrastructure.debug.opencv_alignment_windows import (
    close_alignment_debug_windows,
    poll_alignment_debug_key,
    show_alignment_debug_windows,
    shutdown_alignment_debug_worker,
)

__all__ = [
    "alignment_debug_unavailable_reason",
    "alignment_debug_visual_available",
    "close_alignment_debug_windows",
    "poll_alignment_debug_key",
    "show_alignment_debug_windows",
    "shutdown_alignment_debug_worker",
]
