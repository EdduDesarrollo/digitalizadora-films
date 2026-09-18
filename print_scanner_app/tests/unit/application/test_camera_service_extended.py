"""Escenarios mockeados de `CameraService` (serial, multi-cámara, errores)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

import print_scanner_app.application.services.camera_service as cam_svc
from print_scanner_app.application.services.camera_service import CameraService
from print_scanner_app.application.dto.camera_session import CameraSession
from print_scanner_app.infrastructure.camera.camera_config import ApplyConfigResult


def _mock_gphoto_client() -> MagicMock:
    """Evita ``import gphoto2`` en CI (solo pytest + Pillow en requirements-dev)."""
    client = MagicMock()
    client.gp = MagicMock(name="gp")
    return client


def _svc(monkeypatch: pytest.MonkeyPatch, *, run=None) -> CameraService:
    return CameraService(run=run, photo_client=_mock_gphoto_client())


def test_prepare_raises_returns_error(monkeypatch: pytest.MonkeyPatch):
    def boom(*a, **k):
        raise RuntimeError("gio")

    monkeypatch.setattr(cam_svc, "prepare_and_list_cameras", boom)
    r = CameraService().assign_camera("SN", {})
    assert not r.ok and "gio" in (r.error or "")


def test_no_cameras(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cam_svc, "prepare_and_list_cameras", lambda *a, **k: [])
    r = CameraService().assign_camera("SN", {})
    assert not r.ok and "Sin cámaras" in (r.error or "")


def _stub_camera_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        cam_svc,
        "read_camera_model_from_device",
        lambda *a, **k: "Canon EOS M6 Mark II",
    )
    monkeypatch.setattr(
        cam_svc,
        "apply_camera_configurations",
        lambda *a, **k: ApplyConfigResult(ok=True, applied=["k"]),
    )
    monkeypatch.setattr(
        cam_svc,
        "ensure_capture_target_memory_card",
        lambda *a, **k: True,
    )


def test_assign_serial_match(monkeypatch: pytest.MonkeyPatch):
    cam_mock = MagicMock()
    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("Canon", "usb:1,1")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: cam_mock)
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda gp, cam: "ABC123")
    _stub_camera_config(monkeypatch)

    r = _svc(monkeypatch).assign_camera("ABC123", {"k": "v"})
    assert r.ok
    assert r.usb_address == "usb:1,1"
    assert r.serial == "ABC123"
    cam_mock.exit.assert_called_once()


def test_single_camera_no_serial_without_expected_serial_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("Canon", "usb:1,1")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: object())
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda gp, cam: None)
    _stub_camera_config(monkeypatch)

    r = _svc(monkeypatch).assign_camera("", {})
    assert not r.ok


def test_skips_on_serial_mismatch_then_ok(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    def serial(gp, cam):
        calls["n"] += 1
        return "BAD" if calls["n"] == 1 else "GOOD"

    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("A", "usb:1,1"), ("B", "usb:1,2")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: object())
    monkeypatch.setattr(cam_svc, "get_camera_serial", serial)
    _stub_camera_config(monkeypatch)

    r = _svc(monkeypatch).assign_camera("GOOD", {})
    assert r.ok
    assert r.usb_address == "usb:1,2"


def test_all_inits_fail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("A", "usb:1,1")],
    )
    monkeypatch.setattr(
        cam_svc,
        "init_camera_at_address",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    r = _svc(monkeypatch).assign_camera("X", {})
    assert not r.ok


def test_reset_usb_for_address(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cam_svc, "reset_usb_address", lambda addr: addr == "usb:1,1")
    assert CameraService().reset_usb_for_address("usb:1,1")
    assert not CameraService().reset_usb_for_address("bad")


def test_uses_custom_subprocess_run(monkeypatch: pytest.MonkeyPatch):
    passed_run = []

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def fake_prepare(client, *, run, unmount_first=True):
        passed_run.append(run)
        return [("x", "usb:9,9")]

    monkeypatch.setattr(cam_svc, "prepare_and_list_cameras", fake_prepare)
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: object())
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda *a, **k: "SN")
    _stub_camera_config(monkeypatch)

    _svc(monkeypatch, run=fake_run).assign_camera("SN", {}, unmount_first=False)
    assert passed_run and passed_run[0] is fake_run


def test_capture_helpers_delegate_to_gphoto(monkeypatch: pytest.MonkeyPatch):
    svc = CameraService()
    sess = CameraSession(gp="gp", camera="cam", usb_address="usb:1")
    monkeypatch.setattr(cam_svc, "trigger_capture_and_get_raw_name", lambda c, g: "X.CR3")
    monkeypatch.setattr(cam_svc, "find_latest_raw_on_camera", lambda c, g, last_found_folder=None: ("/", "Y.CR3"))
    assert svc.capture_raw_name(sess) == "X.CR3"
    assert svc.find_latest_raw_name(sess, []) == "Y.CR3"


def test_model_mismatch_skips_apply_still_invariant(monkeypatch: pytest.MonkeyPatch):
    calls = {"apply": 0, "inv": 0}

    def fake_apply(*a, **k):
        calls["apply"] += 1
        return ApplyConfigResult(ok=True)

    def fake_inv(*a, **k):
        calls["inv"] += 1
        return True

    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("Canon", "usb:1,1")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: MagicMock())
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda *a, **k: "SN1")
    monkeypatch.setattr(
        cam_svc,
        "read_camera_model_from_device",
        lambda *a, **k: "Other Camera",
    )
    monkeypatch.setattr(cam_svc, "apply_camera_configurations", fake_apply)
    monkeypatch.setattr(cam_svc, "ensure_capture_target_memory_card", fake_inv)

    config = {"main/status/cameramodel": "Canon EOS M6 Mark II"}
    r = _svc(monkeypatch).assign_camera("SN1", config)
    assert r.ok
    assert calls["apply"] == 0
    assert calls["inv"] == 1


def test_open_session_skips_apply_when_flag_false(monkeypatch: pytest.MonkeyPatch):
    calls = {"apply": 0, "inv": 0}

    def fake_apply(*a, **k):
        calls["apply"] += 1
        return ApplyConfigResult(ok=True)

    def fake_inv(*a, **k):
        calls["inv"] += 1
        return True

    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("Canon", "usb:1,1")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: MagicMock())
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda *a, **k: "SN1")
    monkeypatch.setattr(cam_svc, "read_camera_model_from_device", lambda *a, **k: "Model")
    monkeypatch.setattr(cam_svc, "apply_camera_configurations", fake_apply)
    monkeypatch.setattr(cam_svc, "ensure_capture_target_memory_card", fake_inv)

    svc = _svc(monkeypatch)
    session, err = svc.open_session_for_capture(
        "SN1",
        {"main/x": 1},
        apply_saved_config=False,
    )
    assert session is not None
    assert err is None
    assert calls["apply"] == 0
    assert calls["inv"] == 0


def test_open_session_for_download_skips_invariant(monkeypatch: pytest.MonkeyPatch):
    calls = {"inv": 0}

    def fake_inv(*a, **k):
        calls["inv"] += 1
        return True

    monkeypatch.setattr(
        cam_svc,
        "prepare_and_list_cameras",
        lambda *a, **k: [("Canon", "usb:1,1")],
    )
    monkeypatch.setattr(cam_svc, "init_camera_at_address", lambda *a, **k: MagicMock())
    monkeypatch.setattr(cam_svc, "get_camera_serial", lambda *a, **k: "SN1")
    monkeypatch.setattr(cam_svc, "read_camera_model_from_device", lambda *a, **k: "Model")
    monkeypatch.setattr(cam_svc, "ensure_capture_target_memory_card", fake_inv)

    session, err = _svc(monkeypatch).open_session_for_download("SN1", {})
    assert session is not None and err is None
    assert calls["inv"] == 0


def test_close_session_ignores_errors(monkeypatch: pytest.MonkeyPatch):
    class Cam:
        def exit(self):
            raise RuntimeError("x")

    monkeypatch.setattr(
        "print_scanner_app.application.services.camera_service.disable_viewfinder_best_effort",
        lambda *_a, **_k: False,
    )
    sess = CameraSession(gp=None, camera=Cam(), usb_address="usb:1")
    CameraService().close_session(sess)


def test_close_session_disables_viewfinder_before_exit(monkeypatch: pytest.MonkeyPatch):
    order: list[str] = []

    class Cam:
        def exit(self):
            order.append("exit")

    monkeypatch.setattr(
        "print_scanner_app.application.services.camera_service.disable_viewfinder_best_effort",
        lambda cam, gp: order.append("vf") or True,
    )
    sess = CameraSession(gp="gp", camera=Cam(), usb_address="usb:1")
    CameraService().close_session(sess)
    assert order == ["vf", "exit"]
