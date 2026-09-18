"""Tests de detección: aire fino + fallback centro→lado."""

from __future__ import annotations

import numpy as np
from PIL import Image

from print_scanner_app.domain.policies.perforation_alignment import (
    analyze_perforation_alignment,
    compute_search_roi,
)
from print_scanner_app.domain.policies.perforation_roi import RoiSpec


def _y_roi(yi: int = 40, yf: int = 120) -> RoiSpec:
    return RoiSpec(xi=0, yi=yi, xf=10, yf=yf)


def _synth_left(
    *,
    w: int = 400,
    h: int = 200,
    hole_x: int = 40,
    hole_w: int = 36,
    hole_y: int = 50,
    hole_h: int = 40,
    content_x: int = 160,
    air_xf: int = 8,
) -> Image.Image:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :air_xf] = 255
    arr[:, air_xf:content_x] = 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    arr[:, content_x:] = 100
    arr[:, content_x + 20 : content_x + 80] = 130
    return Image.fromarray(arr, mode="RGB")


def _synth_right(
    *,
    w: int = 400,
    h: int = 200,
    content_xf: int = 240,
    hole_x: int = 320,
    hole_w: int = 36,
    hole_y: int = 50,
    hole_h: int = 40,
    air_xi: int = 392,
) -> Image.Image:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :content_xf] = 100
    arr[:, content_xf:air_xi] = 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    arr[:, air_xi:] = 255
    return Image.fromarray(arr, mode="RGB")


def test_left_blob_area_is_sprocket():
    img = _synth_left()
    hole_area = 36 * 40
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=hole_area - 10,
        side="left",
        w_rail=90,
    )
    assert res.aligned
    assert res.white_pixel_count == hole_area
    assert res.blob_area == hole_area
    assert res.blob_xi == 40
    assert res.side == "left"
    assert res.rail_floor is False
    assert res.roi_effective.xi <= 40
    assert res.roi_effective.xf >= 76
    assert res.x_air_edge is not None and res.x_air_edge < 40


def test_below_threshold_still_reports_blob_area():
    img = _synth_left()
    hole_area = 36 * 40
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=hole_area + 50,
        side="left",
        w_rail=90,
    )
    assert not res.aligned
    assert res.white_pixel_count == hole_area


def test_no_sprocket_is_not_aligned():
    img = _synth_left()
    arr = np.array(img)
    arr[50:90, 40:76] = 40
    img2 = Image.fromarray(arr, mode="RGB")
    res = analyze_perforation_alignment(
        img2,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    assert not res.aligned
    assert res.white_pixel_count == 0
    assert res.rail_floor is True


def test_with_thin_air_prefers_rail_sprocket_not_inner():
    img = _synth_left(hole_x=40, hole_w=36, hole_h=40)
    arr = np.array(img)
    arr[50:90, 100:136] = 255
    img2 = Image.fromarray(arr, mode="RGB")
    left_area = 36 * 40
    res = analyze_perforation_alignment(
        img2,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    assert res.white_pixel_count == left_area
    assert res.blob_xi == 40
    assert res.aligned


def test_right_side_picks_rightmost_sprocket():
    img = _synth_right()
    hole_area = 36 * 40
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=hole_area - 10,
        side="right",
        w_rail=75,
    )
    assert res.aligned
    assert res.side == "right"
    assert res.white_pixel_count == hole_area
    assert res.blob_xf == 356


def test_partial_sprocket_in_y_band_counts_overlap():
    img = _synth_left(hole_y=90, hole_h=50, hole_x=40, hole_w=36)
    # banda fija 40-120 → overlap y 90..119 = 30 * 36 = 1080
    partial = 30 * 36
    res = analyze_perforation_alignment(
        img,
        _y_roi(40, 120),
        umbral_grey=245,
        umbral_px_blancos=partial - 10,
        side="left",
        w_rail=90,
    )
    assert res.white_pixel_count == partial
    assert res.aligned
    assert res.roi_effective.yi == 40
    assert res.roi_effective.yf == 120
    assert res.blob_xi == 40


def test_saturated_rail_with_dark_ring_selects_hole():
    """Rail clipado a 255; anillo oscuro 4-conectado aísla el sprocket."""
    w, h = 500, 200
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, 0:6] = 255  # aire fino
    arr[:, 6:200] = 255
    hx, hy, hw, hh = 110, 52, 36, 40
    arr[hy - 2 : hy + hh + 2, hx - 2 : hx + hw + 2] = 20
    arr[hy : hy + hh, hx : hx + hw] = 255
    arr[:, 200:] = 80
    img = Image.fromarray(arr, mode="RGB")
    hole_area = hw * hh
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=hole_area - 10,
        side="left",
        w_rail=90,
    )
    assert res.aligned
    assert res.white_pixel_count == hole_area
    assert res.roi_effective.xi <= hx
    assert res.roi_effective.xf >= hx + hw
    assert res.blob_xi == hx


