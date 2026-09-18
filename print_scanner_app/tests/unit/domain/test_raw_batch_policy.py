import pytest

from print_scanner_app.domain.policies.raw_batch_policy import batch_subfolder_for_download, extract_frame_from_basename

pytestmark = pytest.mark.critical


def test_extract_frame():
    assert extract_frame_from_basename("UY-X-00042.cr3") == 42
    assert extract_frame_from_basename("00499.jpg") == 499
    assert extract_frame_from_basename("p-00100.CR2") == 100


def test_batch_folder():
    info = batch_subfolder_for_download(["a-00000.cr3", "a-00499.cr3"])
    assert info.subfolder == "00000-00499"
    assert info.min_frame == 0
    assert info.max_frame == 499


def test_batch_small_range():
    info = batch_subfolder_for_download(["p-00500.cr3", "p-00505.cr3"])
    assert info.subfolder == "00500-00505"


def test_sin_rango():
    info = batch_subfolder_for_download(["nohaynumero.cr3"])
    assert info.subfolder == "sin_rango_descarga"


def test_batch_single_frame_cr2():
    info = batch_subfolder_for_download(["pref-00100.CR2"])
    assert info.subfolder == "00100-00100"
    assert info.min_frame == info.max_frame == 100
