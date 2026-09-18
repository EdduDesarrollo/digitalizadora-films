import pytest

from print_scanner_app.domain.models.raw_batch import RawBatchInfo
from print_scanner_app.domain.policies.raw_batch_policy import (
    batch_subfolder_for_download,
    extract_frame_from_basename,
    format_batch_dir_name,
)

pytestmark = pytest.mark.critical


def test_extract_empty_string():
    assert extract_frame_from_basename("") is None


def test_format_batch_dir_name():
    info = RawBatchInfo(subfolder="00001-00002", min_frame=1, max_frame=2)
    assert format_batch_dir_name(info) == "00001-00002"


def test_mixed_parseable_batch():
    info = batch_subfolder_for_download(["a-00010.cr3", "bad.cr3", "a-00005.cr3"])
    assert info.subfolder == "00005-00010"
