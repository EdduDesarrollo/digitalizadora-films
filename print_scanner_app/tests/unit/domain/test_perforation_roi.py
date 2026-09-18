from print_scanner_app.domain.policies.perforation_roi import (
    OVERLAY_BASE_W,
    PERFORATION_RAIL_WIDTH_KEY,
    PERFORATION_RAIL_WIDTH_MAX_KEY,
    PERFORATION_SIDE_KEY,
    RoiSpec,
    UMBRAL_GREY_DEFAULT,
    mirror_x_pair,
    overlay_rect_for_format,
    roi_for_format,
    roi_from_config,
    side_from_config,
    umbral_grey_from_config,
    w_rail_default_for_format,
    w_rail_from_config,
    w_rail_max_from_config,
)


def test_roi_16mm_differs_from_35mm():
    r16 = roi_for_format("16mm")
    r35 = roi_for_format("35mm")
    assert r16 != r35
    assert r16.xi == 200 and r35.xi == 175
    assert r16.yi == 155 and r16.yf == 235


def test_overlay_16mm_shifted_up_with_roi():
    rx1, ry1, rx2, ry2 = overlay_rect_for_format("16mm", "left")
    assert (rx1, ry1, rx2, ry2) == (200.0, 295.0, 310.0, 200.0)


def test_roi_8mm_uses_16mm_preset():
    assert roi_for_format("8mm") == roi_for_format("16mm")


def test_roi_from_config_override_partial():
    cfg = {
        "PERFORATION_ROI": {
            "16mm": {"xi": 201},
        }
    }
    r = roi_from_config(cfg, "16mm")
    assert r.xi == 201
    assert r.xf == 290


def test_roi_from_config_default_key():
    cfg = {"PERFORATION_ROI": {"default": {"xi": 1, "yi": 2, "xf": 10, "yf": 20}}}
    r = roi_from_config(cfg, "35mm")
    assert r == RoiSpec(xi=1, yi=2, xf=10, yf=20)


def test_umbral_grey_from_config():
    assert umbral_grey_from_config({}) == UMBRAL_GREY_DEFAULT
    assert umbral_grey_from_config({"UMBRAL_GREY_PERFORACION": 128}) == 128
    assert umbral_grey_from_config({"UMBRAL_GREY_PERFORACION": 999}) == 255


def test_side_from_config_default_left():
    assert side_from_config(None) == "left"
    assert side_from_config({}) == "left"
    assert side_from_config({PERFORATION_SIDE_KEY: "right"}) == "right"
    assert side_from_config({PERFORATION_SIDE_KEY: "LEFT"}) == "left"


def test_mirror_x_pair():
    a, b = mirror_x_pair(200, 310, OVERLAY_BASE_W)
    assert a == OVERLAY_BASE_W - 310
    assert b == OVERLAY_BASE_W - 200


def test_overlay_rect_mirrors_on_right():
    left = overlay_rect_for_format("16mm", "left")
    right = overlay_rect_for_format("16mm", "right")
    assert left[1] == right[1] and left[3] == right[3]
    assert right[0] == OVERLAY_BASE_W - left[2]
    assert right[2] == OVERLAY_BASE_W - left[0]


def test_w_rail_defaults_match_historic_roi_width():
    assert w_rail_default_for_format("16mm") == 90
    assert w_rail_default_for_format("8mm") == 90
    assert w_rail_default_for_format("35mm") == 75


def test_w_rail_from_config_override():
    assert w_rail_from_config({}, "16mm") == 90
    assert w_rail_from_config({PERFORATION_RAIL_WIDTH_KEY: {"16mm": 120}}, "16mm") == 120
    assert w_rail_from_config({PERFORATION_RAIL_WIDTH_KEY: 55}, "35mm") == 55
    assert (
        w_rail_from_config(
            {"PERFORATION_ROI": {"16mm": {"w_rail": 88}}},
            "16mm",
        )
        == 88
    )


def test_w_rail_max_defaults_to_twice_rail():
    assert w_rail_max_from_config({}, "16mm") == 180
    assert w_rail_max_from_config({}, "35mm") == 150
    assert w_rail_max_from_config({}, "16mm", w_rail=100) == 200


def test_w_rail_max_from_config_override():
    assert (
        w_rail_max_from_config({PERFORATION_RAIL_WIDTH_MAX_KEY: {"16mm": 200}}, "16mm")
        == 200
    )
    assert w_rail_max_from_config({PERFORATION_RAIL_WIDTH_MAX_KEY: 160}, "35mm") == 160
    # Nunca por debajo de W_rail
    assert (
        w_rail_max_from_config({PERFORATION_RAIL_WIDTH_MAX_KEY: {"16mm": 50}}, "16mm")
        == 90
    )
    assert (
        w_rail_max_from_config(
            {"PERFORATION_ROI": {"16mm": {"w_rail_max": 170}}},
            "16mm",
        )
        == 170
    )
