from __future__ import annotations

import logging
from pathlib import Path

from print_scanner_app.application.services.camera_service import CameraService
from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.application.services.printer_service import PrinterService
from print_scanner_app.application.services.raw_download_service import RawDownloadService
from print_scanner_app.application.services.shutdown_service import ShutdownService
from print_scanner_app.application.services.startup_service import StartupService
from print_scanner_app.application.use_cases.download_raws import DownloadRawsUseCase
from print_scanner_app.application.use_cases.exit_app import ExitAppUseCase
from print_scanner_app.application.use_cases.pause_digitization import PauseDigitizationUseCase
from print_scanner_app.application.use_cases.resume_digitization import ResumeDigitizationUseCase
from print_scanner_app.application.use_cases.retry_camera import RetryCameraUseCase
from print_scanner_app.application.use_cases.start_digitization import StartDigitizationUseCase
from print_scanner_app.application.use_cases.stop_digitization import StopDigitizationUseCase
from print_scanner_app.domain.models.app_state import AppState
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository
from print_scanner_app.infrastructure.system.env_tools import project_root_from_here


class Container:
    """Factoría de servicios de la aplicación."""

    def __init__(
        self,
        project_root: Path,
        session_label: str | None,
        logger: logging.Logger,
    ):
        self.project_root = project_root
        # None en producción: clave de `raw_pendientes_*.txt` sale de config (CODIGO_REFERENCIA + prefijo).
        self.session_label = session_label or ""
        self.logger = logger
        self.app_state = AppState()
        self.config_repo = ConfigRepository(project_root / "config.json")
        utils = project_root / "Utils"
        self.raw_pending_repo = RawPendingRepository(
            utils,
            self.config_repo,
            fixed_session_key=session_label,
        )
        self._camera_service = CameraService(logger=self.logger)
        self._printer_service = PrinterService(logger=self.logger)
        self._capture_service = CaptureService(self.raw_pending_repo)

    def camera_service(self) -> CameraService:
        return self._camera_service

    def printer_service(self) -> PrinterService:
        return self._printer_service

    def startup_service(self) -> StartupService:
        return StartupService(
            camera=self.camera_service(),
            printer=self.printer_service(),
            logger=self.logger,
        )

    def shutdown_service(self) -> ShutdownService:
        return ShutdownService(logger=self.logger)

    def raw_download_service(self) -> RawDownloadService:
        return RawDownloadService(self.raw_pending_repo, logger=self.logger)

    def download_raws_use_case(self) -> DownloadRawsUseCase:
        return DownloadRawsUseCase(self.raw_download_service())

    def retry_camera_use_case(self) -> RetryCameraUseCase:
        return RetryCameraUseCase(self.camera_service())

    def exit_app_use_case(self) -> ExitAppUseCase:
        return ExitAppUseCase(self.shutdown_service())

    def start_digitization_use_case(self) -> StartDigitizationUseCase:
        return StartDigitizationUseCase(self.app_state, self.capture_service())

    def pause_digitization_use_case(self) -> PauseDigitizationUseCase:
        return PauseDigitizationUseCase(self.app_state, self.capture_service())

    def resume_digitization_use_case(self) -> ResumeDigitizationUseCase:
        return ResumeDigitizationUseCase(self.app_state, self.capture_service())

    def stop_digitization_use_case(self) -> StopDigitizationUseCase:
        return StopDigitizationUseCase(self.app_state, self.capture_service())

    def capture_service(self) -> CaptureService:
        return self._capture_service


def default_container(logger: logging.Logger, session_label: str | None = None) -> Container:
    root = project_root_from_here(Path(__file__).resolve().parent.parent.parent)
    return Container(root, session_label, logger)
