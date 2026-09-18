from __future__ import annotations

from typing import Any, Mapping

from print_scanner_app.application.dto.results import CameraAssignResult
from print_scanner_app.application.services.camera_service import CameraService


class RetryCameraUseCase:
    def __init__(self, camera_service: CameraService):
        self._cam = camera_service

    def execute(self, expected_serial: str, config_camara: Mapping[str, Any]) -> CameraAssignResult:
        try:
            return self._cam.assign_camera(expected_serial, config_camara)
        except Exception as exc:
            return CameraAssignResult(ok=False, error=str(exc))
