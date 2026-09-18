from __future__ import annotations

import logging
from pathlib import Path

import pytest

from print_scanner_app.domain.models.app_state import AppState, RawDownloadState
from print_scanner_app.domain.models.camera_state import CameraState
from print_scanner_app.domain.models.printer_state import PrinterState
from print_scanner_app.domain.models.raw_batch import RawBatchInfo
from print_scanner_app.domain.models.raw_item import RawItem


@pytest.fixture
def sample_app_state() -> AppState:
    return AppState(
        frame_count=3,
        raw_download=RawDownloadState(pending=[["A.CR3", "pref-00003.cr3"]]),
    )


@pytest.fixture
def sample_raw_items() -> list[RawItem]:
    return [
        RawItem("X.CR3", "p-00001.cr3"),
        RawItem("Y.CR3", "p-00100.cr3"),
    ]


@pytest.fixture
def sample_camera_state() -> CameraState:
    return CameraState(
        selected_serial="SN-001",
        usb_address="usb:1,2",
        initialized=True,
        last_error=None,
    )


@pytest.fixture
def sample_printer_state() -> PrinterState:
    return PrinterState(device_path="/dev/usb/lp1", connected=True, last_error=None)


@pytest.fixture
def sample_batch_info() -> RawBatchInfo:
    return RawBatchInfo(subfolder="00001-00100", min_frame=1, max_frame=100)


@pytest.fixture
def test_logger() -> logging.Logger:
    return logging.getLogger("print_scanner_app.tests")


@pytest.fixture
def project_tmp(tmp_path: Path) -> Path:
    """Raíz de proyecto simulado (config.json + Utils) para smoke/unit locales."""
    (tmp_path / "Utils").mkdir(parents=True)
    return tmp_path
