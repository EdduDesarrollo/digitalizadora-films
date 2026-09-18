import errno
from pathlib import Path

import pytest

pytestmark = pytest.mark.critical

from print_scanner_app.domain.exceptions.domain_errors import RawDownloadError
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository
from print_scanner_app.application.services.raw_download_service import RawDownloadService


class FakeCam:
    def __init__(self, fail_at: str | None = None, raise_os: OSError | None = None):
        self.fail_at = fail_at
        self.raise_os = raise_os

    def find_raw(self, raw_name):
        if raw_name == "MISS.CR3":
            return None, None
        return "/", raw_name

    def save_raw_to(self, folder, name, dest_path: Path):
        if self.raise_os:
            raise self.raise_os
        dest_path.write_bytes(b"raw")

    def delete_raw(self, folder, name):
        pass

    def delete_jpeg(self, jpg_basename):
        return "deleted"


def _cfg(tmp_path) -> ConfigRepository:
    p = tmp_path / "config.json"
    p.write_text("{}", encoding="utf-8")
    return ConfigRepository(p)


def test_download_batch_ok(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")
    srv = RawDownloadService(repo)
    base = tmp_path / "out"
    out = srv.download_batch(repo.load_all(), base, FakeCam())
    assert out.batch_folder == "00001-00002"
    assert len(out.downloaded) == 2
    assert not out.not_found
    assert not out.missing_local_copy_ids
    assert repo.is_empty()


def test_resume_after_partial(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    for i in range(1, 5):
        repo.append(f"F{i}.CR3", f"p-{i:05d}.cr3")

    class Partial(FakeCam):
        def save_raw_to(self, folder, name, dest_path):
            if name == "F3.CR3":
                raise OSError(errno.ENOSPC, "full")
            super().save_raw_to(folder, name, dest_path)

    srv = RawDownloadService(repo)

    out = srv.download_batch(repo.load_all(), tmp_path / "o1", Partial())
    assert out.error
    assert out.downloaded == ["F1.CR3", "F2.CR3"]

    remaining = repo.load_all()
    assert len(remaining) == 2  # F3, F4 still there (F1,F2 succeeded and removed)


def test_not_found_lists(tmp_path):
    repo = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="s")
    repo.append("MISS.CR3", "p-00001.cr3")
    srv = RawDownloadService(repo)
    out = srv.download_batch(repo.load_all(), tmp_path / "o", FakeCam())
    assert not out.downloaded
    assert "MISS.CR3" in out.not_found
    assert out.missing_local_copy_ids == ["MISS.CR3"]


def test_download_batch_empty_returns_empty(tmp_path):
    repo = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="s")
    srv = RawDownloadService(repo)
    out = srv.download_batch([], tmp_path / "o", FakeCam())
    assert out.downloaded == [] and out.not_found == [] and out.batch_folder == ""
    assert out.missing_local_copy_ids == []


def test_download_batch_raises_when_no_valid_lines(tmp_path):
    repo = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="s")
    srv = RawDownloadService(repo)
    with pytest.raises(RawDownloadError, match="No hay líneas válidas"):
        srv.download_batch([["solo"]], tmp_path / "o", FakeCam())


