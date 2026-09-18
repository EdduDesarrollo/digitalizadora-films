"""
Smoke de cableado (sin hardware): Container + repos + config.

Marcado `integration` para distinguirlo de unit puro; no requiere cámara ni impresora.
"""

import json
import logging
from pathlib import Path

import pytest

from print_scanner_app.app.container import Container

pytestmark = pytest.mark.integration


def test_container_config_and_raw_pending(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"CAMARA": "TEST-SN", "DIRECTORIO": str(tmp_path)}), encoding="utf-8")
    log = logging.getLogger("smoke.integration")
    c = Container(tmp_path, "session_smoke", log)

    loaded = c.config_repo.load()
    assert loaded["CAMARA"] == "TEST-SN"

    c.raw_pending_repo.append("A.CR3", "dest-00001.cr3")
    pairs = c.raw_pending_repo.load_all()
    assert len(pairs) == 1 and pairs[0][0] == "A.CR3"

    uc = c.download_raws_use_case()
    assert uc is not None

    assert not c.app_state.digitalizing
    assert c.start_digitization_use_case().execute().ok
    assert c.app_state.digitalizing


def test_services_construct_without_side_effects(tmp_path: Path):
    log = logging.getLogger("smoke2")
    c = Container(tmp_path, "s", log)
    assert c.camera_service() is not None
    assert c.printer_service() is not None
    assert c.capture_service() is not None