def test_thick_chassis_air_rejected_falls_back_to_center_scan():
    """Banda blanca gruesa (=chasis) no cuenta como aire; se elige KS desde el centro."""
    w, h = 600, 200
    arr = np.full((h, w, 3), 30, dtype=np.uint8)
    arr[:, :40] = 255  # chasis > 15 px → no aire fino
    arr[:, 560:] = 255  # aire derecho distractor
    hole_x, hole_w, hole_y, hole_h = 120, 36, 50, 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    img = Image.fromarray(arr, mode="RGB")
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=220,
        umbral_px_blancos=hole_w * hole_h - 50,
        side="left",
        w_rail=90,
    )
    assert res.rail_floor is False
    assert res.blob_xi == hole_x
    assert res.white_pixel_count == hole_w * hole_h
    assert res.aligned
    assert res.roi_effective.xi < w // 2
    assert res.roi_effective.xf < 400


def test_does_not_pick_right_air_when_side_left():
    """Regresión: side=left no debe clavar ROI en el aire derecho del frame."""
    w, h = 1000, 200
    arr = np.full((h, w, 3), 40, dtype=np.uint8)
    arr[:, :50] = 255
    arr[:, 900:] = 255
    hole_x, hole_w, hole_y, hole_h = 180, 36, 50, 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    img = Image.fromarray(arr, mode="RGB")
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=220,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    assert res.blob_xi == hole_x
    assert res.roi_effective.xi < 400
    assert res.roi_effective.xf < 500
    assert res.roi_effective.xi < w // 2


def test_no_air_center_scan_finds_left_sprocket():
    """Sin meseta de aire: primer blob compacto desde el centro hacia left."""
    w, h = 600, 200
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :] = 50
    hole_x, hole_w, hole_y, hole_h = 200, 36, 50, 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    img = Image.fromarray(arr, mode="RGB")
    search = compute_search_roi(
        np.asarray(img.convert("L"), dtype=np.float32),
        yi=40,
        yf=120,
        side="left",
        umbral_grey=252,
        w_rail=90,
    )
    assert search.rail_floor is False
    assert search.blob_xi == hole_x
    assert search.roi.xi <= hole_x
    assert search.roi.xf >= hole_x + hole_w
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=252,
        umbral_px_blancos=hole_w * hole_h - 50,
        side="left",
        w_rail=90,
    )
    assert res.white_pixel_count == hole_w * hole_h
    assert res.aligned


def test_shifted_film_without_air_finds_sprocket():
    w, h = 600, 200
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, 220:280] = 40
    hole_x, hole_w, hole_y, hole_h = 230, 36, 50, 40
    arr[hole_y : hole_y + hole_h, hole_x : hole_x + hole_w] = 255
    arr[:, 280:] = 90
    img = Image.fromarray(arr, mode="RGB")
    search = compute_search_roi(
        np.asarray(img.convert("L"), dtype=np.float32),
        yi=40,
        yf=120,
        side="left",
        umbral_grey=252,
        w_rail=90,
    )
    assert search.roi.xi <= hole_x
    assert search.roi.xf >= hole_x + hole_w
    assert search.roi.xi > 50
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=252,
        umbral_px_blancos=hole_w * hole_h - 50,
        side="left",
        w_rail=90,
    )
    assert res.white_pixel_count == hole_w * hole_h
    assert res.aligned


