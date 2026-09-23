import json
import logging
import sys
import threading
import time
import types
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from print_scanner_app import __version__
from print_scanner_app.app.container import Container
from print_scanner_app.application.dto.camera_session import CameraSession
from print_scanner_app.application.dto.results import CameraAssignResult, DownloadRawsResult, SimpleOk
from print_scanner_app.application.services.camera_service import CameraService
from print_scanner_app.application.services.startup_service import StartupOutcome, StartupService
from print_scanner_app.ui.presenters.app_presenter import AppPresenter


def _patch_immediate_shoot_stack(
    monkeypatch: pytest.MonkeyPatch,
    *,
    latest_cr3: str = "_MG_0001.CR3",
    exists: bool = True,
) -> None:
    """Mocks del camino capture() + baseline CR3 (digitación automática)."""
    import print_scanner_app.ui.presenters.app_presenter as ap_mod
    from print_scanner_app.domain.policies.shot_name_prediction import predict_next_cr3_name

    monkeypatch.setattr(ap_mod, "IMMEDIATE_TO_MOVE_DELAY_S", 0.0)
    monkeypatch.setattr(
        CameraService,
        "find_latest_raw_name",
        lambda self, _s, _c=None: latest_cr3,
    )

    state = {"last": latest_cr3}

    def _capture_raw_name(self, _s):
        nxt = predict_next_cr3_name(state["last"]) or state["last"]
        state["last"] = nxt
        return nxt

    monkeypatch.setattr(CameraService, "capture_raw_name", _capture_raw_name)
    monkeypatch.setattr(CameraService, "trigger_immediate_release", lambda self, _s: True)
    monkeypatch.setattr(
        CameraService,
        "raw_name_exists_on_card",
        lambda self, _s, _name, _c=None: exists,
    )


def _install_fake_kivy_clock(monkeypatch: pytest.MonkeyPatch, clock_cls: type) -> None:
    """Registra módulos ``kivy`` / ``kivy.clock`` en ``sys.modules`` (CI sin Kivy instalado)."""
    kivy_pkg = types.ModuleType("kivy")
    clock_mod = types.ModuleType("kivy.clock")
    clock_mod.Clock = clock_cls
    monkeypatch.setitem(sys.modules, "kivy", kivy_pkg)
    monkeypatch.setitem(sys.modules, "kivy.clock", clock_mod)


@pytest.fixture(autouse=True)
def _assume_printer_lp_for_digitization(monkeypatch: pytest.MonkeyPatch):
    """Evita depender de /dev/usb/lp* en CI; tests que necesiten fallo de impresora lo sobrescriben."""
    monkeypatch.setattr(
        "print_scanner_app.ui.presenters.app_presenter._printer_lp_available",
        lambda: True,
    )
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "CAMERA_EXIT_SETTLE_S", 0.0)


@pytest.fixture(autouse=True)
def _immediate_shoot_defaults(monkeypatch: pytest.MonkeyPatch):
    """Baseline CR3 + Immediate rápido por defecto (digitación automática)."""
    _patch_immediate_shoot_stack(monkeypatch, latest_cr3="_MG_0001.CR3", exists=True)


def test_welcome_message_contains_version():
    msg = AppPresenter().welcome_message()
    assert msg == f"Print Scanner v{__version__}"


def test_status_and_exit_with_container(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "SN-UNIT"}), encoding="utf-8")
    c = Container(tmp_path, "ut_presenter", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert "SN-UNIT" in p.status_hint()
    assert "Digitalización: detenida" in p.status_hint()
    assert "Frames: 0" in p.status_hint()
    assert p.pending_raw_count() == 0
    c.raw_pending_repo.append("a.CR3", "b.cr3")
    assert p.pending_raw_count() == 1
    assert p.exit_via_use_case().ok


def test_exit_without_container_returns_not_ok(test_logger):
    p = AppPresenter(logger=test_logger)
    assert not p.exit_via_use_case().ok


def test_config_and_pending_without_container():
    p = AppPresenter()
    assert p.config_camera_serial() == ""
    assert p.pending_raw_count() == 0
    assert p.current_directory() == ""
    assert "Digitalización: sin Container" in p.status_hint()
    assert p.capture_tick_interval_seconds() == 0.4
    assert not p.set_directory("/tmp/x")
    assert not p.open_current_directory()
    assert not p.set_format("16mm")
    assert p.get_format() == "16mm"
    assert p.increment_frame(1) == 0
    assert p.set_frame(10) == 0


def test_directory_and_format_and_frame_ops(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(json.dumps({"DIRECTORIO": str(tmp_path)}), encoding="utf-8")
    c = Container(tmp_path, "ops", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert p.current_directory() == str(tmp_path)
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    assert p.set_directory(str(new_dir))
    assert p.current_directory() == str(new_dir.resolve())
    seen = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: seen.append(a))
    assert p.open_current_directory()
    assert seen
    assert p.set_format("35mm")
    assert p.get_format() == "35mm"
    assert p.set_format("8mm")
    assert p.get_format() == "8mm"
    assert p.set_format("super8")
    assert p.get_format() == "super8"
    assert p.increment_frame(2) == 2
    assert p.set_frame(9) == 9


def test_move_film_pixels_delegates_to_printer(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "mfilm", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px: int) -> bool:
            moved.append(int(px))
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    r = p.move_film_pixels(1)
    assert isinstance(r, SimpleOk) and r.ok and moved == [1]
    r2 = p.move_film_pixels(0)
    assert r2.ok and moved == [1, 1]


def test_move_film_pixels_without_container(test_logger):
    p = AppPresenter(logger=test_logger)
    r = p.move_film_pixels(1)
    assert isinstance(r, SimpleOk) and not r.ok


def test_poll_alignment_debug_keys_r_clears_ui(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.debug.opencv_alignment_windows.poll_alignment_debug_key",
        lambda: ord("r"),
    )
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.debug.opencv_alignment_windows.close_alignment_debug_windows",
        lambda: None,
    )
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "pkey", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True
    assert p.poll_alignment_debug_keys()
    assert not p.is_debug_ui_active()


def test_poll_alignment_debug_key_e_clears_waiting(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.debug.opencv_alignment_windows.poll_alignment_debug_key",
        lambda: ord("e"),
    )
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "pe", test_logger), logger=test_logger)
    p._debug_alignment_waiting = True
    assert p.poll_alignment_debug_keys()
    assert not p.is_debug_alignment_waiting()
    assert p._debug_step_requested


def test_debug_waiting_skips_trigger_capture(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "dw", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    p._capture_session = object()
    p._debug_alignment_waiting = True
    seen: list[int] = []

    def _no_capture():
        seen.append(1)
        return None

    monkeypatch.setattr(p, "_trigger_and_read_raw_name", _no_capture)
    assert not p.run_capture_tick()
    assert seen == []


def test_poll_alignment_debug_keys_none(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.debug.opencv_alignment_windows.poll_alignment_debug_key",
        lambda: None,
    )
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "pn", test_logger), logger=test_logger)
    assert not p.poll_alignment_debug_keys()


