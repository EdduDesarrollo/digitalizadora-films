from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Sequence, Union

from print_scanner_app.application.dto.results import DownloadRawsResult
from print_scanner_app.application.services.raw_download_service import CameraRawPort, RawDownloadService
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingBlock

ProgressCb = Callable[[int, int, str], None]

PendingInput = Sequence[Union[RawPendingBlock, Sequence[str]]]


class DownloadRawsUseCase:
    def __init__(self, service: RawDownloadService):
        self._service = service

    def execute(
        self,
        pending: PendingInput | List[List[str]],
        base_dir: Path,
        camera: CameraRawPort,
        progress: ProgressCb | None = None,
        *,
        search_root: Path | None = None,
    ) -> DownloadRawsResult:
        res = DownloadRawsResult()
        try:
            batch_res = self._service.download_batch(
                pending,
                base_dir,
                camera,
                search_root=search_root,
                progress=progress,
            )
            res.downloaded = batch_res.downloaded
            res.not_found = batch_res.not_found
            res.batch_folder = batch_res.batch_folder or None
            res.missing_local_copy_ids = batch_res.missing_local_copy_ids
            if batch_res.error:
                res.error = batch_res.error
                res.stopped_at = res.downloaded[-1] if res.downloaded else None
        except Exception as e:  # noqa: BLE001
            res.error = str(e)
            res.stopped_at = res.downloaded[-1] if res.downloaded else None
        return res
