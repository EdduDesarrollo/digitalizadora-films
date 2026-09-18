import logging
from pathlib import Path
import pytest

from print_scanner_app.application.services.capture_service import CaptureService
from print_scanner_app.application.services.shutdown_service import ShutdownService
from print_scanner_app.application.services.startup_service import StartupService
from print_scanner_app.application.use_cases.exit_app import ExitAppUseCase
from print_scanner_app.application.use_cases.pause_digitization import PauseDigitizationUseCase
from print_scanner_app.application.use_cases.resume_digitization import ResumeDigitizationUseCase
from print_scanner_app.application.use_cases.retry_camera import RetryCameraUseCase
from print_scanner_app.application.use_cases.start_digitization import StartDigitizationUseCase
from print_scanner_app.application.use_cases.stop_digitization import StopDigitizationUseCase
from print_scanner_app.app.bootstrap import bootstrap, parse_args
from print_scanner_app.app.container import Container, default_container


def test_parse_args_log_level():
    a = parse_args(["--log-level", "DEBUG"])
    assert a.log_level == "DEBUG"


def test_parse_args_startup_flags():
    a = parse_args(["--no-startup", "--no-usb-reset-on-startup"])
    assert a.no_startup is True
    assert a.no_usb_reset_on_startup is True


def test_bootstrap_returns_logger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    logs = tmp_path / "print_scanner_app" / "logs"
    logs.mkdir(parents=True)

    def fake_root(here: Path):
        return tmp_path

    monkeypatch.setattr("print_scanner_app.app.bootstrap.project_root_from_here", fake_root)
    args, logger = bootstrap(["--log-level", "WARNING"])
    assert args.log_level == "WARNING"
    assert isinstance(logger, logging.Logger)


def test_container_factories(tmp_path: Path):
    log = logging.getLogger("t.container")
    c = Container(tmp_path, "sess", log)
    assert c.config_repo.path == tmp_path / "config.json"
    assert isinstance(c.camera_service(), object)
    assert isinstance(c.download_raws_use_case(), object)
    assert isinstance(c.startup_service(), StartupService)
    assert isinstance(c.shutdown_service(), ShutdownService)
    assert isinstance(c.retry_camera_use_case(), RetryCameraUseCase)
    assert isinstance(c.exit_app_use_case(), ExitAppUseCase)
    assert isinstance(c.start_digitization_use_case(), StartDigitizationUseCase)
    assert isinstance(c.pause_digitization_use_case(), PauseDigitizationUseCase)
    assert isinstance(c.resume_digitization_use_case(), ResumeDigitizationUseCase)
    assert isinstance(c.stop_digitization_use_case(), StopDigitizationUseCase)
    assert isinstance(c.capture_service(), CaptureService)
    assert not c.app_state.digitalizing
    assert c.camera_service() is c.camera_service()
    assert c.printer_service() is c.printer_service()


def test_container_with_project_tmp_fixture(project_tmp: Path, test_logger: logging.Logger):
    c = Container(project_tmp, "lab", test_logger)
    assert c.raw_pending_repo._utils_dir == project_tmp / "Utils"
    assert c.raw_pending_repo.file_path.parent == project_tmp / "Utils" / "Pending_raws"
    assert c.session_label == "lab"


def test_default_container_uses_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.app.container.project_root_from_here",
        lambda p: tmp_path,
    )
    log = logging.getLogger("t.def")
    c = default_container(log, "x")
    assert c.project_root == tmp_path
    assert c.session_label == "x"
