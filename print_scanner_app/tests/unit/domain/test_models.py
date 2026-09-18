import dataclasses

import pytest

from print_scanner_app.domain.models.app_state import AppState
from print_scanner_app.domain.models.camera_state import CameraState
from print_scanner_app.domain.models.printer_state import PrinterState
from print_scanner_app.domain.models.raw_batch import RawBatchInfo
from print_scanner_app.domain.models.raw_item import RawItem


def test_raw_item_as_pair():
    r = RawItem("IMG.CR3", "dest-0001.cr3")
    assert r.as_pair() == ["IMG.CR3", "dest-0001.cr3"]


def test_app_state_roundtrip_dict():
    s = AppState(frame_count=5)
    d = s.to_serializable_dict()
    s2 = AppState.from_dict(d)
    assert s2.frame_count == 5


def test_camera_state_defaults():
    c = CameraState()
    assert c.selected_serial == ""
    assert not c.initialized
    assert c.last_error is None


def test_camera_state_fixture(sample_camera_state: CameraState):
    assert sample_camera_state.initialized and sample_camera_state.usb_address.startswith("usb:")


def test_printer_state_fixture(sample_printer_state: PrinterState):
    assert sample_printer_state.connected and "/lp" in sample_printer_state.device_path


def test_raw_batch_info_fixture(sample_batch_info: RawBatchInfo):
    assert sample_batch_info.subfolder == "00001-00100"
    assert sample_batch_info.min_frame == 1 and sample_batch_info.max_frame == 100


def test_raw_batch_info_frozen():
    info = RawBatchInfo(subfolder="a", min_frame=None, max_frame=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.subfolder = "b"  # type: ignore[misc]


def test_sample_raw_items_fixture(sample_raw_items: list[RawItem]):
    assert len(sample_raw_items) == 2
    assert all(isinstance(x, RawItem) for x in sample_raw_items)


def test_sample_app_state_has_pending(sample_app_state: AppState):
    assert sample_app_state.frame_count == 3
    assert sample_app_state.raw_download.pending
