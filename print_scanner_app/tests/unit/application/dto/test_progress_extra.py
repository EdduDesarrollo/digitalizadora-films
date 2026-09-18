from print_scanner_app.application.dto.progress import Progress


def test_progress_zero_total():
    p = Progress(0, 0, "x")
    assert p.fraction == 0.0
