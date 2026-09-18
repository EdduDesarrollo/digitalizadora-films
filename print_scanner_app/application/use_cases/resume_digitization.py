from print_scanner_app.application.dto.results import SimpleOk
from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.domain.models.app_state import AppState


class ResumeDigitizationUseCase:
    def __init__(self, app_state: AppState, capture: CaptureService):
        self._state = app_state
        self._capture = capture

    def execute(self) -> SimpleOk:
        if not self._state.pause_digitization:
            return SimpleOk(ok=False, error="digitización no está en pausa")
        return SimpleOk(ok=self._capture.resume_digitization(self._state))
