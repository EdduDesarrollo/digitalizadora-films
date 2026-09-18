from print_scanner_app.application.dto.results import ExitResult
from print_scanner_app.application.services.shutdown_service import ShutdownService


class ExitAppUseCase:
    def __init__(self, shutdown: ShutdownService):
        self._shutdown = shutdown

    def execute(self) -> ExitResult:
        try:
            self._shutdown.release_printer()
            return ExitResult(ok=True)
        except Exception:
            return ExitResult(ok=False)
