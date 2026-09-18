from print_scanner_app.application.dto.errors import ErrorCode, ErrorEnvelope
from print_scanner_app.application.dto.progress import Progress


def test_progress_fraction():
    p = Progress(1, 4, "x")
    assert abs(p.fraction - 0.25) < 1e-6


def test_error_envelope():
    e = ErrorEnvelope(ErrorCode.DISK_FULL, "sin espacio")
    assert e.code == ErrorCode.DISK_FULL
