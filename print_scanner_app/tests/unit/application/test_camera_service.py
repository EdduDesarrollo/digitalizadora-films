import subprocess

from print_scanner_app.application.services.camera_service import CameraService


def test_assign_no_cameras(monkeypatch):
    def fake_prepare(client, **kwargs):
        return []

    monkeypatch.setattr(
        "print_scanner_app.application.services.camera_service.prepare_and_list_cameras",
        fake_prepare,
    )
    svc = CameraService()
    r = svc.assign_camera("SN", {})
    assert not r.ok

    sess, err = svc.open_session_for_download("SN", {})
    assert sess is None and err == "Sin cámaras"
    sess2, err2 = svc.open_session_for_capture("SN", {})
    assert sess2 is None and err2 == "Sin cámaras"