def test_download_batch_ignores_short_lines_when_mixed_with_valid(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    srv = RawDownloadService(repo)
    out = srv.download_batch(
        [["mal"], ["A.CR3", "p-00001.cr3"]],
        tmp_path / "o",
        FakeCam(),
    )
    assert out.downloaded == ["A.CR3"]
    assert not out.not_found
    assert not out.missing_local_copy_ids
    assert out.batch_folder == "00001-00001"


def test_download_batch_calls_progress(tmp_path):
    repo = RawPendingRepository(tmp_path, _cfg(tmp_path), fixed_session_key="s")
    repo.append("A.CR3", "p-00001.cr3")
    srv = RawDownloadService(repo)
    prog: list[tuple[int, int, str]] = []
    srv.download_batch(
        repo.load_all(),
        tmp_path / "out",
        FakeCam(),
        progress=lambda i, t, msg: prog.append((i, t, msg)),
    )
    assert len(prog) == 1
    assert prog[0][0] == 1 and prog[0][1] == 1
    assert "Descargando" in prog[0][2]


class FakeCamMissingOnCard(FakeCam):
    """RAW no aparece en cámara (simula recuperación solo por disco)."""

    def find_raw(self, raw_name):
        return None, None


def test_disk_recovery_removes_block_without_download(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append("GONE.CR3", "p-found.cr3")
    srv = RawDownloadService(repo)
    root = tmp_path / "dest"
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "p-found.cr3").write_bytes(b"already")
    out = srv.download_batch(
        repo.load_all(), tmp_path / "out", FakeCamMissingOnCard(), search_root=root
    )
    assert out.downloaded == []
    assert out.not_found == []
    assert out.missing_local_copy_ids == []
    assert repo.is_empty()


def test_disk_recovery_duplicate_basename_lexicographic(tmp_path, caplog):
    import logging

    caplog.set_level(logging.WARNING)
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append("GONE.CR3", "dup.cr3")
    srv = RawDownloadService(repo)
    root = tmp_path / "dest"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir(parents=True)
    (root / "z" / "dup.cr3").write_text("z", encoding="utf-8")
    (root / "a" / "dup.cr3").write_text("a", encoding="utf-8")
    out = srv.download_batch(
        repo.load_all(), tmp_path / "out", FakeCamMissingOnCard(), search_root=root
    )
    assert out.downloaded == [] and out.not_found == [] and out.missing_local_copy_ids == []
    assert repo.is_empty()
    assert any("varias copias" in r.message for r in caplog.records)


class RecordingDownloadCam(FakeCam):
    def __init__(self):
        super().__init__()
        self.deleted_jpegs: list[str] = []

    def delete_jpeg(self, jpg_basename):
        self.deleted_jpegs.append(jpg_basename)
        return "deleted"


def test_phase_b_calls_delete_jpeg_for_each_success_with_metadata(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append_with_jpg("A.CR3", "p-00001.cr3", "a.JPG")
    repo.append_with_jpg("B.CR3", "p-00002.cr3", "b.JPG")
    srv = RawDownloadService(repo)
    cam = RecordingDownloadCam()
    out = srv.download_batch(repo.load_blocks(), tmp_path / "out", cam)
    assert out.downloaded == ["A.CR3", "B.CR3"] and not out.not_found and not out.missing_local_copy_ids
    assert sorted(cam.deleted_jpegs) == ["a.JPG", "b.JPG"]
    assert repo.is_empty()


class FlakyJpegCam(FakeCam):
    def __init__(self):
        super().__init__()
        self.delete_calls: list[str] = []

    def delete_jpeg(self, jpg_basename):
        self.delete_calls.append(jpg_basename)
        if len(self.delete_calls) == 1:
            raise TimeoutError("simulated timeout")
        return "deleted"


def test_phase_b_non_fatal_jpeg_error_continues_with_next(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append_with_jpg("A.CR3", "p-00001.cr3", "1.JPG")
    repo.append_with_jpg("B.CR3", "p-00002.cr3", "2.JPG")
    srv = RawDownloadService(repo)
    cam = FlakyJpegCam()
    out = srv.download_batch(repo.load_blocks(), tmp_path / "out", cam)
    assert out.downloaded == ["A.CR3", "B.CR3"]
    assert len(cam.delete_calls) == 2
    assert cam.delete_calls == ["1.JPG", "2.JPG"]


class AbsentJpegCam(FakeCam):
    def delete_jpeg(self, jpg_basename):
        return "absent"


def test_phase_b_absent_jpeg_counts_as_success(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append_with_jpg("A.CR3", "p-00001.cr3", "gone.JPG")
    srv = RawDownloadService(repo)
    out = srv.download_batch(repo.load_blocks(), tmp_path / "out", AbsentJpegCam())
    assert out.downloaded == ["A.CR3"] and not out.not_found and not out.missing_local_copy_ids
    assert repo.is_empty()


def test_fatal_abort_preserves_popup_ids_and_skips_phase_b(tmp_path):
    utils = tmp_path / "u"
    utils.mkdir()
    repo = RawPendingRepository(utils, _cfg(tmp_path), fixed_session_key="s")
    repo.append("MISS.CR3", "p-miss.cr3")
    repo.append("A.CR3", "p-00001.cr3")
    repo.append("B.CR3", "p-00002.cr3")
    srv = RawDownloadService(repo)

    class CamFatal(FakeCam):
        def save_raw_to(self, folder, name, dest_path):
            if name == "B.CR3":
                raise OSError(errno.ENOSPC, "full")
            super().save_raw_to(folder, name, dest_path)

        def delete_jpeg(self, jpg_basename):
            raise AssertionError("fase B no debe ejecutarse tras aborto fatal")

    out = srv.download_batch(repo.load_blocks(), tmp_path / "out", CamFatal())
    assert out.error
    assert out.missing_local_copy_ids == ["MISS.CR3"]
    assert out.downloaded == ["A.CR3"]
    assert _pending_names(repo) == ["MISS.CR3", "B.CR3"]


def _pending_names(repo: RawPendingRepository) -> list[str]:
    return [row[0] for row in repo.load_all()]
