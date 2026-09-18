from print_scanner_app.application.dto.results import SimpleOk
from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.domain.models.app_state import AppState


class StartDigitizationUseCase:
    def __init__(self, app_state: AppState, capture: CaptureService):
        self._state = app_state
        self._capture = capture

    def execute(self) -> SimpleOk:
        if self._state.digitalizing and not self._state.pause_digitization:
            return SimpleOk(ok=False, error="digitización ya activa")
        return SimpleOk(ok=self._capture.start_digitization(self._state))
