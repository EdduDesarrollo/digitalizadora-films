"""
E2E con hardware: mueve el film 1 px hasta detectar sprocket (sin disparar RAW).

    DIGITALIZADORA_HARDWARE_TEST=1 pytest print_scanner_app/tests/integration/test_hardware_alignment.py -m hardware --no-cov -s
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from print_scanner_app.tests.integration.hardware_alignment import (
    _repo_root_from_here,
    run_hardware_alignment,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.hardware,
]

_SKIP_REASON = (
    "Test de hardware desactivado. "
    "Exportá DIGITALIZADORA_HARDWARE_TEST=1 con cámara, impresora y film cargado."
)


def _gphoto2_available() -> bool:
    try:
        import gphoto2  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def project_root() -> Path:
    return _repo_root_from_here()


@pytest.mark.skipif(os.environ.get("DIGITALIZADORA_HARDWARE_TEST") != "1", reason=_SKIP_REASON)
@pytest.mark.skipif(not _gphoto2_available(), reason="Módulo gphoto2 no instalado")
def test_hardware_moves_film_until_sprocket_aligned(project_root: Path):
    from print_scanner_app.infrastructure.printer.printer_device import first_lp_device

    if first_lp_device() is None:
        pytest.fail("No hay impresora /dev/usb/lp*")

    outcome = run_hardware_alignment(project_root)
    assert outcome.aligned, (
        f"{outcome.error} blob_area={outcome.white_pixel_count} "
        f"umbral={outcome.umbral} jpeg={outcome.last_jpeg_path}"
    )
    assert outcome.white_pixel_count > outcome.umbral


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:], "-m", "hardware", "--no-cov", "-s"]))
