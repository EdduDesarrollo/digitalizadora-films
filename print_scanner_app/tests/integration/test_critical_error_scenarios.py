import errno

import pytest

from print_scanner_app.application.services.raw_download_service import RawDownloadService
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository

pytestmark = pytest.mark.critical


class FakeCamera:
    def __init__(self, *, fail_on: str | None = None):
        self.fail_on = fail_on

    def find_raw(self, raw_name: str):
        return "/", raw_name

    def save_raw_to(self, folder, name, dest_path):
        if self.fail_on and name == self.fail_on:
            raise OSError(errno.ENOSPC, "No space left on device")
        dest_path.write_bytes(b"raw")

    def delete_raw(self, folder, name):
        return None

    def delete_jpeg(self, jpg_basename):
        return "deleted"


def _pending(repo: RawPendingRepository) -> list[str]:
    return [row[0] for row in repo.load_all()]


def _repo(tmp_path, key: str = "s") -> RawPendingRepository:
    (tmp_path / "utils").mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    return RawPendingRepository(tmp_path / "utils", ConfigRepository(cfg), fixed_session_key=key)


def test_enospc_keeps_current_and_following_pending(tmp_path):
    repo = _repo(tmp_path)
    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")
    repo.append("C.CR3", "p-00003.cr3")
    srv = RawDownloadService(repo)

    out = srv.download_batch(
        repo.load_all(),
        tmp_path / "out",
        FakeCamera(fail_on="B.CR3"),
        search_root=tmp_path / "out",
    )
    assert out.error
    assert out.downloaded == ["A.CR3"]

    assert _pending(repo) == ["B.CR3", "C.CR3"]


def test_retry_is_idempotent_after_partial_failure(tmp_path):
    repo = _repo(tmp_path)
    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")
    srv = RawDownloadService(repo)

    out_fail = srv.download_batch(
        repo.load_all(),
        tmp_path / "out",
        FakeCamera(fail_on="B.CR3"),
        search_root=tmp_path / "out",
    )
    assert out_fail.error
    assert out_fail.downloaded == ["A.CR3"]

    out_ok = srv.download_batch(
        repo.load_all(),
        tmp_path / "out",
        FakeCamera(),
        search_root=tmp_path / "out",
    )
    assert out_ok.downloaded == ["B.CR3"]
    assert out_ok.not_found == []
    assert out_ok.batch_folder == "00002-00002"
    assert repo.is_empty()


def test_each_click_generates_its_own_m_n_subfolder(tmp_path):
    repo = _repo(tmp_path)
    srv = RawDownloadService(repo)
    base = tmp_path / "out"

    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")
    out1 = srv.download_batch(repo.load_all(), base, FakeCamera(), search_root=base)

    repo.append("C.CR3", "p-00010.cr3")
    repo.append("D.CR3", "p-00011.cr3")
    out2 = srv.download_batch(repo.load_all(), base, FakeCamera(), search_root=base)

    assert out1.batch_folder == "00001-00002"
    assert out2.batch_folder == "00010-00011"
    assert (base / out1.batch_folder).is_dir()
    assert (base / out2.batch_folder).is_dir()
