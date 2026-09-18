from print_scanner_app.application.services.shutdown_service import ShutdownService
from print_scanner_app.application.services.startup_service import StartupService


def test_shutdown_calls_kill(monkeypatch, tmp_path):
    called = []

    monkeypatch.setattr(
        "print_scanner_app.application.services.shutdown_service.kill_processes_using_device",
        lambda p: called.append(p),
    )
    ShutdownService().release_printer("/dev/usb/lp9")
    assert "/dev/usb/lp9" in called


def test_startup_runs(monkeypatch):
    monkeypatch.setattr(
        "print_scanner_app.application.services.startup_service.unmount_camera_mounts",
        lambda: None,
    )
    monkeypatch.setattr(
        "print_scanner_app.application.services.startup_service.reset_usb_camara_e_impresora",
        lambda: 0,
    )

    class CS:
        def assign_camera(self, *a, **k):
            from print_scanner_app.application.dto.results import CameraAssignResult

            return CameraAssignResult(ok=True)

    class PS:
        def connect(self):
            return True

    out = StartupService(camera=CS(), printer=PS()).run(
        expected_serial="",
        config_camera_json={},
        reset_usb_first=False,
    )
    assert out.camera_assigned and out.printer_ok


def test_startup_reset_usb_counts_and_sleeps(monkeypatch):
    monkeypatch.setattr(
        "print_scanner_app.application.services.startup_service.unmount_camera_mounts",
        lambda: None,
    )
    monkeypatch.setattr(
        "print_scanner_app.application.services.startup_service.reset_usb_camara_e_impresora",
        lambda: 2,
    )
    sleeps = []
    monkeypatch.setattr(
        "print_scanner_app.application.services.startup_service.time.sleep",
        lambda s: sleeps.append(s),
    )

    class CS:
        def assign_camera(self, *a, **k):
            from print_scanner_app.application.dto.results import CameraAssignResult

            return CameraAssignResult(ok=True)

    class PS:
        def connect(self):
            return False

    out = StartupService(camera=CS(), printer=PS()).run(
        expected_serial="SN",
        config_camera_json={},
        reset_usb_first=True,
    )
    assert out.usb_resets == 2
    assert 4.0 in sleeps
    assert not out.printer_ok
