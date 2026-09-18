from print_scanner_app.application.services.raw_download_service import RawDownloadService
from print_scanner_app.application.use_cases.download_raws import DownloadRawsUseCase
from print_scanner_app.application.use_cases.retry_camera import RetryCameraUseCase
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository


def test_download_raws_use_case_propagates_error(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    repo = RawPendingRepository(
        tmp_path,
        ConfigRepository(tmp_path / "config.json"),
        fixed_session_key="s",
    )
    repo.append("A.CR3", "x.cr3")

    class BoomCam:
        def find_raw(self, raw_name):
            return "/", raw_name

        def save_raw_to(self, folder, name, dest_path):
            raise RuntimeError("disk")

        def delete_raw(self, folder, name):
            pass

        def delete_jpeg(self, jpg_basename):
            return "deleted"

    uc = DownloadRawsUseCase(RawDownloadService(repo))
    res = uc.execute(repo.load_all(), tmp_path / "d", BoomCam(), search_root=tmp_path / "d")
    assert res.error


def test_retry_camera_delegates(monkeypatch):
    class Svc:
        def assign_camera(self, serial, cfg):
            from print_scanner_app.application.dto.results import CameraAssignResult

            return CameraAssignResult(ok=True, serial=serial)

    uc = RetryCameraUseCase(Svc())
    r = uc.execute("SN123", {})
    assert r.ok and r.serial == "SN123"
