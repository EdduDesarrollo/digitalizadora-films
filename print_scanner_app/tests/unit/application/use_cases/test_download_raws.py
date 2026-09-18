from pathlib import Path

from print_scanner_app.application.services.raw_download_service import RawDownloadService
from print_scanner_app.application.use_cases.download_raws import DownloadRawsUseCase
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository


class Cam:
    def find_raw(self, raw_name):
        return "/", raw_name

    def save_raw_to(self, folder, name, dest_path):
        dest_path.write_bytes(b"1")

    def delete_raw(self, folder, name):
        pass


def test_use_case(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    repo = RawPendingRepository(
        tmp_path,
        ConfigRepository(tmp_path / "config.json"),
        fixed_session_key="s",
    )
    repo.append("A.CR3", "x-00001.cr3")
    uc = DownloadRawsUseCase(RawDownloadService(repo))
    res = uc.execute(repo.load_all(), tmp_path / "d", Cam(), search_root=tmp_path / "d")
    assert res.downloaded
    assert not res.error
    assert res.missing_local_copy_ids == []


def test_use_case_reports_error_when_pending_lines_invalid(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    repo = RawPendingRepository(
        tmp_path,
        ConfigRepository(tmp_path / "config.json"),
        fixed_session_key="s",
    )
    uc = DownloadRawsUseCase(RawDownloadService(repo))
    res = uc.execute([["solo"]], tmp_path / "d", Cam(), search_root=tmp_path / "d")
    assert res.error
    assert "No hay líneas válidas" in (res.error or "")
    assert not res.downloaded


def test_use_case_populates_missing_local_copy_ids(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    repo = RawPendingRepository(
        tmp_path,
        ConfigRepository(tmp_path / "config.json"),
        fixed_session_key="miss",
    )
    repo.append("M.CR3", "p-00001.cr3")

    class CamMiss:
        def find_raw(self, raw_name):
            return None, None

        def save_raw_to(self, folder, name, dest_path):
            pass

        def delete_raw(self, folder, name):
            pass

        def delete_jpeg(self, jpg_basename):
            return "deleted"

    uc = DownloadRawsUseCase(RawDownloadService(repo))
    res = uc.execute(repo.load_all(), tmp_path / "d", CamMiss(), search_root=tmp_path / "d")
    assert not res.error
    assert res.missing_local_copy_ids == ["M.CR3"]
    assert "M.CR3" in res.not_found


def test_use_case_fatal_abort_keeps_popup_ids(tmp_path):
    import errno

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    repo = RawPendingRepository(
        tmp_path,
        ConfigRepository(tmp_path / "config.json"),
        fixed_session_key="fatal",
    )
    repo.append("MISS.CR3", "p-miss.cr3")
    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")

    class Cam:
        def find_raw(self, raw_name):
            if raw_name == "MISS.CR3":
                return None, None
            return "/", raw_name

        def save_raw_to(self, folder, name, dest_path):
            if name == "B.CR3":
                raise OSError(errno.ENOSPC, "full")
            dest_path.write_bytes(b"1")

        def delete_raw(self, folder, name):
            pass

        def delete_jpeg(self, jpg_basename):
            return "deleted"

    uc = DownloadRawsUseCase(RawDownloadService(repo))
    res = uc.execute(repo.load_blocks(), tmp_path / "d", Cam(), search_root=tmp_path / "d")
    assert res.error
    assert res.missing_local_copy_ids == ["MISS.CR3"]
    assert res.downloaded == ["A.CR3"]
