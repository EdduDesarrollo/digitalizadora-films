"""
Ventanas de debug de alineación (`cv2.imshow`).

OpenCV es opcional: si no está instalado o no hay display, las funciones no hacen nada
y registran un log a nivel debug.

**Hilos (Linux / Wayland / Qt-GTK):**

- `cv2.imshow`, `cv2.waitKey` y `cv2.destroyAllWindows` **no** son seguros fuera del hilo
  que posee la conexión con el display (en la práctica: el hilo principal de la app con Kivy).
  Ejecutarlos desde un hilo de captura o un worker dedicado provoca **violación de segmento**
  con el backend Qt/GTK de HighGUI (mensajes tipo XDG/Wayland + crash).
- La preparación de matrices (PIL, ``cv2.rectangle``/``putText`` sobre ``numpy``) puede
  hacerse en el **hilo de captura**; el resultado se deja en un buffer ``_pending_show`` y
  **solo** el callback periódico del ``Clock`` de Kivy (mismo hilo que la ventana principal)
  aplica ``imshow`` + ``waitKey(1)``.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from print_scanner_app.domain.policies.perforation_alignment import PerforationAlignmentResult
    from print_scanner_app.domain.policies.perforation_roi import RoiSpec

_log = logging.getLogger(__name__)

_WINDOW_FULL = "debug_img_bgr"
_WINDOW_THRESH = "debug_zona_thresh.jpg"
_WINDOW_THRESH_FULL = "debug_thresh_full"

_lock = threading.Lock()
# Último triple BGR listo para mostrar (el hilo de captura escribe; el Clock de Kivy lee).
_pending_show: tuple[object, object, object] | None = None  # np.ndarray x3
_windows_open = False


def _pil_to_bgr_numpy(rgb: Image.Image):
    try:
        import numpy as np
    except ImportError:
        return None
    arr = np.asarray(rgb.convert("RGB"))
    return arr[:, :, ::-1].copy()


def _pil_l_to_numpy(gray: Image.Image):
    try:
        import numpy as np
    except ImportError:
        return None
    return np.asarray(gray.convert("L"))


def _raw_full_thresh_bgr(image_rgb: Image.Image, umbral_grey: int, cv2_mod):
    """Máscara cruda ``gray > umbral_grey`` en frame completo, sin overlays ni filtro de aire."""
    try:
        import numpy as np
    except ImportError:
        return None
    gray = np.asarray(image_rgb.convert("L"))
    t = max(0, min(255, int(umbral_grey)))
    mask = (gray > t).astype(np.uint8) * 255
    try:
        return cv2_mod.cvtColor(mask, cv2_mod.COLOR_GRAY2BGR)
    except Exception:  # noqa: BLE001
        return mask


def show_alignment_debug_windows(
    image_rgb: Image.Image,
    roi: RoiSpec,
    result: PerforationAlignmentResult,
    *,
    umbral_grey: int,
    overlay_help: str,
    overlay_white_px: str,
    logger: logging.Logger | None = None,
) -> bool:
    """
    Construye las vistas BGR y las deja pendientes para el hilo principal de Kivy.

    Ventanas: frame anotado, thresh del ROI (post-filtro), thresh full crudo
    (``gray > umbral_grey``, sin overlays).

    Puede llamarse desde el hilo de captura: **no** llama a ``imshow`` ni ``waitKey``.

    Retorna True si hay datos listos para mostrar (OpenCV/numpy disponibles).
    """
    log = logger or _log
    try:
        import cv2
    except ImportError:
        log.debug("OpenCV no instalado: omitiendo ventanas de debug de alineación")
        return False

    bgr = _pil_to_bgr_numpy(image_rgb)
    if bgr is None:
        log.debug("numpy no disponible: omitiendo ventanas de debug de alineación")
        return False

    cv2_mod = cv2

    eff = result.roi_effective
    cv2_mod.rectangle(bgr, (eff.xi, eff.yi), (eff.xf, eff.yf), (255, 0, 0), 2)
    bxi = getattr(result, "blob_xi", None)
    bxf = getattr(result, "blob_xf", None)
    byi = getattr(result, "blob_yi", None)
    byf = getattr(result, "blob_yf", None)
    if None not in (bxi, bxf, byi, byf):
        cv2_mod.rectangle(
            bgr,
            (int(bxi), int(byi)),
            (int(bxf), int(byf)),
            (0, 255, 255),
            2,
        )
    h_img = bgr.shape[0]
    try:
        font = cv2_mod.FONT_HERSHEY_SIMPLEX
        cv2_mod.putText(
            bgr,
            overlay_help,
            (30, h_img - 20),
            font,
            0.55,
            (0, 255, 0),
            1,
            cv2_mod.LINE_AA,
        )
        cv2_mod.putText(
            bgr,
            overlay_white_px,
            (30, 28),
            font,
            0.7,
            (0, 255, 0),
            2,
            cv2_mod.LINE_AA,
        )
        air_e = getattr(result, "x_air_edge", None)
        content_e = getattr(result, "x_content_edge", None)
        w_rail = getattr(result, "w_rail", 0)
        w_rail_max = getattr(result, "w_rail_max", 0)
        floor = 1 if getattr(result, "rail_floor", False) else 0
        if air_e is not None and content_e is not None:
            cv2_mod.putText(
                bgr,
                f"air={air_e} content={content_e} roi=({eff.xi},{eff.yi})-({eff.xf},{eff.yf})",
                (30, 58),
                font,
                0.5,
                (0, 255, 0),
                1,
                cv2_mod.LINE_AA,
            )
            cv2_mod.putText(
                bgr,
                f"W_rail={w_rail} max={w_rail_max} floor={floor}",
                (30, 82),
                font,
                0.5,
                (0, 255, 0),
                1,
                cv2_mod.LINE_AA,
            )
    except Exception as e:  # noqa: BLE001
        log.debug("putText OpenCV: %s", e)

    thresh_np = _pil_l_to_numpy(result.thresh_roi)
    if thresh_np is None:
        return False

    try:
        if thresh_np.ndim == 2:
            thresh_bgr = cv2_mod.cvtColor(thresh_np, cv2_mod.COLOR_GRAY2BGR)
        else:
            thresh_bgr = thresh_np
    except Exception as e:  # noqa: BLE001
        log.debug("cvtColor thresh debug: %s", e)
        thresh_bgr = thresh_np

    thresh_full_bgr = _raw_full_thresh_bgr(image_rgb, umbral_grey, cv2_mod)
    if thresh_full_bgr is None:
        return False

    try:
        bgr_copy = bgr.copy()
        tb_copy = thresh_bgr.copy()
        tf_copy = thresh_full_bgr.copy()
    except Exception as e:  # noqa: BLE001
        log.debug("copy matrices debug: %s", e)
        return False

    global _pending_show
    with _lock:
        _pending_show = (bgr_copy, tb_copy, tf_copy)
    return True


def _apply_pending_imshow() -> None:
    """Ejecutar solo desde el hilo principal (p. ej. ``Clock`` de Kivy)."""
    global _pending_show, _windows_open
    with _lock:
        pending = _pending_show
        _pending_show = None
    if pending is None:
        return
    bgr, thresh_bgr, thresh_full_bgr = pending
    try:
        import cv2

        cv2.imshow(_WINDOW_FULL, bgr)
        cv2.imshow(_WINDOW_THRESH, thresh_bgr)
        cv2.imshow(_WINDOW_THRESH_FULL, thresh_full_bgr)
        h, w = bgr.shape[:2]
        try:
            cv2.moveWindow(_WINDOW_FULL, 40, 40)
            cv2.moveWindow(_WINDOW_THRESH, min(40 + w + 40, 1600), 40)
            cv2.moveWindow(_WINDOW_THRESH_FULL, 40, min(40 + h + 40, 900))
        except Exception:  # noqa: BLE001
            pass
        _windows_open = True
    except Exception as e:  # noqa: BLE001
        _log.warning("cv2.imshow no disponible (¿sin display?): %s", e)


def poll_alignment_debug_key() -> int | None:
    """
    Debe llamarse **solo** desde el hilo principal de Kivy (mismo que ``Clock``).

    Aplica frames pendientes del hilo de captura, bombea eventos con ``waitKey(1)`` y
    devuelve una tecla si hubo.
    """
    try:
        import cv2
    except ImportError:
        return None

    _apply_pending_imshow()

    global _windows_open
    if not _windows_open:
        return None

    k = cv2.waitKey(1) & 0xFF
    if k in (0, 255):
        return None
    return k


def close_alignment_debug_windows() -> None:
    """Cerrar ventanas; llamar preferentemente desde el hilo principal."""
    global _pending_show, _windows_open
    with _lock:
        _pending_show = None
    try:
        import cv2

        cv2.destroyAllWindows()
    except Exception:  # noqa: BLE001
        pass
    _windows_open = False


def shutdown_alignment_debug_worker() -> None:
    """Compatibilidad con ``on_stop``: no hay hilo worker; solo cerrar ventanas."""
    close_alignment_debug_windows()
