from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.domain.models.app_state import AppState
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository


def _cfg(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{}", encoding="utf-8")
    return ConfigRepository(p)


def test_start_sets_digitalization_flags():
    st = AppState(digitalizing=False, pause_digitization=True)
    svc = CaptureService()
    assert svc.start_digitization(st)
    assert st.digitalizing and not st.pause_digitization


def test_pause_resume_require_started_state():
    st = AppState()
    svc = CaptureService()
    assert not svc.pause_digitization(st)
    assert not svc.resume_digitization(st)


def test_pause_and_resume_flow():
    st = AppState(digitalizing=True, pause_digitization=False)
    svc = CaptureService()
    assert svc.pause_digitization(st)
    assert st.pause_digitization
    assert svc.resume_digitization(st)
    assert not st.pause_digitization


def test_stop_digitization_resets_state():
    st = AppState(digitalizing=True, pause_digitization=True)
    svc = CaptureService()
    assert svc.stop_digitization(st)
    assert not st.digitalizing and not st.pause_digitization


def test_capture_tick_increments_only_when_active():
    st = AppState(digitalizing=False, pause_digitization=False, frame_count=0)
    svc = CaptureService()
    assert not svc.capture_tick(st)
    assert st.frame_count == 0

    st.digitalizing = True
    assert svc.capture_tick(st)
    assert st.frame_count == 1

    st.pause_digitization = True
    assert not svc.capture_tick(st)
    assert st.frame_count == 1


def test_capture_tick_appends_pending_when_repo_present(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="cap")
    st = AppState(digitalizing=True, frame_count=0)
    svc = CaptureService(repo)
    assert svc.capture_tick(st)
    assert st.frame_count == 1
    pairs = repo.load_all()
    assert pairs == [["CAP-000001.CR3", "cap-000001.cr3"]]


def test_capture_tick_uses_provider_when_available(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="cap2")
    st = AppState(digitalizing=True, frame_count=0)
    svc = CaptureService(repo, raw_name_provider=lambda i: f"REAL-{i:06d}.CR3")
    assert svc.capture_tick(st)
    assert repo.load_all() == [["REAL-000001.CR3", "cap2-000001.cr3"]]


def test_capture_tick_falls_back_when_provider_fails(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="cap3")
    st = AppState(digitalizing=True, frame_count=0)

    def broken_provider(_i: int):
        raise RuntimeError("boom")

    svc = CaptureService(repo, raw_name_provider=broken_provider)
    assert svc.capture_tick(st)
    assert repo.load_all() == [["CAP-000001.CR3", "cap3-000001.cr3"]]


def test_observe_raw_and_capture_tick_emit_frame_callback():
    st = AppState(digitalizing=True, frame_count=0)
    svc = CaptureService()
    seen: list[int] = []
    svc.set_on_frame_count_changed(lambda n: seen.append(n))
    assert svc.observe_raw(st, "X.CR3")
    assert seen == [1]
    assert svc.observe_raw(st, "Y.CR3")
    assert seen == [1, 2]
    assert not svc.observe_raw(st, "Y.CR3")
    assert seen == [1, 2]
    assert svc.capture_tick(st)
    assert seen == [1, 2, 3]


def test_observe_raw_deduplicates_names(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="obs")
    st = AppState(digitalizing=True, frame_count=0)
    svc = CaptureService(repo)
    assert svc.observe_raw(st, "A.CR3")
    assert not svc.observe_raw(st, "A.CR3")
    assert svc.observe_raw(st, "B.CR3")
    assert st.frame_count == 2
    assert repo.load_all() == [["A.CR3", "obs-000001.cr3"], ["B.CR3", "obs-000002.cr3"]]


def test_observe_raw_blocks_when_paused_without_flag():
    """Sin allow_when_paused=True, observe_raw ignora el RAW si pause_digitization=True."""
    st = AppState(digitalizing=True, pause_digitization=True, frame_count=0)
    svc = CaptureService()
    assert not svc.observe_raw(st, "X.CR3")
    assert st.frame_count == 0


def test_observe_raw_allows_when_paused_with_flag(tmp_path):
    """Con allow_when_paused=True, observe_raw persiste el pendiente aunque pause_digitization=True."""
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="paused")
    st = AppState(digitalizing=True, pause_digitization=True, frame_count=0)
    svc = CaptureService(repo)
    assert svc.observe_raw(st, "X.CR3", allow_when_paused=True)
    assert st.frame_count == 1
    assert repo.load_all() == [["X.CR3", "paused-000001.cr3"]]


def test_observe_raw_not_digitalizing_always_blocks():
    """Si digitalizing=False, observe_raw siempre bloquea sin importar allow_when_paused."""
    st = AppState(digitalizing=False, frame_count=0)
    svc = CaptureService()
    assert not svc.observe_raw(st, "X.CR3", allow_when_paused=True)
    assert st.frame_count == 0


def test_observe_raw_manual_works_when_not_digitalizing(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="fxf")
    st = AppState(digitalizing=False, pause_digitization=False, frame_count=0)
    svc = CaptureService(repo)
    assert svc.observe_raw_manual(st, "M.CR3", jpg_name="M.JPG")
    assert st.frame_count == 1
    assert not st.digitalizing
    blocks = repo.load_blocks()
    assert len(blocks) == 1
    assert blocks[0].raw_name == "M.CR3" and blocks[0].jpg_name == "M.JPG"


def test_observe_raw_manual_works_when_paused(tmp_path):
    (tmp_path / "Utils").mkdir(parents=True)
    repo = RawPendingRepository(tmp_path / "Utils", _cfg(tmp_path), fixed_session_key="fxfp")
    st = AppState(digitalizing=True, pause_digitization=True, frame_count=3)
    svc = CaptureService(repo)
    assert svc.observe_raw_manual(st, "P.CR3")
    assert st.frame_count == 4
    assert st.pause_digitization
    assert repo.load_all()[-1] == ["P.CR3", "fxfp-000004.cr3"]


def test_observe_raw_manual_deduplicates_and_emits_callback():
    st = AppState(digitalizing=False, frame_count=0)
    svc = CaptureService()
    seen: list[int] = []
    svc.set_on_frame_count_changed(lambda n: seen.append(n))
    assert svc.observe_raw_manual(st, "A.CR3")
    assert not svc.observe_raw_manual(st, "A.CR3")
    assert svc.observe_raw_manual(st, "B.CR3")
    assert seen == [1, 2]
    assert st.frame_count == 2