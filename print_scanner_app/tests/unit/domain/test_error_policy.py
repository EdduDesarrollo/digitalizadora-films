import errno

import pytest

from print_scanner_app.domain.exceptions.domain_errors import DiskFullError, PermissionDeniedError

pytestmark = pytest.mark.critical
from print_scanner_app.domain.policies.error_policy import classify_exception


def test_enospc():
    e = OSError(errno.ENOSPC, "lleno")
    c = classify_exception(e)
    assert isinstance(c, DiskFullError)


def test_eacces():
    e = OSError(errno.EACCES, "denied")
    assert isinstance(classify_exception(e), PermissionDeniedError)
