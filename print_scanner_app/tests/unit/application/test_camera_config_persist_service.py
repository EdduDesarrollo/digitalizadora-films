from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from print_scanner_app.application.services.camera_config_persist_service import CameraConfigPersistService
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository


def test_persist_success_merges_and_saves(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "CONFIG_CAMARA": {
                    "main/imgsettings/iso": "200",
                    "main/actions/old": 1,
                },
                "NUMERO_FRAME": 5,
            }
        ),
        encoding="utf-8",
    )
    repo = ConfigRepository(cfg_path)

    svc = CameraConfigPersistService()
    cam = MagicMock()
    gp = MagicMock()

    before = {"main/imgsettings/iso": "200"}
    after_export = {
        "main/imgsettings/iso": "250",
        "main/imgsettings/whitebalance": "Manual",
        "main/actions/ignored": 9,
    }

    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        "print_scanner_app.application.services.camera_config_persist_service.export_camera_config_tree",
        lambda _c, _g: after_export,
    )
    monkey.setattr(
        "print_scanner_app.application.services.camera_config_persist_service.time.sleep",
        lambda _s: None,
    )
    try:
        r = svc.persist_camera_config_after_entangle(
            cam,
            gp,
            repo,
            before_snapshot=before,
            max_attempts=2,
        )
    finally:
        monkey.undo()

    assert r.ok
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert saved["CONFIG_CAMARA"] == {
        "main/imgsettings/iso": "250",
        "main/imgsettings/whitebalance": "Manual",
    }
    assert saved["NUMERO_FRAME"] == 5


def test_persist_fails_after_two_attempts(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"CONFIG_CAMARA": {}}), encoding="utf-8")
    repo = ConfigRepository(cfg_path)
    svc = CameraConfigPersistService()

    class _GpErr(Exception):
        code = -110

        def __str__(self):
            return "I/O in progress"

    def boom(_c, _g):
        raise _GpErr()

    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        "print_scanner_app.application.services.camera_config_persist_service.export_camera_config_tree",
        boom,
    )
    monkey.setattr(
        "print_scanner_app.application.services.camera_config_persist_service.time.sleep",
        lambda _s: None,
    )
    try:
        r = svc.persist_camera_config_after_entangle(MagicMock(), MagicMock(), repo, max_attempts=2)
    finally:
        monkey.undo()

    assert not r.ok
