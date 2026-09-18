from __future__ import annotations

from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
    diff_camera_config,
    filter_camera_config_to_whitelist,
    has_preset_camera_config,
)


def test_filter_drops_non_whitelist_keys():
    raw = {
        "main/actions/syncdatetime": 0,
        "main/imgsettings/iso": "250",
        "main/settings/capturetarget": "Memory card",
    }
    out = filter_camera_config_to_whitelist(raw)
    assert "main/actions/syncdatetime" not in out
    assert out["main/imgsettings/iso"] == "250"


def test_has_preset_false_when_empty_or_only_invariants():
    assert not has_preset_camera_config({})
    assert not has_preset_camera_config({"main/settings/capturetarget": "x"})
    assert not has_preset_camera_config(
        {"main/status/cameramodel": "Canon EOS M6 Mark II"}
    )


def test_has_preset_true_with_iso():
    assert has_preset_camera_config({"main/imgsettings/iso": "250"})


def test_diff_only_changed_whitelist_keys():
    before = {"main/imgsettings/iso": "200", "main/settings/capturetarget": "A"}
    after = {"main/imgsettings/iso": "250", "main/settings/capturetarget": "A"}
    assert diff_camera_config(before, after) == {"main/imgsettings/iso": "250"}
