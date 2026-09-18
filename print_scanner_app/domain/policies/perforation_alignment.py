"""
Alineación por blob de sprocket (Y fija de formato, X dinámica).

1. Banda Y = ancla de formato (p. ej. 160–240 en 16 mm). El ROI en Y no se mueve.
2. Aire en X = primera meseta blanca (``frac > umbral_grey``, ancho 1..N) tras
   chasis oscuro. Si existe, blobs solo en el rail a continuación.
3. Sin aire: primer blob compacto desde el centro hacia el ``side``.
4. KS cortado por el borde de la banda: se cuenta el **trozo** dentro de Y
   (aspect más permisivo si toca yi/yf de la banda).
5. Sin blob → piso ``w_rail`` en el borde X del ``side`` (Y sigue fija).

``white_pixel_count`` = área del blob (o trozo); ``aligned`` si supera el umbral.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image

from print_scanner_app.domain.policies.perforation_roi import PerforationSide, RoiSpec

_BLOB_MARGIN_PX = 4
_ASPECT_MIN = 0.55
_ASPECT_MAX = 1.8
# KS a caballo del borde Y: el trozo queda más ancho que alto.
_ASPECT_MAX_Y_CLIPPED = 4.0
_SOLIDITY_MIN = 0.80
_HEIGHT_FRAC_MAX = 0.90
_RING_PX = 2
_AIR_COLUMN_WHITE_FRAC = 0.55
_AIR_MESETA_MAX_PX = 48


@dataclass(frozen=True)
class PerforationAlignmentResult:
    """Resultado del análisis sobre una imagen RGB."""

    white_pixel_count: int
    aligned: bool
    thresh_roi: Image.Image
    roi_effective: RoiSpec
    side: PerforationSide = "left"
    x_air_edge: Optional[int] = None
    x_content_edge: Optional[int] = None
    blob_area: int = 0
    blob_xi: Optional[int] = None
    blob_xf: Optional[int] = None
    blob_yi: Optional[int] = None
    blob_yf: Optional[int] = None
    w_rail: int = 0
    w_rail_max: int = 0
    rail_floor: bool = False


@dataclass(frozen=True)
class SearchRoiResult:
    roi: RoiSpec
    x_air_edge: int
    x_content_edge: int
    rail_floor: bool
    w_rail: int
    w_rail_max: int
    blob_area: int = 0
    blob_xi: Optional[int] = None
    blob_xf: Optional[int] = None
    blob_yi: Optional[int] = None
    blob_yf: Optional[int] = None


@dataclass(frozen=True)
class _BlobCand:
    area: int
    xi: int
    xf: int  # exclusivo
    yi: int
    yf: int  # exclusivo (coords dentro de la banda Y fija)
    solidity: float
    ring_score: float
    mask: object  # np.ndarray bool del tamaño de la banda


@dataclass(frozen=True)
class _Cc:
    area: int
    xi: int
    xf: int
    yi: int
    yf: int
    mask: object


@dataclass(frozen=True)
class _SprocketHit:
    blob: _BlobCand
    x_air_edge: Optional[int]


def _clip_y_band(width: int, height: int, y_roi: RoiSpec) -> Tuple[int, int]:
    yi = max(0, min(height - 1, y_roi.yi))
    yf = max(yi + 1, min(height, y_roi.yf))
    return yi, yf


def _clip_roi_to_image(width: int, height: int, roi: RoiSpec) -> RoiSpec:
    xi = max(0, min(width - 1, roi.xi))
    yi = max(0, min(height - 1, roi.yi))
    xf = max(xi + 1, min(width, roi.xf))
    yf = max(yi + 1, min(height, roi.yf))
    return RoiSpec(xi=xi, yi=yi, xf=xf, yf=yf)


def _as_gray_array(image_rgb: Image.Image):
    try:
        import numpy as np
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("numpy es requerido para detección de perforación") from e
    gray = image_rgb.convert("L")
    return np.asarray(gray, dtype=np.float32)


def _area_bounds(band_h: int, rail_max: int) -> tuple[int, int]:
    h = max(1, int(band_h))
    amin = max(200, int(0.15 * h * h))
    amax = max(amin + 1, int(0.55 * h * max(1, int(rail_max))))
    return amin, amax


def _convex_hull(points):
    pts = sorted(set((int(x), int(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[int, int]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[int, int]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _polygon_area(hull) -> float:
    n = len(hull)
    if n < 3:
        return float(max(n, 1))
    acc = 0.0
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def _solidity(ys, xs, area: int, bw: int, bh: int) -> float:
    bbox_a = max(1, int(bw) * int(bh))
    extent = float(area) / float(bbox_a)
    if area > 4000:
        return extent
    hull = _convex_hull(zip(xs.tolist(), ys.tolist()))
    ha = _polygon_area(hull)
    if ha < 1.0:
        return extent
    return min(1.0, float(area) / ha)


def _label_4(mask):
    import numpy as np

    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    n = 0
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or labels[y, x] != 0:
                continue
            n += 1
            stack = [(y, x)]
            labels[y, x] = n
            while stack:
                cy, cx = stack.pop()
                if cy > 0 and mask[cy - 1, cx] and labels[cy - 1, cx] == 0:
                    labels[cy - 1, cx] = n
                    stack.append((cy - 1, cx))
                if cy + 1 < h and mask[cy + 1, cx] and labels[cy + 1, cx] == 0:
                    labels[cy + 1, cx] = n
                    stack.append((cy + 1, cx))
                if cx > 0 and mask[cy, cx - 1] and labels[cy, cx - 1] == 0:
                    labels[cy, cx - 1] = n
                    stack.append((cy, cx - 1))
                if cx + 1 < w and mask[cy, cx + 1] and labels[cy, cx + 1] == 0:
                    labels[cy, cx + 1] = n
                    stack.append((cy, cx + 1))
    return labels, n


def _ring_score(band, blob_mask, xi: int, xf: int, yi: int, yf: int) -> float:
    import numpy as np

    h, w = band.shape
    r = _RING_PX
    y0 = max(0, yi - r)
    y1 = min(h, yf + r)
    x0 = max(0, xi - r)
    x1 = min(w, xf + r)
    region = np.zeros((h, w), dtype=bool)
    region[y0:y1, x0:x1] = True
    ring = region & ~blob_mask
    if not ring.any() or not blob_mask.any():
        return 0.0
    interior = float(band[blob_mask].mean())
    outside = float(band[ring].mean())
    return interior - outside


def _column_bright_mask(band, umbral_grey: int, white_frac_thr: float = _AIR_COLUMN_WHITE_FRAC):
    t = max(0, min(255, int(umbral_grey)))
    return (band > t).mean(axis=0) >= float(white_frac_thr)


def _find_thin_air_left(bright) -> Optional[int]:
    w = int(len(bright))
    i = 0
    while i < w and not bool(bright[i]):
        i += 1
    if i >= w:
        return None
    start = i
    while i < w and bool(bright[i]):
        i += 1
    width = i - start
    if width < 1 or width > _AIR_MESETA_MAX_PX:
        return None
    return i - 1


def _find_thin_air_right(bright) -> Optional[int]:
    w = int(len(bright))
    i = w - 1
    while i >= 0 and not bool(bright[i]):
        i -= 1
    if i < 0:
        return None
    end = i
    while i >= 0 and bool(bright[i]):
        i -= 1
    width = end - i
    if width < 1 or width > _AIR_MESETA_MAX_PX:
        return None
    return i + 1


def _compact_cand_from_cc(band, cc: _Cc, amin: int, amax: int) -> _BlobCand | None:
    import numpy as np

    area = cc.area
    if area < amin or area > amax:
        return None
    bw = cc.xf - cc.xi
    bh = cc.yf - cc.yi
    if bh < 1 or bw < 1:
        return None
    band_h = int(band.shape[0])
    if bh > int(_HEIGHT_FRAC_MAX * max(1, band_h)):
        return None
    y_clipped = cc.yi <= 0 or cc.yf >= band_h
    aspect = bw / float(bh)
    amax_asp = _ASPECT_MAX_Y_CLIPPED if y_clipped else _ASPECT_MAX
    if aspect < _ASPECT_MIN or aspect > amax_asp:
        return None
    ys, xs = np.nonzero(cc.mask)
    sol = _solidity(ys, xs, area, bw, bh)
    if sol < _SOLIDITY_MIN:
        return None
    return _BlobCand(
        area=area,
        xi=cc.xi,
        xf=cc.xf,
        yi=cc.yi,
        yf=cc.yf,
        solidity=sol,
        ring_score=_ring_score(band, cc.mask, cc.xi, cc.xf, cc.yi, cc.yf),
        mask=cc.mask,
    )


def _iter_components(band, umbral_grey: int) -> list[_Cc]:
    import numpy as np

    t = max(0, min(255, int(umbral_grey)))
    mask = band > t
    labels, nlab = _label_4(mask)
    out: list[_Cc] = []
    for lab in range(1, nlab + 1):
        bm = labels == lab
        area = int(bm.sum())
        if area < 1:
            continue
        ys, xs = np.nonzero(bm)
        out.append(
            _Cc(
                area=area,
                xi=int(xs.min()),
                xf=int(xs.max()) + 1,
                yi=int(ys.min()),
                yf=int(ys.max()) + 1,
                mask=bm,
            )
        )
    return out


def _compact_blobs(band, umbral_grey: int, rail_max: int) -> list[_BlobCand]:
    amin, amax = _area_bounds(band.shape[0], rail_max)
    ccs = _iter_components(band, umbral_grey)
    out: list[_BlobCand] = []
    for cc in ccs:
        cand = _compact_cand_from_cc(band, cc, amin, amax)
        if cand is not None:
            out.append(cand)
    return out


def _pick_in_rail_after_air(
    cands: list[_BlobCand],
    side: PerforationSide,
    x_air: int,
    rail_max: int,
    frame_w: int,
) -> _BlobCand | None:
    if side == "right":
        x_hi = x_air
        x_lo = max(0, x_air - rail_max)
        in_rail = [c for c in cands if x_lo <= (c.xi + c.xf) // 2 <= x_hi]
        if not in_rail:
            in_rail = [c for c in cands if c.xf > x_lo and c.xi >= x_lo]
        if not in_rail:
            return None
        return max(in_rail, key=lambda c: (c.xf, c.ring_score, c.area))

    x_lo = x_air + 1
    x_hi = min(frame_w, x_air + 1 + rail_max)
    in_rail = [c for c in cands if x_lo <= (c.xi + c.xf) // 2 < x_hi]
    if not in_rail:
        in_rail = [c for c in cands if c.xf > x_lo and c.xi < x_hi]
    if not in_rail:
        return None
    return min(in_rail, key=lambda c: (c.xi, -c.ring_score, -c.area))


def _pick_from_center_toward_side(
    cands: list[_BlobCand],
    side: PerforationSide,
    frame_w: int,
) -> _BlobCand | None:
    mid = frame_w // 2
    if side == "right":
        half = [c for c in cands if c.xi >= mid]
        if not half:
            return None
        return min(half, key=lambda c: (c.xi, -c.ring_score, -c.area))
    half = [c for c in cands if c.xf <= mid]
    if not half:
        half = [c for c in cands if (c.xi + c.xf) // 2 < mid]
    if not half:
        return None
    return max(half, key=lambda c: (c.xi, c.ring_score, c.area))


def _find_sprocket(
    band,
    umbral_grey: int,
    side: PerforationSide,
    rail_max: int,
) -> _SprocketHit | None:
    frame_w = int(band.shape[1])
    cands = _compact_blobs(band, umbral_grey, rail_max)
    bright = _column_bright_mask(band, umbral_grey)
    if side == "right":
        x_air = _find_thin_air_right(bright)
    else:
        x_air = _find_thin_air_left(bright)

    if x_air is not None:
        blob = _pick_in_rail_after_air(cands, side, x_air, rail_max, frame_w)
        if blob is not None:
            return _SprocketHit(blob=blob, x_air_edge=x_air)

    blob = _pick_from_center_toward_side(cands, side, frame_w)
    if blob is None:
        return None
    return _SprocketHit(blob=blob, x_air_edge=None)


def _floor_roi(
    w: int,
    yi: int,
    yf: int,
    side: PerforationSide,
    rail: int,
    rail_max: int,
) -> SearchRoiResult:
    if side == "right":
        xf = w
        xi = max(0, w - rail)
        return SearchRoiResult(
            roi=RoiSpec(xi=xi, yi=yi, xf=xf, yf=yf),
            x_air_edge=max(0, w - 1),
            x_content_edge=xi,
            rail_floor=True,
            w_rail=rail,
            w_rail_max=rail_max,
        )
    xi = 0
    xf = min(w, rail)
    return SearchRoiResult(
        roi=RoiSpec(xi=xi, yi=yi, xf=max(xi + 1, xf), yf=yf),
        x_air_edge=0,
        x_content_edge=int(max(xi + 1, xf)),
        rail_floor=True,
        w_rail=rail,
        w_rail_max=rail_max,
    )


def _roi_from_blob(
    w: int,
    yi_nom: int,
    yf_nom: int,
    blob: _BlobCand,
    side: PerforationSide,
    rail: int,
    rail_max: int,
    x_air_edge: Optional[int] = None,
) -> SearchRoiResult:
    """X sigue al blob; Y queda fija en la banda de formato."""
    m = _BLOB_MARGIN_PX
    xi = max(0, blob.xi - m)
    xf = min(w, blob.xf + m)
    width = xf - xi
    if width < rail:
        extra = rail - width
        if side == "right":
            xi = max(0, xi - extra)
        else:
            xf = min(w, xf + extra)
    if xf - xi > rail_max:
        if side == "right":
            xi = xf - rail_max
        else:
            xf = xi + rail_max
    if xf <= xi:
        xf = min(w, xi + 1)
    byi = yi_nom + blob.yi
    byf = yi_nom + blob.yf
    if x_air_edge is not None:
        air = int(x_air_edge)
    elif side == "left":
        air = max(0, xi - 1)
    else:
        air = min(w - 1, xf)
    return SearchRoiResult(
        roi=RoiSpec(xi=xi, yi=yi_nom, xf=xf, yf=yf_nom),
        x_air_edge=air,
        x_content_edge=xf if side == "left" else xi,
        rail_floor=False,
        w_rail=rail,
        w_rail_max=rail_max,
        blob_area=blob.area,
        blob_xi=blob.xi,
        blob_xf=blob.xf,
        blob_yi=byi,
        blob_yf=byf,
    )


def compute_search_roi(
    gray,
    *,
    yi: int,
    yf: int,
    side: PerforationSide,
    umbral_grey: int,
    w_rail: int,
    w_rail_max: int | None = None,
) -> SearchRoiResult:
    """ROI: X del sprocket, Y = banda fija; sin blob → piso X en el borde."""
    h, w = gray.shape
    yi = max(0, min(h - 1, yi))
    yf = max(yi + 1, min(h, yf))
    rail = max(1, int(w_rail))
    rail_max = max(rail, int(w_rail_max) if w_rail_max is not None else rail * 2)
    side_n: PerforationSide = "right" if side == "right" else "left"
    band = gray[yi:yf, :]
    hit = _find_sprocket(band, umbral_grey, side_n, rail_max)
    if hit is None:
        return _floor_roi(w, yi, yf, side_n, rail, rail_max)
    return _roi_from_blob(
        w, yi, yf, hit.blob, side_n, rail, rail_max, x_air_edge=hit.x_air_edge
    )


def analyze_perforation_alignment(
    image_rgb: Image.Image,
    y_roi: RoiSpec,
    *,
    umbral_grey: int,
    umbral_px_blancos: int,
    side: PerforationSide = "left",
    w_rail: int = 90,
    w_rail_max: int | None = None,
) -> PerforationAlignmentResult:
    """``white_pixel_count`` = área del blob/trozo; ROI Y fija de ``y_roi``."""
    import numpy as np

    if image_rgb.mode != "RGB":
        image_rgb = image_rgb.convert("RGB")
    w, h = image_rgb.size
    side_n: PerforationSide = "right" if side == "right" else "left"
    yi, yf = _clip_y_band(w, h, y_roi)
    gray = _as_gray_array(image_rgb)
    rail = max(1, int(w_rail))
    rail_max = max(rail, int(w_rail_max) if w_rail_max is not None else rail * 2)

    band = gray[yi:yf, :]
    hit = _find_sprocket(band, umbral_grey, side_n, rail_max)
    if hit is None:
        search = _floor_roi(w, yi, yf, side_n, rail, rail_max)
        eff = _clip_roi_to_image(w, h, search.roi)
        empty = np.zeros((max(1, eff.height()), max(1, eff.width())), dtype=np.uint8)
        return PerforationAlignmentResult(
            white_pixel_count=0,
            aligned=False,
            thresh_roi=Image.fromarray(empty, mode="L"),
            roi_effective=eff,
            side=side_n,
            x_air_edge=search.x_air_edge,
            x_content_edge=search.x_content_edge,
            blob_area=0,
            w_rail=rail,
            w_rail_max=rail_max,
            rail_floor=True,
        )

    blob = hit.blob
    search = _roi_from_blob(
        w, yi, yf, blob, side_n, rail, rail_max, x_air_edge=hit.x_air_edge
    )
    eff = _clip_roi_to_image(w, h, search.roi)
    crop_h = max(1, eff.yf - eff.yi)
    crop_w = max(1, eff.xf - eff.xi)
    # Máscara del blob relativa a la banda fija (= ROI Y).
    rel_yi = 0
    rel_yf = band.shape[0]
    rel_xi = max(0, eff.xi)
    rel_xf = min(w, eff.xi + crop_w)
    crop_mask = blob.mask[rel_yi:rel_yf, rel_xi:rel_xf]
    thresh_u8 = np.zeros((crop_h, crop_w), dtype=np.uint8)
    hh, ww = crop_mask.shape
    # crop_h == band height when ROI Y == banda
    thresh_u8[: min(hh, crop_h), : min(ww, crop_w)] = (
        crop_mask[: min(hh, crop_h), : min(ww, crop_w)].astype(np.uint8) * 255
    )
    count = int(blob.area)
    return PerforationAlignmentResult(
        white_pixel_count=count,
        aligned=count > int(umbral_px_blancos),
        thresh_roi=Image.fromarray(thresh_u8, mode="L"),
        roi_effective=eff,
        side=side_n,
        x_air_edge=search.x_air_edge,
        x_content_edge=search.x_content_edge,
        blob_area=count,
        blob_xi=search.blob_xi,
        blob_xf=search.blob_xf,
        blob_yi=search.blob_yi,
        blob_yf=search.blob_yf,
        w_rail=rail,
        w_rail_max=rail_max,
        rail_floor=False,
    )