def test_full_height_white_stripe_without_sprocket_floors():
    """Franja blanca a altura de banda sin blob compacto → no inventa sprocket."""
    w, h = 400, 200
    arr = np.full((h, w, 3), 30, dtype=np.uint8)
    arr[40:120, 40:160] = 255
    img = Image.fromarray(arr, mode="RGB")
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    assert not res.aligned
    assert res.white_pixel_count == 0
    assert res.rail_floor is True


def test_debug_mask_matches_blob_pixels():
    img = _synth_left()
    res = analyze_perforation_alignment(
        img,
        _y_roi(),
        umbral_grey=245,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    mask = np.asarray(res.thresh_roi)
    assert int((mask > 0).sum()) == res.white_pixel_count


def test_y_band_clips():
    img = _synth_left()
    res = analyze_perforation_alignment(
        img,
        RoiSpec(0, -10, 10, 5000),
        umbral_grey=245,
        umbral_px_blancos=100,
        side="left",
        w_rail=90,
    )
    assert 0 <= res.roi_effective.yi < res.roi_effective.yf <= 200


def test_threshold_strict_greater_tiny_is_ignored():
    w, h = 200, 120
    arr = np.full((h, w, 3), 40, dtype=np.uint8)
    arr[50:51, 40:41] = 255
    img = Image.fromarray(arr, mode="RGB")
    res = analyze_perforation_alignment(
        img,
        _y_roi(30, 90),
        umbral_grey=245,
        umbral_px_blancos=0,
        side="left",
        w_rail=60,
    )
    assert not res.aligned
    assert res.white_pixel_count == 0
    arr2 = arr.copy()
    arr2[45:85, 30:66] = 255
    img2 = Image.fromarray(arr2, mode="RGB")
    res2 = analyze_perforation_alignment(
        img2,
        _y_roi(30, 90),
        umbral_grey=245,
        umbral_px_blancos=20,
        side="left",
        w_rail=60,
    )
    assert res2.aligned
    assert res2.white_pixel_count == 36 * 40


def test_ks_clipped_by_fixed_y_counts_partial_keeps_roi_y():
    """KS a caballo de 160–240: cuenta el trozo; ROI Y sigue fija."""
    w, h = 960, 640
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, 164:180] = 255
    hx, hy, hw, hh = 216, 129, 65, 53
    arr[hy : hy + hh, hx : hx + hw] = 255
    img = Image.fromarray(arr, mode="RGB")
    # overlap en banda: y 160..182 → 22 * 65
    partial = 22 * 65
    res = analyze_perforation_alignment(
        img,
        RoiSpec(0, 160, 10, 240),
        umbral_grey=220,
        umbral_px_blancos=1000,
        side="left",
        w_rail=90,
    )
    assert res.rail_floor is False
    assert res.blob_xi == hx
    assert res.white_pixel_count == partial
    assert res.roi_effective.yi == 160
    assert res.roi_effective.yf == 240
    assert res.roi_effective.xi > 90
    assert res.blob_yi == 160  # clip al borde superior de la banda
    assert res.x_air_edge is not None and 164 <= res.x_air_edge <= 179


def test_real_thresh_full_fixture_finds_left_sprocket():
    """Regresión contra captura debug_thresh_full (aire + KS izquierda, Y fija)."""
    from pathlib import Path

    path = Path(
        "/home/cintel/.cursor/projects/home-cintel-Documentos-digitalizadora-films-dev"
        "/assets/image-c556e978-e69b-4985-9d13-79afcfc4f460.png"
    )
    if not path.is_file():
        return
    gray = np.asarray(Image.open(path).convert("L"))
    if gray.shape[0] < 400 or gray.shape[1] < 700:
        return
    rgb = np.stack([gray, gray, gray], axis=-1)
    img = Image.fromarray(rgb, mode="RGB")
    res = analyze_perforation_alignment(
        img,
        RoiSpec(0, 160, 10, 240),
        umbral_grey=220,
        umbral_px_blancos=1000,
        side="left",
        w_rail=90,
    )
    assert res.rail_floor is False
    assert res.blob_xi is not None and 200 <= res.blob_xi <= 250
    assert res.roi_effective.yi == 160
    assert res.roi_effective.yf == 240
    assert res.roi_effective.xi > 100
    assert res.white_pixel_count > 1000
