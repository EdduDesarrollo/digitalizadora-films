from print_scanner_app.application.dto.results import CameraAssignResult
from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.application.services.shutdown_service import ShutdownService
from print_scanner_app.application.use_cases.exit_app import ExitAppUseCase
from print_scanner_app.application.use_cases.pause_digitization import PauseDigitizationUseCase
from print_scanner_app.application.use_cases.resume_digitization import ResumeDigitizationUseCase
from print_scanner_app.application.use_cases.retry_camera import RetryCameraUseCase
from print_scanner_app.application.use_cases.start_digitization import StartDigitizationUseCase
from print_scanner_app.application.use_cases.stop_digitization import StopDigitizationUseCase
from print_scanner_app.domain.models.app_state import AppState


def test_start_pause_resume_updates_state():
    st = AppState()
    cap = CaptureService()
    start = StartDigitizationUseCase(st, cap).execute()
    pause = PauseDigitizationUseCase(st, cap).execute()
    resume = ResumeDigitizationUseCase(st, cap).execute()
    assert start.ok and pause.ok and resume.ok
    assert st.digitalizing and not st.pause_digitization


def test_pause_resume_fail_without_digitizing():
    st = AppState()
    cap = CaptureService()
    r_pause = PauseDigitizationUseCase(st, cap).execute()
    r_resume = ResumeDigitizationUseCase(st, cap).execute()
    assert not r_pause.ok
    assert not r_resume.ok
    assert r_resume.error == "digitización no está en pausa"


def test_restart_clears_pause():
    st = AppState()
    st.digitalizing = True
    st.pause_digitization = True
    StartDigitizationUseCase(st, CaptureService()).execute()
    assert st.digitalizing and not st.pause_digitization


def test_stop_digitization_resets_flags():
    st = AppState(digitalizing=True, pause_digitization=True)
    r = StopDigitizationUseCase(st, CaptureService()).execute()
    assert r.ok
    assert not st.digitalizing and not st.pause_digitization


def test_start_fails_if_already_active():
    st = AppState(digitalizing=True, pause_digitization=False)
    r = StartDigitizationUseCase(st, CaptureService()).execute()
    assert not r.ok
    assert r.error == "digitización ya activa"


def test_pause_fails_if_already_paused():
    st = AppState(digitalizing=True, pause_digitization=True)
    r = PauseDigitizationUseCase(st, CaptureService()).execute()
    assert not r.ok
    assert r.error == "digitización ya pausada"


def test_stop_fails_if_already_stopped():
    st = AppState(digitalizing=False, pause_digitization=False)
    r = StopDigitizationUseCase(st, CaptureService()).execute()
    assert not r.ok
    assert r.error == "digitización ya detenida"


def test_exit():
    ex = ExitAppUseCase(ShutdownService())
    r = ex.execute()
    assert r.ok


def test_exit_delegates_to_shutdown(monkeypatch):
    called: list[str] = []

    class FakeShutdown:
        def release_printer(self, device_path="/dev/usb/lp0"):
            called.append(str(device_path))

    r = ExitAppUseCase(FakeShutdown()).execute()
    assert r.ok and called == ["/dev/usb/lp0"]


def test_retry_camera_propaga_fallo():
    class FakeCam:
        def assign_camera(self, serial, cfg):
            return CameraAssignResult(ok=False, error="sin cámara")

    r = RetryCameraUseCase(FakeCam()).execute("SN", {})
    assert not r.ok and r.error == "sin cámara"


def test_retry_camera_handles_exception():
    class BoomCam:
        def assign_camera(self, serial, cfg):
            raise RuntimeError("usb busy")

    r = RetryCameraUseCase(BoomCam()).execute("SN", {})
    assert not r.ok and r.error == "usb busy"


def test_exit_handles_exception():
    class BadShutdown:
        def release_printer(self, device_path="/dev/usb/lp0"):
            raise RuntimeError("release failed")

    r = ExitAppUseCase(BadShutdown()).execute()
    assert not r.ok
