import errno

import pytest

pytestmark = pytest.mark.critical

from print_scanner_app.domain.exceptions.domain_errors import (
    DiskFullError,
    DomainError,
    PermissionDeniedError,
    ReadOnlyFilesystemError,
)
from print_scanner_app.domain.policies.error_policy import classify_exception, format_rofs, raise_classified


def test_erofs_with_filename():
    e = OSError(errno.EROFS, "ro", "/mnt/x")
    c = classify_exception(e)
    assert isinstance(c, ReadOnlyFilesystemError)


def test_domain_error_passthrough():
    inner = DiskFullError("x")
    assert classify_exception(inner) is inner


def test_unknown_maps_to_domain_error():
    c = classify_exception(ValueError("oops"))
    assert isinstance(c, DomainError) and "oops" in str(c)


def test_format_rofs_plain():
    assert format_rofs("msg", None) == "msg"


def test_raise_classified():
    with pytest.raises(DiskFullError):
        raise_classified(OSError(errno.ENOSPC, "full"))
