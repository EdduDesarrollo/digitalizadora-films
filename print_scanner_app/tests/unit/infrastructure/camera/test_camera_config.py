from print_scanner_app.infrastructure.camera.camera_config import (
    ApplyConfigResult,
    WARNING_CONFIG_MANUAL,
    apply_camera_configurations,
    apply_configurations_to_camera,
)


def test_apply_config_result_model_mismatch():
    r = ApplyConfigResult(model_mismatch=True, ok=False)
    assert not r.ok
    assert r.model_mismatch


def test_warning_constants_exact():
    assert "Warning!" in WARNING_CONFIG_MANUAL
    assert "configuración manualmente" in WARNING_CONFIG_MANUAL


def test_apply_empty():
    class Cam:
        pass

    assert apply_configurations_to_camera(Cam(), {}, None) is True
