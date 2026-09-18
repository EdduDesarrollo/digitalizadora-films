import subprocess

from print_scanner_app.infrastructure.camera.camera_detection import prepare_and_list_cameras
from print_scanner_app.infrastructure.camera.gphoto_client import GPhotoClient


def test_prepare_lists_cameras(monkeypatch):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_detection.list_camera_addresses",
        lambda *a, **k: [("Canon", "usb:1,2")],
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    out = prepare_and_list_cameras(GPhotoClient(), run=fake_run, unmount_first=False)
    assert out == [("Canon", "usb:1,2")]


def test_prepare_unmounts_when_requested(monkeypatch):
    calls = []

    def fake_unmount(*, run):
        calls.append(run)

    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_detection.unmount_camera_mounts",
        fake_unmount,
    )
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_detection.list_camera_addresses",
        lambda *a, **k: [],
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    prepare_and_list_cameras(GPhotoClient(), run=fake_run, unmount_first=True)
    assert calls and calls[0] is fake_run
