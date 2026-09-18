"""
E2E con cámara real: descarga RAW pendientes y borrado de JPG (fase A + B).

No se ejecuta en CI por defecto. Activar con:

    DIGITALIZADORA_HARDWARE_TEST=1 pytest print_scanner_app/tests/integration/test_hardware_download_raws.py -m hardware --no-cov -s

Antes de correr: dejar bloques en ``Utils/Pending_raws/raw_pendientes_*.txt`` y los archivos en la tarjeta.
Tras un éxito el archivo de pendientes queda vacío; hay que capturar de nuevo para repetir.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from print_scanner_app.tests.integration.hardware_download import (
    _repo_root_from_here,
    run_hardware_download,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.hardware,
]

_SKIP_REASON = (
    "Test de hardware desactivado. "
    "Exportá DIGITALIZADORA_HARDWARE_TEST=1 y conectá la cámara con pendientes en Utils/."
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
def test_hardware_download_pending_raws_and_delete_jpegs(project_root: Path):
    from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
    from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository

    repo = RawPendingRepository(project_root / "Utils", ConfigRepository(project_root / "config.json"))
    pending_before = repo.load_blocks()
    if not pending_before:
        pytest.skip("Sin pendientes en Utils/Pending_raws/raw_pendientes_*.txt")

    expected_raws = [b.raw_name for b in pending_before]
    expected_dests = {b.dest_basename for b in pending_before}
    jpg_names = [b.jpg_name for b in pending_before if b.has_jpg and b.jpg_name]

    outcome = run_hardware_download(project_root)
    res = outcome.result

    assert not res.error, res.error
    assert res.not_found == []
    assert res.missing_local_copy_ids == []
    assert set(res.downloaded) == set(expected_raws)
    assert repo.load_blocks() == []

    assert outcome.batch_dir is not None
    on_disk = {p.name for p in outcome.batch_dir.glob("*.cr3")}
    assert expected_dests <= on_disk

    if jpg_names:
        assert outcome.jpg_absent_on_card
        still_on_card = [n for n, ok in outcome.jpg_absent_on_card.items() if not ok]
        assert not still_on_card, f"JPG aún en cámara: {still_on_card}"


if __name__ == "__main__":
    os.environ.setdefault("DIGITALIZADORA_HARDWARE_TEST", "1")
    raise SystemExit(pytest.main([__file__, *sys.argv[1:], "-m", "hardware", "--no-cov", "-s"]))
