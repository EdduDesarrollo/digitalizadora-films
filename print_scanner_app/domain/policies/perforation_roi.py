"""
ROI de perforación por formato.

8 mm y super 8 reutilizan el preset 16 mm (misma cuadrícula).

La banda Y sigue siendo fija por formato; la X de búsqueda se calcula en runtime
(borde de aire ↔ inicio de contenido) según `PERFORATION_SIDE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

PerforationSide = Literal["left", "right"]

PERFORATION_SIDE_KEY = "PERFORATION_SIDE"
PERFORATION_SIDE_DEFAULT: PerforationSide = "left"
PERFORATION_RAIL_WIDTH_KEY = "PERFORATION_RAIL_WIDTH"
PERFORATION_RAIL_WIDTH_MAX_KEY = "PERFORATION_RAIL_WIDTH_MAX"


@dataclass(frozen=True)
class RoiSpec:
    """Rectángulo en píxeles (origen arriba-izquierda, como PIL). ``xf``/``yf`` exclusivos en crop."""

    xi: int
    yi: int
    xf: int
    yf: int

    def width(self) -> int:
        return max(0, self.xf - self.xi)

    def height(self) -> int:
        return max(0, self.yf - self.yi)


# zona_*_16mm / zona_*_35mm (Y de búsqueda; X es dinámica)
# 16mm: banda histórica 160–240 desplazada 5 px hacia arriba (155–235).
_ROI_16MM = RoiSpec(xi=200, yi=155, xf=290, yf=235)
_ROI_35MM = RoiSpec(xi=175, yi=70, xf=250, yf=155)

UMBRAL_GREY_DEFAULT = 252

# Overlay Kivy (base 1024×768) — rect de perforación; al lado right se espeja en X.
# 16mm: mismo desplazamiento +5 en ry_top (mayor ry = más arriba en pantalla).
_OVERLAY_RECT_16MM = (200.0, 295.0, 310.0, 200.0)  # rx1, ry1_top, rx2, ry2_top
_OVERLAY_RECT_35MM = (180.0, 560.0, 240.0, 490.0)
OVERLAY_BASE_W = 1024.0
OVERLAY_BASE_H = 768.0


def _normalize_format(fmt: str) -> str:
    f = (fmt or "16mm").strip().lower()
    if f in ("8mm", "super8", "super 8"):
        return "16mm"
    return f


def roi_for_format(format_str: str) -> RoiSpec:
    """ROI por defecto según formato (Y fija; xi/xf históricos como referencia)."""
    f = _normalize_format(format_str)
    if f == "35mm":
        return _ROI_35MM
    return _ROI_16MM


def roi_from_config(config: Mapping[str, Any] | None, format_str: str) -> RoiSpec:
    """
    `PERFORATION_ROI` en config.json puede ser un dict por formato, p. ej.:

    ```json
    "PERFORATION_ROI": {
      "16mm": {"xi": 200, "yi": 155, "xf": 290, "yf": 235},
      "35mm": {"xi": 175, "yi": 70, "xf": 250, "yf": 155}
    }
    ```

    Claves omitidas caen al default de `roi_for_format`.
    En la detección dinámica solo `yi`/`yf` anclan la banda vertical.
    """
    base = roi_for_format(format_str)
    if not config:
        return base
    raw = config.get("PERFORATION_ROI")
    if not isinstance(raw, dict):
        return base
    key = _normalize_format(format_str)
    entry = raw.get(key)
    if not isinstance(entry, dict):
        default_e = raw.get("default")
        entry = default_e if isinstance(default_e, dict) else None
    if not isinstance(entry, dict):
        return base

    def _i(name: str, default: int) -> int:
        v = entry.get(name)
        if v is None:
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return RoiSpec(
        xi=_i("xi", base.xi),
        yi=_i("yi", base.yi),
        xf=_i("xf", base.xf),
        yf=_i("yf", base.yf),
    )


def umbral_grey_from_config(config: Mapping[str, Any] | None) -> int:
    """Umbral de gris para binarizar la ROI (clave `UMBRAL_GREY_PERFORACION`, típ. 245)."""
    if not config:
        return UMBRAL_GREY_DEFAULT
    raw = config.get("UMBRAL_GREY_PERFORACION", UMBRAL_GREY_DEFAULT)
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return UMBRAL_GREY_DEFAULT
    return max(0, min(255, v))


def side_from_config(config: Mapping[str, Any] | None) -> PerforationSide:
    """Lado del rail: `left` (default) o `right`."""
    if not config:
        return PERFORATION_SIDE_DEFAULT
    raw = str(config.get(PERFORATION_SIDE_KEY, PERFORATION_SIDE_DEFAULT) or "").strip().lower()
    if raw in ("right", "derecha", "r"):
        return "right"
    return "left"


def w_rail_default_for_format(format_str: str) -> int:
    """Ancho mínimo del rail = ancho del ROI fijo histórico por formato (16→90, 35→75)."""
    return max(1, roi_for_format(format_str).width())


def w_rail_from_config(config: Mapping[str, Any] | None, format_str: str) -> int:
    """
    Ancho mínimo garantizado desde el borde de aire hacia el film.

    Override en config:

    ```json
    "PERFORATION_RAIL_WIDTH": { "16mm": 90, "35mm": 75 }
    ```

    También acepta entero global o ``w_rail`` dentro de ``PERFORATION_ROI.<formato>``.
    """
    base = w_rail_default_for_format(format_str)
    if not config:
        return base
    key = _normalize_format(format_str)

    raw = config.get(PERFORATION_RAIL_WIDTH_KEY)
    if isinstance(raw, dict):
        entry = raw.get(key, raw.get("default"))
        if entry is not None:
            try:
                return max(1, int(entry))
            except (TypeError, ValueError):
                pass
    elif raw is not None:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass

    roi_raw = config.get("PERFORATION_ROI")
    if isinstance(roi_raw, dict):
        entry = roi_raw.get(key)
        if not isinstance(entry, dict):
            entry = roi_raw.get("default") if isinstance(roi_raw.get("default"), dict) else None
        if isinstance(entry, dict) and entry.get("w_rail") is not None:
            try:
                return max(1, int(entry["w_rail"]))
            except (TypeError, ValueError):
                pass
    return base


def w_rail_max_from_config(
    config: Mapping[str, Any] | None,
    format_str: str,
    *,
    w_rail: int | None = None,
) -> int:
    """
    Techo del rail (default ``2 * W_rail``).

    ```json
    "PERFORATION_RAIL_WIDTH_MAX": { "16mm": 180, "35mm": 150 }
    ```
    """
    rail = int(w_rail) if w_rail is not None else w_rail_from_config(config, format_str)
    base = max(rail, rail * 2)
    if not config:
        return base
    key = _normalize_format(format_str)
    raw = config.get(PERFORATION_RAIL_WIDTH_MAX_KEY)
    if isinstance(raw, dict):
        entry = raw.get(key, raw.get("default"))
        if entry is not None:
            try:
                return max(rail, int(entry))
            except (TypeError, ValueError):
                pass
    elif raw is not None:
        try:
            return max(rail, int(raw))
        except (TypeError, ValueError):
            pass
    roi_raw = config.get("PERFORATION_ROI")
    if isinstance(roi_raw, dict):
        entry = roi_raw.get(key)
        if not isinstance(entry, dict):
            entry = roi_raw.get("default") if isinstance(roi_raw.get("default"), dict) else None
        if isinstance(entry, dict) and entry.get("w_rail_max") is not None:
            try:
                return max(rail, int(entry["w_rail_max"]))
            except (TypeError, ValueError):
                pass
    return base


def overlay_rect_for_format(format_str: str, side: PerforationSide = "left") -> tuple[float, float, float, float]:
    """
    Rectángulo de cuadrícula Kivy (rx1, ry1_top, rx2, ry2_top) en espacio base 1024×768.
    Con ``side=right`` espeja solo X: ``x' = base_w - x``.
    """
    f = _normalize_format(format_str)
    rx1, ry1, rx2, ry2 = _OVERLAY_RECT_35MM if f == "35mm" else _OVERLAY_RECT_16MM
    if side == "right":
        rx1, rx2 = mirror_x_pair(rx1, rx2, OVERLAY_BASE_W)
    return rx1, ry1, rx2, ry2


def mirror_x_pair(x1: float, x2: float, base_w: float = OVERLAY_BASE_W) -> tuple[float, float]:
    a = base_w - x2
    b = base_w - x1
    return (min(a, b), max(a, b))