def test_debug_ui_toggle_and_save_preference(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"DEBUG_CAPTURA": False}), encoding="utf-8")
    c = Container(tmp_path, "dui", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert not p.is_debug_ui_active()
    assert p.toggle_debug_ui() and p.is_debug_ui_active()
    p.save_debug_capture_preference(True)
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("DEBUG_CAPTURA") is True


def test_preview_fps_target_default_and_clamp(tmp_path, test_logger):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "fpsd", test_logger), logger=test_logger)
    assert abs(p.preview_fps_target() - 15.0) < 0.01
    (tmp_path / "config.json").write_text(json.dumps({"PREVIEW_FPS_TARGET": 2}), encoding="utf-8")
    assert abs(p.preview_fps_target() - 4.0) < 0.01
    (tmp_path / "config.json").write_text(json.dumps({"PREVIEW_FPS_TARGET": 99}), encoding="utf-8")
    assert abs(p.preview_fps_target() - 30.0) < 0.01


def test_threshold_and_debug_flags(tmp_path, test_logger):
    c = Container(tmp_path, "flags", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert p.get_threshold() == 2000
    assert p.set_threshold(2345)
    assert p.get_threshold() == 2345
    assert not p.is_debug_capture_enabled()
    assert p.toggle_debug_capture()
    assert p.is_debug_capture_enabled()
    assert not p.toggle_debug_capture()
    assert not p.is_debug_capture_enabled()


def test_umbral_grey_default_and_persist(tmp_path, test_logger):
    from print_scanner_app.domain.policies.perforation_roi import UMBRAL_GREY_DEFAULT

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "ugrey", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert p.get_umbral_grey() == UMBRAL_GREY_DEFAULT
    assert p.set_umbral_grey(220)
    assert p.get_umbral_grey() == 220
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("UMBRAL_GREY_PERFORACION") == 220
    assert p.set_umbral_grey(999)
    assert p.get_umbral_grey() == 255
    assert not p.is_umbralizacion_active()


def test_begin_umbralizacion_blocked_while_digitalizing(tmp_path, test_logger):
    c = Container(tmp_path, "ugblock", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    err = p.begin_umbralizacion_preview()
    assert err is not None
    assert not p.is_umbralizacion_active()


def test_perforation_side_toggle_persists_and_blocks_while_running(tmp_path, test_logger):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "pside", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert p.get_perforation_side() == "left"
    assert p.toggle_perforation_side() == "right"
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("PERFORATION_SIDE") == "right"
    assert p.get_perforation_side() == "right"
    st = c.app_state
    st.digitalizing = True
    st.pause_digitization = False
    assert p.toggle_perforation_side() is None
    assert p.get_perforation_side() == "right"
    st.pause_digitization = True
    assert p.toggle_perforation_side() == "left"


def test_can_open_camera_settings(tmp_path, test_logger):
    c = Container(tmp_path, "t", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    st = c.app_state
    st.digitalizing = False
    st.pause_digitization = False
    assert p.can_open_camera_settings()
    st.digitalizing = True
    st.pause_digitization = True
    assert p.can_open_camera_settings()
    st.pause_digitization = False
    assert not p.can_open_camera_settings()
    assert p.reject_camera_settings_reason()


def test_prepare_for_entangle_closes_sessions(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    c = Container(tmp_path, "t2", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    calls = []

    monkeypatch.setattr(p, "_close_preview_session", lambda: calls.append("prev"))
    monkeypatch.setattr(p, "_close_capture_session", lambda: calls.append("cap"))
    monkeypatch.setattr(p, "close_alignment_debug_windows", lambda: calls.append("dbg"))
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.system.mount_tools.unmount_camera_mounts",
        lambda: calls.append("umount"),
    )
    p.prepare_for_entangle()
    assert calls == ["prev", "cap", "dbg", "umount"]


def test_run_entangle_wait_uses_wait(tmp_path, test_logger):
    c = Container(tmp_path, "t3", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    order: list[str] = []

    class _Proc:
        def wait(self):
            return 0

    p._entangle_sleep = lambda s: order.append(f"sleep:{s}")

    def fake_popen(_cmd):
        order.append("popen")
        return _Proc()

    p._entangle_popen_factory = fake_popen
    assert p.run_entangle_wait() is None
    assert order[0] == f"sleep:{0.5}"
    assert order[1] == "popen"


def test_entangle_usb_release_delay_constant():
    from print_scanner_app.ui.presenters.app_presenter import ENTANGLE_USB_RELEASE_DELAY_S

    assert ENTANGLE_USB_RELEASE_DELAY_S == 0.5


def test_reset_to_espera_after_entangle_from_pause(tmp_path, test_logger):
    c = Container(tmp_path, "t4", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = True
    c.app_state.frame_count = 7
    p.reset_to_espera_after_entangle()
    assert not c.app_state.digitalizing
    assert not c.app_state.pause_digitization
    assert c.app_state.frame_count == 7


def test_is_entangle_flow_active_flag(tmp_path, test_logger):
    c = Container(tmp_path, "t5", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert not p.is_entangle_flow_active()
    p._entangle_flow_active = True
    assert p.is_entangle_flow_active()


def test_capture_tick_interval_from_config(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAPTURE_TICK_SECONDS": 0.8}), encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "ti1", test_logger), logger=test_logger)
    assert p.capture_tick_interval_seconds() == 0.8


def test_capture_tick_interval_clamped_and_fallback(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAPTURE_TICK_SECONDS": "bad"}), encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "ti2", test_logger), logger=test_logger)
    assert p.capture_tick_interval_seconds() == 0.4

    (tmp_path / "config.json").write_text(json.dumps({"CAPTURE_TICK_SECONDS": 0.001}), encoding="utf-8")
    assert p.capture_tick_interval_seconds() == 0.05

    (tmp_path / "config.json").write_text(json.dumps({"CAPTURE_TICK_SECONDS": 9}), encoding="utf-8")
    assert p.capture_tick_interval_seconds() == 5.0


def test_run_download_requires_directorio(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "dl1", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_download_pending()
    assert r.error and "directorio" in r.error.lower()


def test_run_download_no_pending(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dl2", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_download_pending()
    assert r.error and "pendientes" in r.error.lower()


def test_run_startup_invokes_service(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "SN", "CONFIG_CAMARA": {"x": 1}}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "su", test_logger)
    seen = []

    def fake_run(self, *, expected_serial, config_camera_json, reset_usb_first=True):
        seen.append((expected_serial, config_camera_json, reset_usb_first))
        return StartupOutcome(camera_assigned=True, printer_ok=True, usb_resets=0)

    monkeypatch.setattr(StartupService, "run", fake_run)
    p = AppPresenter(container=c, logger=test_logger)
    out = p.run_startup(reset_usb_first=False)
    assert out is not None and out.camera_assigned and out.printer_ok
    assert seen == [("SN", {}, False)]


def test_run_startup_without_container(test_logger):
    assert AppPresenter(logger=test_logger).run_startup() is None


def test_run_retry_camera_without_container(test_logger):
    r = AppPresenter(logger=test_logger).run_retry_camera()
    assert not r.ok and "sin Container" in (r.error or "")


def test_run_retry_camera_delegates(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "Z9", "CONFIG_CAMARA": {"a": 1}}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "retry", test_logger)
    seen = []

    class FakeUC:
        def execute(self, serial, cfg):
            seen.append((serial, cfg))
            return CameraAssignResult(ok=True, usb_address="usb:0,0", serial="Z9")

    monkeypatch.setattr(
        c,
        "retry_camera_use_case",
        lambda: FakeUC(),
    )
    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_retry_camera()
    assert r.ok and seen == [("Z9", {})]


def test_read_preview_skipped_during_raw_download(tmp_path, test_logger):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "dlblk", test_logger), logger=test_logger)
    p._raw_download_in_progress = True
    assert p.read_preview_jpeg() is None


def test_capture_tick_skipped_when_download_gate_cleared(tmp_path, test_logger):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "tickgate", test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = True
    p = AppPresenter(container=c, logger=test_logger)
    p._capture_tick_may_run.clear()
    assert p.run_capture_tick() is False
    assert not p._capture_tick_running


def test_wait_until_capture_tick_allowed_blocks_until_gate_set(tmp_path, test_logger):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    p = AppPresenter(container=Container(tmp_path, "waitgate", test_logger), logger=test_logger)
    p._capture_tick_may_run.clear()
    released = threading.Event()

    def waiter():
        p.wait_until_capture_tick_allowed()
        released.set()

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    assert not released.wait(0.15)
    p._capture_tick_may_run.set()
    assert released.wait(1.0)
    t.join(timeout=1.0)


def test_run_download_waits_for_in_flight_capture_tick(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dlwait", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    class Cam:
        def exit(self):
            pass

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(CameraService, "open_session_for_download", lambda *a, **k: (session, None))

    class FakeUC:
        def execute(self, *a, **k):
            return DownloadRawsResult(downloaded=["p.cr3"])

    monkeypatch.setattr(c, "download_raws_use_case", lambda: FakeUC())

    p = AppPresenter(container=c, logger=test_logger)
    monkeypatch.setattr(p, "_close_preview_session", lambda: None)
    monkeypatch.setattr(p, "close_alignment_debug_windows", lambda: None)
    monkeypatch.setattr(p, "_close_capture_session", lambda: None)

    order: list[str] = []
    p._capture_tick_running = True

    def release_tick_soon():
        time.sleep(0.05)
        with p._capture_tick_idle:
            p._capture_tick_running = False
            order.append("tick_idle")
            p._capture_tick_idle.notify_all()

    threading.Thread(target=release_tick_soon, daemon=True).start()

    real_wait = p._wait_capture_tick_idle

    def track_wait(timeout_s):
        order.append("wait_start")
        ok = real_wait(timeout_s)
        order.append("wait_done" if ok else "wait_fail")
        return ok

    monkeypatch.setattr(p, "_wait_capture_tick_idle", track_wait)

    r = p.run_download_pending()
    assert not r.error
    assert order[:3] == ["wait_start", "tick_idle", "wait_done"]
    assert p._capture_tick_may_run.is_set()
    assert not p._raw_download_in_progress


def test_run_download_times_out_if_capture_tick_stuck(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dltimeout", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    opened = []

    def fake_open(*a, **k):
        opened.append(1)
        return None, "no"

    monkeypatch.setattr(CameraService, "open_session_for_download", fake_open)

    p = AppPresenter(container=c, logger=test_logger)
    p._capture_tick_running = True
    monkeypatch.setattr(
        "print_scanner_app.ui.presenters.app_presenter.RAW_DOWNLOAD_CAPTURE_IDLE_TIMEOUT_S",
        0.05,
    )

    r = p.run_download_pending()
    assert r.error and "captura sigue ocupando" in r.error.lower()
    assert opened == []
    assert not p._raw_download_in_progress
    assert p._capture_tick_may_run.is_set()


def test_run_download_clears_in_progress_flag(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dl3", test_logger)
    c.raw_pending_repo.append("a.CR3", "p-00001.cr3")

    def fake_open(self, *a, **k):
        return None, "cámara no disponible"

    monkeypatch.setattr(CameraService, "open_session_for_download", fake_open)

    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_download_pending()
    assert r.error == "cámara no disponible"
    assert not p._raw_download_in_progress
    assert p._capture_tick_may_run.is_set()


def test_run_download_without_container(test_logger):
    r = AppPresenter(logger=test_logger).run_download_pending()
    assert r.error and "sin Container" in r.error


def test_reopen_camera_preview_after_download_delegates(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "reoprev", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    calls: list[int] = []
    monkeypatch.setattr(p, "_reopen_preview_session", lambda: calls.append(1))
    p.reopen_camera_preview_after_download()
    assert calls == [1]


def test_run_download_pauses_when_digitizing_active(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dlpause", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False

    pauses: list[int] = []

    class Cam:
        def exit(self):
            pass

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")

    monkeypatch.setattr(CameraService, "open_session_for_download", lambda *a, **k: (session, None))

    class FakeUC:
        def execute(self, *a, **k):
            return DownloadRawsResult(downloaded=[])

    monkeypatch.setattr(c, "download_raws_use_case", lambda: FakeUC())

    p = AppPresenter(container=c, logger=test_logger)
    real_pause = p.run_pause_digitization

    def track_pause():
        pauses.append(1)
        return real_pause()

    monkeypatch.setattr(p, "run_pause_digitization", track_pause)
    monkeypatch.setattr(p, "_close_preview_session", lambda: None)

    r = p.run_download_pending()
    assert not r.error
    assert pauses == [1]


def test_run_download_success_calls_camera_exit(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dl4", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    class Cam:
        def __init__(self):
            self.exits = 0

        def exit(self):
            self.exits += 1

    cam = Cam()
    session = CameraSession(gp=None, camera=cam, usb_address="usb:0")

    def fake_open(self, *a, **k):
        return session, None

    monkeypatch.setattr(CameraService, "open_session_for_download", fake_open)

    class FakeUC:
        def execute(self, *a, **k):
            return DownloadRawsResult(downloaded=["p.cr3"], batch_folder="m-1")

    monkeypatch.setattr(c, "download_raws_use_case", lambda: FakeUC())

    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_download_pending()
    assert not r.error and cam.exits == 1


def test_run_download_ignores_exit_exception(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dl5", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    class Cam:
        def exit(self):
            raise RuntimeError("boom")

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")

    monkeypatch.setattr(
        CameraService,
        "open_session_for_download",
        lambda self, *a, **k: (session, None),
    )

    class FakeUC:
        def execute(self, *a, **k):
            return DownloadRawsResult(downloaded=[])

    monkeypatch.setattr(c, "download_raws_use_case", lambda: FakeUC())
    r = AppPresenter(container=c, logger=test_logger).run_download_pending()
    assert not r.error


def test_pause_calls_gc_after_session_closes(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "pausegc", test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    p = AppPresenter(container=c, logger=test_logger)
    order: list[str] = []

    monkeypatch.setattr(p, "_clear_alignment_debug_all", lambda: order.append("clear"))
    monkeypatch.setattr(p, "_close_capture_session", lambda: order.append("close_cap"))
    monkeypatch.setattr(p, "close_alignment_debug_windows", lambda: order.append("close_cv"))
    monkeypatch.setattr(p, "_gc_after_gphoto_session_boundary", lambda: order.append("gc"))

    assert p.run_pause_digitization().ok
    assert order == ["clear", "close_cap", "close_cv", "gc"]


def test_run_download_calls_gc_before_open_and_after_exit(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dlgc", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    order: list[str] = []

    class Cam:
        def exit(self):
            order.append("exit")

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")

    def fake_open(self, *a, **k):
        order.append("open")
        return session, None

    monkeypatch.setattr(CameraService, "open_session_for_download", fake_open)

    class FakeUC:
        def execute(self, *a, **k):
            order.append("exec")
            return DownloadRawsResult(downloaded=["p.cr3"])

    monkeypatch.setattr(c, "download_raws_use_case", lambda: FakeUC())

    p = AppPresenter(container=c, logger=test_logger)
    monkeypatch.setattr(p, "_close_preview_session", lambda: order.append("close_prev"))
    monkeypatch.setattr(p, "close_alignment_debug_windows", lambda: None)
    monkeypatch.setattr(p, "_close_capture_session", lambda: None)

    real_gc = p._gc_after_gphoto_session_boundary

    def track_gc():
        order.append("gc")
        real_gc()

    monkeypatch.setattr(p, "_gc_after_gphoto_session_boundary", track_gc)

    r = p.run_download_pending()
    assert not r.error
    assert order == ["close_prev", "gc", "open", "exec", "exit", "gc"]


def test_run_download_gc_before_open_even_if_session_fails(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path / "out")}),
        encoding="utf-8",
    )
    (tmp_path / "out").mkdir()
    c = Container(tmp_path, "dlgc2", test_logger)
    c.raw_pending_repo.append("a.CR3", "p.cr3")

    gcs: list[int] = []

    monkeypatch.setattr(
        CameraService,
        "open_session_for_download",
        lambda self, *a, **k: (None, "fail"),
    )

    p = AppPresenter(container=c, logger=test_logger)
    monkeypatch.setattr(p, "_close_preview_session", lambda: None)
    monkeypatch.setattr(p, "close_alignment_debug_windows", lambda: None)
    monkeypatch.setattr(p, "_gc_after_gphoto_session_boundary", lambda: gcs.append(1))

    r = p.run_download_pending()
    assert r.error == "fail"
    assert gcs == [1]


def test_config_camara_non_dict_normalized(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "S1", "CONFIG_CAMARA": ["x"]}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "norm", test_logger)
    seen: list = []

    class FakeUC:
        def execute(self, serial, cfg):
            seen.append((serial, cfg))
            return CameraAssignResult(ok=True)

    monkeypatch.setattr(c, "retry_camera_use_case", lambda: FakeUC())
    AppPresenter(container=c, logger=test_logger).run_retry_camera()
    assert seen == [("S1", {})]


def test_digitization_flow_via_presenter(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "dig", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            pass

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    names = iter([f"F{i:04d}.CR3" for i in range(1, 10)])
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: next(names, None))
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    assert p.run_start_digitization().ok
    assert c.app_state.digitalizing and not c.app_state.pause_digitization
    assert "Digitalización: activa" in p.status_hint()
    assert p.run_pause_digitization().ok and c.app_state.pause_digitization
    assert "Digitalización: pausada" in p.status_hint()
    assert p.run_resume_digitization().ok and not c.app_state.pause_digitization
    assert "Digitalización: activa" in p.status_hint()
    assert p.run_capture_tick()
    assert c.app_state.frame_count == 1
    assert p.pending_raw_count() == 1
    assert "Frames: 1" in p.status_hint()
    assert p.run_stop_digitization().ok
    assert "Digitalización: detenida" in p.status_hint()


def test_digitization_pause_resume_without_container(test_logger):
    p = AppPresenter(logger=test_logger)
    assert not p.run_start_digitization().ok
    assert not p.run_pause_digitization().ok
    assert not p.run_resume_digitization().ok
    assert not p.run_stop_digitization().ok


def test_pause_resume_without_start(tmp_path, test_logger):
    c = Container(tmp_path, "dig2", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert not p.run_pause_digitization().ok
    assert not p.run_resume_digitization().ok


def test_run_capture_tick_without_container(test_logger):
    assert not AppPresenter(logger=test_logger).run_capture_tick()


def test_capture_tick_real_session_deduplicates(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "capreal", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def __init__(self):
            self.exits = 0

        def exit(self):
            self.exits += 1

    cam = Cam()
    session = CameraSession(gp=None, camera=cam, usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    _patch_immediate_shoot_stack(monkeypatch, latest_cr3="_MG_0001.CR3")
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    assert c.app_state.frame_count == 1
    assert p.run_capture_tick()
    assert c.app_state.frame_count == 2
    assert p.pending_raw_count() == 2
    assert p.run_stop_digitization().ok
    assert cam.exits >= 1


def test_capture_tick_real_reopens_session_on_trigger_error(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "capreopen", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def __init__(self):
            self.exits = 0

        def exit(self):
            self.exits += 1

    cam1 = Cam()
    cam2 = Cam()
    sessions = iter(
        [
            (CameraSession(gp=None, camera=cam1, usb_address="usb:1"), None),
            (CameraSession(gp=None, camera=cam2, usb_address="usb:1"), None),
        ]
    )
    monkeypatch.setattr(CameraService, "open_session_for_capture", lambda self, *a, **k: next(sessions))
    _patch_immediate_shoot_stack(monkeypatch, latest_cr3="_MG_0001.CR3")
    monkeypatch.setattr(
        CameraService,
        "capture_raw_name",
        lambda self, _s: None,
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    assert p.run_start_digitization().ok
    assert not p.run_capture_tick()
    assert c.app_state.pause_digitization
    assert p._capture_last_error


def test_capture_tick_advances_printer_with_config_pattern(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "FORMATO_DIGITALIZAR": "16mm",
                "PRINTER_PATTERN_16MM": [22, 23],
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "prnpat", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            pass

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    names = iter(["_MG_0002.CR3", "_MG_0003.CR3"])
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: next(names))
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))

    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px):
            moved.append(px)
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    assert p.run_capture_tick()
    assert moved == [22, 23]


def _jpeg_bytes(fill: int) -> bytes:
    """
    Stub de preview.

    ``fill >= 200``: aire + rail + sprocket en banda Y 16mm (alineado con umbral ~100).
    Valores bajos: plano uniforme (no alineado con el detector dinámico).
    """
    import numpy as np

    w, h = 640, 480
    if fill >= 200:
        arr = np.full((h, w, 3), 100, dtype=np.uint8)
        arr[:, :50] = 255
        arr[:, 50:200] = 40
        # Cubrir bandas Y 16mm (155–235) y 35mm (70–155)
        arr[90:140, 90:140] = 255  # 50×50
        arr[165:215, 90:140] = 255
    else:
        arr = np.full((h, w, 3), int(fill), dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_capture_tick_skips_shot_when_not_aligned(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 2000,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "aligskip", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(0))
    shot_calls = {"n": 0}

    def _capture_raw_name(_self, _sess):
        shot_calls["n"] += 1
        return "_MG_0002.CR3"

    monkeypatch.setattr(CameraService, "capture_raw_name", _capture_raw_name)
    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px):
            moved.append(px)
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    assert p.run_start_digitization().ok
    assert not p.run_capture_tick()
    assert shot_calls["n"] == 0
    assert moved == [1]


def test_capture_tick_no_shot_without_alignment_preview(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    """Sin JPEG de alineación no se dispara RAW (§3.1c criterio 1)."""
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "no-prev", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    monkeypatch.setattr(p, "_capture_preview_for_alignment", lambda: None)
    shot_calls = {"n": 0}

    def _cap(_self, _s):
        shot_calls["n"] += 1
        return "X.CR3"

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_raw_name", _cap)
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())
    assert p.run_start_digitization().ok
    assert not p.run_capture_tick()
    assert shot_calls["n"] == 0


def test_trigger_and_read_raw_name_no_second_fallback(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    """El fallback acotado vive en gphoto; el presenter no hace un segundo walk."""
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "raw-fb", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    session = CameraSession(gp=None, camera=object(), usb_address="usb:0")
    p._capture_session = session
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "")
    called = {"n": 0}

    def _should_not_call(self, _s, _c=None):
        called["n"] += 1
        return "FALLBACK.CR3"

    monkeypatch.setattr(CameraService, "find_latest_raw_name", _should_not_call)
    assert p._trigger_and_read_raw_name() is None
    assert called["n"] == 0


def test_post_align_move_before_liveview_preview(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    """Tras alineación: move_film ocurre antes del capture_preview de UI."""
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
                "FORMATO_DIGITALIZAR": "16mm",
                "PRINTER_PATTERN_16MM": [10],
                "DEBUG_PREVIEW_BURST": 1,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "order-mv", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    order: list[str] = []

    def preview(self, _s):
        order.append("preview")
        return _jpeg_bytes(255)

    def move_film(self, px):
        order.append(f"move:{px}")
        return True

    def capture(self, _s):
        order.append("capture")
        return "_MG_0002.CR3"

    monkeypatch.setattr(CameraService, "capture_preview_jpeg", preview)
    monkeypatch.setattr(CameraService, "capture_raw_name", capture)
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": move_film})())

    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    assert "capture" in order
    assert "move:10" in order
    assert order.index("capture") < order.index("move:10")
    assert order.index("move:10") < order.index("preview", order.index("move:10"))
    assert p.last_captured_preview_jpeg() is not None


def test_capture_without_raw_name_pauses(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
                "DEBUG_PREVIEW_BURST": 1,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "no-raw", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: None)
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    assert p.run_start_digitization().ok
    assert not p.run_capture_tick()
    assert c.app_state.pause_digitization
    assert p._capture_last_error


def test_alignment_timeout_pauses_and_invokes_callback(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 50000,
                "UMBRAL_GREY_PERFORACION": 245,
                "FORMATO_DIGITALIZAR": "16mm",
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "alto", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(0))
    shot_calls = {"n": 0}

    def _no_shot(_self, _sess):
        shot_calls["n"] += 1
        return "X.CR3"

    monkeypatch.setattr(CameraService, "capture_raw_name", _no_shot)
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    invoked: list[int] = []
    p.set_alignment_timeout_callback(lambda: invoked.append(1))
    assert p.run_start_digitization().ok
    from print_scanner_app.domain.policies.alignment_constants import ALIGNMENT_MAX_INTENTOS

    for _ in range(ALIGNMENT_MAX_INTENTOS):
        assert not p.run_capture_tick()
    assert c.app_state.pause_digitization
    assert invoked == [1]
    assert shot_calls["n"] == 0


def test_35mm_mid_phase_moves_pattern_without_extra_capture(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "FORMATO_DIGITALIZAR": "35mm",
                "PRINTER_PATTERN_35MM": [30],
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "35mid", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    raw_calls = {"n": 0}

    def cap(_self, _s):
        raw_calls["n"] += 1
        return "_MG_0002.CR3"

    monkeypatch.setattr(CameraService, "capture_raw_name", cap)
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px):
            moved.append(int(px))
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    assert raw_calls["n"] == 1
    assert moved == [30]
    assert not p.run_capture_tick()
    assert raw_calls["n"] == 1
    assert moved == [30, 30]


def test_capture_tick_shoots_when_aligned(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "aligok", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_0002.CR3")

    class FakePrinter:
        def move_film(self, _px):
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    assert p.run_start_digitization().ok
    assert p.run_capture_tick()


def test_debug_step_e_moves_one_px_and_recaptures_debug(
    tmp_path,
    test_logger,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 2000,
                "UMBRAL_GREY_PERFORACION": 245,
                "FORMATO_DIGITALIZAR": "35mm",
                "PRINTER_PATTERN_35MM": [22],
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "step-e", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True
    p._debug_step_requested = True
    p._capture_session = object()
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False

    monkeypatch.setattr(
        p,
        "_analyze_alignment_from_jpeg",
        lambda _jpeg: SimpleNamespace(aligned=False, white_pixel_count=0),
    )
    monkeypatch.setattr(
        CameraService,
        "capture_preview_jpeg",
        lambda self, _s: _jpeg_bytes(0),
    )
    monkeypatch.setattr(
        p,
        "_trigger_and_read_raw_name",
        lambda: (_ for _ in ()).throw(AssertionError("no debe disparar RAW en paso debug")),
    )
    refreshed = {"n": 0}
    monkeypatch.setattr(
        p,
        "_run_alignment_debug_visualization",
        lambda _jpeg: refreshed.__setitem__("n", refreshed["n"] + 1) or True,
    )
    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px):
            moved.append(px)
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())
    # Primer tick en debug: construye frame/contexto y entra en waiting.
    assert not p.run_capture_tick()
    p._debug_step_requested = True
    p._debug_alignment_waiting = False
    # Segundo tick con E: aplica paso 1px + recaptura debug.
    assert not p.run_capture_tick()
    assert moved == [1]
    assert refreshed["n"] == 2
    assert not p._debug_step_requested


def test_debug_gate_pending_after_start_with_debug_ui(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "gate1", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )

    assert not p._debug_digitization_gate_pending
    assert p.run_start_digitization().ok
    assert p._debug_digitization_gate_pending


def test_debug_gate_cleared_after_first_debug_show(
    tmp_path,
    test_logger,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "UMBRAL_PX_BLANCOS": 2000, "UMBRAL_GREY_PERFORACION": 245}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "gate2", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(0))
    monkeypatch.setattr(
        p,
        "_analyze_alignment_from_jpeg",
        lambda _jpeg: SimpleNamespace(aligned=False, white_pixel_count=0),
    )
    monkeypatch.setattr(p, "_run_alignment_debug_visualization", lambda _jpeg: True)

    assert p.run_start_digitization().ok
    assert p._debug_digitization_gate_pending
    assert not p.run_capture_tick()
    assert not p._debug_digitization_gate_pending


def test_debug_first_tick_no_move_film_with_gate(
    tmp_path,
    test_logger,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "UMBRAL_PX_BLANCOS": 2000, "UMBRAL_GREY_PERFORACION": 245}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "gate3", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True
    moved: list[int] = []

    class FakePrinter:
        def move_film(self, px: int) -> bool:
            moved.append(int(px))
            return True

    monkeypatch.setattr(c, "printer_service", lambda: FakePrinter())

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(0))
    monkeypatch.setattr(
        p,
        "_analyze_alignment_from_jpeg",
        lambda _jpeg: SimpleNamespace(aligned=False, white_pixel_count=0),
    )
    monkeypatch.setattr(p, "_run_alignment_debug_visualization", lambda _jpeg: True)

    assert p.run_start_digitization().ok
    assert not p.run_capture_tick()
    assert moved == []


def test_debug_gate_pause_clears_resume_sets(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "gate4", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )

    assert p.run_start_digitization().ok
    assert p._debug_digitization_gate_pending
    assert p.run_pause_digitization().ok
    assert not p._debug_digitization_gate_pending
    assert p.run_resume_digitization().ok
    assert p._debug_digitization_gate_pending


def test_debug_on_without_capture_session_does_not_increment_frame(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "nodbgframe", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    p._capture_session = None
    before = c.app_state.frame_count
    assert not p.run_capture_tick()
    assert c.app_state.frame_count == before


def test_debug_preview_burst_five_jpeg_reads(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    c = Container(tmp_path, "burst", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    calls: list[int] = []

    def capture_preview(_self, _s):
        calls.append(1)
        return _jpeg_bytes(128)

    monkeypatch.setattr(CameraService, "capture_preview_jpeg", capture_preview)
    p._capture_session = object()
    assert p._capture_one_debug_preview_burst() is not None
    assert len(calls) == 5


def test_start_digitization_blocked_without_printer(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.ui.presenters.app_presenter._printer_lp_available",
        lambda: False,
    )
    c = Container(tmp_path, "noprint", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_start_digitization()
    assert not r.ok
    assert "impresora" in (r.error or "").lower()


def test_start_digitization_rolls_back_when_camera_unavailable(tmp_path, test_logger, monkeypatch):
    c = Container(tmp_path, "nocamroll", test_logger)
    monkeypatch.setattr(CameraService, "open_session_for_capture", lambda *a, **k: (None, "fail"))
    p = AppPresenter(container=c, logger=test_logger)
    reopen: list[int] = []
    monkeypatch.setattr(p, "_try_open_preview_session", lambda: reopen.append(1))
    r = p.run_start_digitization()
    assert not r.ok
    assert "cámara" in (r.error or "").lower()
    assert not c.app_state.digitalizing
    assert reopen == [1]


def test_release_camera_sessions_for_exit_closes_preview_and_capture(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "exitcam", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    prev = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    cap = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    p._preview_session = prev
    p._capture_session = cap
    closed: list[str] = []

    def _close(sess):
        closed.append(sess.usb_address)

    monkeypatch.setattr(CameraService, "close_session", lambda self, s: _close(s) if s else None)
    p.release_camera_sessions_for_exit()
    assert p._preview_session is None
    assert p._capture_session is None
    assert len(closed) == 2
    # Segunda llamada idempotente (sin sesión no debe fallar).
    p.release_camera_sessions_for_exit()


def test_release_camera_sessions_for_exit_skips_settle_when_disabled(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "exitsettle", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    slept: list[float] = []
    monkeypatch.setattr(ap_mod.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(CameraService, "close_session", lambda self, s: None)
    # Forzar settle>0 para distinguir skip vs autouse CAMERA_EXIT_SETTLE_S=0.
    monkeypatch.setattr(ap_mod, "CAMERA_EXIT_SETTLE_S", 0.75)
    p.release_camera_sessions_for_exit(settle=False)
    assert slept == []
    assert p._preview_session is None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:1")
    p.release_camera_sessions_for_exit(settle=True)
    assert slept == [0.75]


def test_wait_for_camera_idle_before_exit_blocks_new_ticks(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "exitidle", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    waits: list[str] = []

    monkeypatch.setattr(
        p,
        "_wait_capture_tick_idle",
        lambda t: waits.append(f"cap:{t}") or True,
    )
    monkeypatch.setattr(
        p,
        "_wait_preview_io_idle",
        lambda t: waits.append(f"prev:{t}") or True,
    )
    assert p._capture_tick_may_run.is_set()
    p.wait_for_camera_idle_before_exit(capture_idle_timeout_s=2.0, preview_idle_timeout_s=2.0)
    assert not p._capture_tick_may_run.is_set()
    assert waits == ["cap:2.0", "prev:2.0"]


def test_exit_via_use_case_can_skip_camera_release(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "exitrel", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    calls: list[str] = []
    monkeypatch.setattr(
        p,
        "release_camera_sessions_for_exit",
        lambda **kw: calls.append(f"rel:{kw}"),
    )
    assert p.exit_via_use_case(release_camera=False).ok
    assert calls == []
    assert p.exit_via_use_case(release_camera=True).ok
    assert calls == ["rel:{'settle': False}"]


def test_resume_digitization_reverts_pause_when_camera_fails(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "resumfail", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            pass

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(CameraService, "open_session_for_capture", lambda self, *a, **k: (session, None))

    assert p.run_start_digitization().ok
    assert p.run_pause_digitization().ok
    monkeypatch.setattr(CameraService, "open_session_for_capture", lambda *a, **k: (None, "fail"))
    r = p.run_resume_digitization()
    assert not r.ok
    assert c.app_state.pause_digitization
    assert "cámara" in (r.error or "").lower()


def test_printer_clean_pause_and_popup_at_interval(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "PRINTER_CLEAN_FRAME_INTERVAL", 2)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "pc500", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    names = iter(["_MG_0002.CR3", "_MG_0003.CR3"])
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: next(names))
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    popup_calls: list[int] = []
    refresh_calls: list[int] = []
    p.register_printer_clean_popup_callback(lambda: popup_calls.append(1))
    p.register_printer_clean_refresh_status_callback(lambda: refresh_calls.append(1))

    class FakeClock:
        @staticmethod
        def schedule_once(cb, t=0):
            cb(0)

    _install_fake_kivy_clock(monkeypatch, FakeClock)

    assert p.run_start_digitization().ok
    assert not c.app_state.pause_digitization
    assert p.run_capture_tick()
    assert c.app_state.frame_count == 1
    assert popup_calls == []
    assert p.run_capture_tick()
    assert c.app_state.frame_count == 2
    assert c.app_state.pause_digitization
    assert p.get_last_printer_clean_pause_frame() == 2
    assert popup_calls == [1]
    assert refresh_calls == [1]


def test_printer_clean_skips_when_debug_ui_active(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "PRINTER_CLEAN_FRAME_INTERVAL", 2)
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "pcdbg", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._mostrar_debug_ui = True
    c.app_state.frame_count = 2
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    popup_calls: list[int] = []
    p.register_printer_clean_popup_callback(lambda: popup_calls.append(1))
    p._maybe_schedule_printer_clean_maintenance()
    assert popup_calls == []
    assert not c.app_state.pause_digitization


def test_printer_clean_not_scheduled_when_advance_film_fails(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "PRINTER_CLEAN_FRAME_INTERVAL", 2)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "pcfail", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    names = iter(["_MG_0002.CR3", "_MG_0003.CR3"])
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: next(names))
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    moves = {"n": 0}

    class BadPrinter:
        def move_film(self, px):
            moves["n"] += 1
            return moves["n"] == 1

    monkeypatch.setattr(c, "printer_service", lambda: BadPrinter())

    popup_calls: list[int] = []
    p.register_printer_clean_popup_callback(lambda: popup_calls.append(1))

    class FakeClock:
        @staticmethod
        def schedule_once(cb, t=0):
            cb(0)

    _install_fake_kivy_clock(monkeypatch, FakeClock)

    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    assert not p.run_capture_tick()
    assert c.app_state.pause_digitization
    assert popup_calls == []


def test_printer_clean_latch_reset_on_stop(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "pcstop", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._last_printer_clean_pause_frame = 500
    c.app_state.digitalizing = True
    assert p.run_stop_digitization().ok
    assert p.get_last_printer_clean_pause_frame() is None


def test_printer_clean_warns_when_popup_callback_missing(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    import logging

    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "PRINTER_CLEAN_FRAME_INTERVAL", 2)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "pcnopop", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    names = iter(["_MG_0002.CR3", "_MG_0003.CR3"])
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: next(names))
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())
    p.register_printer_clean_popup_callback(None)
    p.register_printer_clean_refresh_status_callback(lambda: None)

    class FakeClock:
        @staticmethod
        def schedule_once(cb, t=0):
            cb(0)

    _install_fake_kivy_clock(monkeypatch, FakeClock)

    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    with caplog.at_level(logging.WARNING):
        assert p.run_capture_tick()
    assert c.app_state.pause_digitization
    assert any("no registrado" in r.getMessage().lower() for r in caplog.records)


def test_hydrate_numero_frame_from_config_valid(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "NUMERO_FRAME": 42}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "nf1", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p.hydrate_numero_frame_from_config()
    assert c.app_state.frame_count == 42


def test_hydrate_numero_frame_invalid_normalizes_config(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "NUMERO_FRAME": "oops"}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "nf2", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p.hydrate_numero_frame_from_config()
    assert c.app_state.frame_count == 0
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data.get("NUMERO_FRAME") == 0


def test_increment_and_set_frame_persist_numero_frame(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "NUMERO_FRAME": 1}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "nf3", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p.hydrate_numero_frame_from_config()
    assert p.get_frame() == 1
    assert p.increment_frame(2) == 3
    assert p.get_frame() == 3
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data.get("NUMERO_FRAME") == 3
    assert p.set_frame(10) == 10
    assert p.get_frame() == 10
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data.get("NUMERO_FRAME") == 10


def _make_presenter_with_session(tmp_path, test_logger, monkeypatch, *, raw_name="_MG_0002.CR3", move_film_ok=True):
    """Helper: presenter con sesión de captura simulada, listo para correr capture_tick."""
    import json

    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "NUMERO_FRAME": 0, "UMBRAL_PX_BLANCOS": 100}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "defer_pause", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p.hydrate_numero_frame_from_config()

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(CameraService, "open_session_for_capture", lambda self, *a, **k: (session, None))
    _patch_immediate_shoot_stack(monkeypatch, latest_cr3="_MG_0001.CR3")
    # raw_name legacy ignorado: el flujo usa predicción desde latest_cr3
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(200))
    monkeypatch.setattr(
        c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: move_film_ok})()
    )
    assert p.run_start_digitization().ok
    return p, c


def test_pause_during_critical_section_is_deferred(tmp_path, test_logger, monkeypatch):
    """
    Si run_pause_digitization() es llamado mientras _capture_critical_section_active=True,
    la pausa se difiere: pause_pending=True pero pause_digitization sigue False hasta salir de la sección.
    """
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)

    # Activamos manualmente la sección crítica y solicitamos pausa
    p._capture_critical_section_active = True
    result = p.run_pause_digitization()

    # La pausa fue "aceptada" (ok=True) pero diferida
    assert result.ok is True
    assert c.app_state.pause_pending is True
    assert c.app_state.pause_digitization is False  # todavía no aplicada

    # Al salir de la sección crítica, se debe finalizar la pausa
    p._capture_critical_section_active = False
    p._finalize_deferred_pause()

    assert c.app_state.pause_digitization is True
    assert c.app_state.pause_pending is False


def test_deferred_pause_blocks_camera_access(tmp_path, test_logger, monkeypatch):
    """
    Mientras pause_pending=True, _camera_access_blocked() retorna True.
    """
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    assert p.run_start_digitization().ok or True  # ya iniciada en make_presenter
    c.app_state.pause_pending = True
    assert p._camera_access_blocked() is True
    c.app_state.pause_pending = False
    assert p._camera_access_blocked() is False


def test_critical_section_active_blocks_camera_access(tmp_path, test_logger, monkeypatch):
    """
    Mientras _capture_critical_section_active=True, _camera_access_blocked() retorna True.
    """
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    p._capture_critical_section_active = True
    assert p._camera_access_blocked() is True
    p._capture_critical_section_active = False
    assert p._camera_access_blocked() is False


def test_finalize_deferred_pause_applies_full_pause(tmp_path, test_logger, monkeypatch):
    """
    _finalize_deferred_pause() convierte pause_pending en pause_digitization real.
    """
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    c.app_state.pause_pending = True
    c.app_state.pause_digitization = False
    p._finalize_deferred_pause()
    assert c.app_state.pause_digitization is True
    assert c.app_state.pause_pending is False


def test_pause_accepted_and_capture_closed_callbacks_immediate(tmp_path, test_logger, monkeypatch):
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    events: list[str] = []
    p.register_pause_accepted_callback(lambda: events.append("accepted"))
    p.register_pause_capture_closed_callback(lambda: events.append("closed"))
    assert p.run_pause_digitization().ok
    assert events == ["accepted", "closed"]


def test_pause_deferred_emits_accepted_then_closed_on_finalize(tmp_path, test_logger, monkeypatch):
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    events: list[str] = []
    p.register_pause_accepted_callback(lambda: events.append("accepted"))
    p.register_pause_capture_closed_callback(lambda: events.append("closed"))
    p._capture_critical_section_active = True
    assert p.run_pause_digitization().ok
    assert events == ["accepted"]
    assert c.app_state.pause_pending is True
    p._capture_critical_section_active = False
    p._finalize_deferred_pause()
    assert events == ["accepted", "closed"]


def test_pause_transitioning_blocks_camera_settings(tmp_path, test_logger, monkeypatch):
    p, c = _make_presenter_with_session(tmp_path, test_logger, monkeypatch)
    c.app_state.digitalizing = False
    assert p.can_open_camera_settings()
    p.begin_pause_transition()
    assert not p.can_open_camera_settings()
    p.end_pause_transition()
    assert p.can_open_camera_settings()


def test_observe_raw_persists_numero_frame_via_callback(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "CAMARA": "X",
                "NUMERO_FRAME": 0,
                "UMBRAL_PX_BLANCOS": 100,
                "UMBRAL_GREY_PERFORACION": 245,
            }
        ),
        encoding="utf-8",
    )
    c = Container(tmp_path, "nf4", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p.hydrate_numero_frame_from_config()

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_0002.CR3")
    monkeypatch.setattr(CameraService, "capture_preview_jpeg", lambda self, _s: _jpeg_bytes(255))
    monkeypatch.setattr(c, "printer_service", lambda: type("P", (), {"move_film": lambda self, px: True})())

    assert p.run_start_digitization().ok
    assert p.run_capture_tick()
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data.get("NUMERO_FRAME") == 1
    assert c.app_state.frame_count == 1


def test_frame_by_frame_idle_enqueues_without_digitalizing(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_idle", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "open_session_for_capture",
        lambda self, *a, **k: (session, None),
    )
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_1001.CR3")
    moves: list[int] = []
    monkeypatch.setattr(
        c,
        "printer_service",
        lambda: type("P", (), {"move_film": lambda self, px: moves.append(px) or True})(),
    )

    assert not c.app_state.digitalizing
    r = p.run_capture_frame_by_frame()
    assert r.ok
    assert not c.app_state.digitalizing
    assert c.app_state.frame_count == 1
    assert p.pending_raw_count() == 1
    assert p.last_captured_raw_name() == "_MG_1001.CR3"
    assert moves == []
    assert not p.is_frame_by_frame_busy()


def test_frame_by_frame_works_when_paused(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_pause", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = True
    c.app_state.frame_count = 5

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    p._preview_session = session
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_0002.CR3")

    r = p.run_capture_frame_by_frame()
    assert r.ok
    assert c.app_state.digitalizing and c.app_state.pause_digitization
    assert c.app_state.frame_count == 6
    assert p.pending_raw_count() == 1


def test_frame_by_frame_blocked_while_digitizing_active(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_block", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.digitalizing = True
    c.app_state.pause_digitization = False
    r = p.run_capture_frame_by_frame()
    assert not r.ok
    assert "Pausá" in (r.error or "")
    assert c.app_state.frame_count == 0


def test_frame_by_frame_requires_directory(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "fxf_nodir", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    r = p.run_capture_frame_by_frame()
    assert not r.ok
    assert "directorio" in (r.error or "").lower()


def test_frame_by_frame_ignores_reentry_while_busy(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_busy", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._frame_by_frame_busy = True
    r = p.run_capture_frame_by_frame()
    assert r.ok
    assert c.app_state.frame_count == 0
    assert p.pending_raw_count() == 0


def test_frame_by_frame_printer_clean_popup_without_pause(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    import print_scanner_app.ui.presenters.app_presenter as ap_mod

    monkeypatch.setattr(ap_mod, "PRINTER_CLEAN_FRAME_INTERVAL", 2)
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_clean", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    c.app_state.frame_count = 1

    class Cam:
        def exit(self):
            return None

    session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    p._preview_session = session
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_0002.CR3")

    popup_calls: list[int] = []
    refresh_calls: list[int] = []
    p.register_printer_clean_popup_callback(lambda: popup_calls.append(1))
    p.register_printer_clean_refresh_status_callback(lambda: refresh_calls.append(1))

    class FakeClock:
        @staticmethod
        def schedule_once(cb, t=0):
            cb(0)

    _install_fake_kivy_clock(monkeypatch, FakeClock)

    r = p.run_capture_frame_by_frame()
    assert r.ok
    assert c.app_state.frame_count == 2
    assert not c.app_state.digitalizing
    assert not c.app_state.pause_digitization
    assert p.get_last_printer_clean_pause_frame() == 2
    assert popup_calls == [1]
    assert refresh_calls == [1]


def test_frame_by_frame_camera_access_blocked_while_busy(tmp_path, test_logger):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "fxf_camblock", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    assert not p._camera_access_blocked()
    p._frame_by_frame_busy = True
    assert p._camera_access_blocked()
    assert p.is_frame_by_frame_busy()


def test_is_gphoto_io_in_progress_error():
    assert AppPresenter._is_gphoto_io_in_progress_error(RuntimeError("[-110] I/O in progress"))
    assert AppPresenter._is_gphoto_io_in_progress_error(RuntimeError("i/o in progress"))
    assert not AppPresenter._is_gphoto_io_in_progress_error(RuntimeError("camera busy -53"))


def test_read_preview_jpeg_skips_when_frame_by_frame_busy(tmp_path, test_logger, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "fxf_prev", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    called = []

    class Cam:
        def exit(self):
            return None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(
        CameraService,
        "capture_preview_jpeg",
        lambda self, _s: called.append(1) or b"jpeg",
    )
    p._frame_by_frame_busy = True
    assert p.read_preview_jpeg() is None
    assert called == []
    assert not p._preview_io_in_progress


def test_frame_by_frame_waits_for_preview_io_idle(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_wait", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    wait_calls: list[float] = []
    monkeypatch.setattr(
        p,
        "_wait_preview_io_idle",
        lambda timeout_s: wait_calls.append(timeout_s) or True,
    )
    monkeypatch.setattr(CameraService, "capture_raw_name", lambda self, _s: "_MG_0002.CR3")

    assert p.run_capture_frame_by_frame().ok
    assert wait_calls and wait_calls[0] > 0
    assert c.app_state.frame_count == 1


def test_frame_by_frame_retries_once_on_io_in_progress(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_retry", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    attempts = {"n": 0}

    def _cap(_self, _s):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("[-110] I/O in progress")
        return "RETRY.CR3"

    monkeypatch.setattr(p, "_wait_preview_io_idle", lambda _t: True)
    monkeypatch.setattr(CameraService, "capture_raw_name", _cap)

    r = p.run_capture_frame_by_frame()
    assert r.ok
    assert attempts["n"] == 2
    assert c.app_state.frame_count == 1
    assert p.last_captured_raw_name() == "RETRY.CR3"


def test_frame_by_frame_fails_if_retry_also_io_in_progress(
    tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "config.json").write_text(
        json.dumps({"CAMARA": "X", "DIRECTORIO": str(tmp_path)}),
        encoding="utf-8",
    )
    c = Container(tmp_path, "fxf_retry_fail", test_logger)
    p = AppPresenter(container=c, logger=test_logger)

    class Cam:
        def exit(self):
            return None

    p._preview_session = CameraSession(gp=None, camera=Cam(), usb_address="usb:0")
    monkeypatch.setattr(p, "_wait_preview_io_idle", lambda _t: True)
    monkeypatch.setattr(
        CameraService,
        "capture_raw_name",
        lambda self, _s: (_ for _ in ()).throw(RuntimeError("[-110] I/O in progress")),
    )

    r = p.run_capture_frame_by_frame()
    assert not r.ok
    assert "I/O in progress" in (r.error or "")
    assert c.app_state.frame_count == 0
    assert not p.is_frame_by_frame_busy()


def test_wait_preview_io_idle_times_out(tmp_path, test_logger, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.json").write_text(json.dumps({"CAMARA": "X"}), encoding="utf-8")
    c = Container(tmp_path, "fxf_to", test_logger)
    p = AppPresenter(container=c, logger=test_logger)
    p._preview_io_in_progress = True
    monkeypatch.setattr(
        "print_scanner_app.ui.presenters.app_presenter.FRAME_BY_FRAME_PREVIEW_IDLE_TIMEOUT_S",
        0.05,
    )
    # Direct unit of wait with tiny timeout
    assert not p._wait_preview_io_idle(0.05)
