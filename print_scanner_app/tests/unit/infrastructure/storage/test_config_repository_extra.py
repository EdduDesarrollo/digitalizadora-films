import json

import pytest

from print_scanner_app.infrastructure.storage.config_repository import (
    ConfigRepository,
    default_config_merged,
    load_config,
    validate_expected_keys,
)


def test_validate_expected_keys_reports_missing():
    miss = validate_expected_keys({"CAMARA": "x"})
    assert miss


def test_load_invalid_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    r = ConfigRepository(p)
    with pytest.raises(json.JSONDecodeError):
        r.load()


def test_update_key_roundtrip(tmp_path):
    p = tmp_path / "c.json"
    r = ConfigRepository(p)
    r.update_key("DIRECTORIO", "/data")
    assert r.load()["DIRECTORIO"] == "/data"


def test_default_config_merged_loads_file(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"CAMARA": "XYZ"}), encoding="utf-8")
    d = default_config_merged(p)
    assert d["CAMARA"] == "XYZ"
    assert "PREFIJO_ARCHIVO" in d


def test_default_config_merged_no_path_returns_defaults():
    d = default_config_merged(None)
    assert d["CAMARA"] == ""
    assert d["UMBRAL_PX_BLANCOS"] == 2000


def test_load_config_rejects_non_object(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="objeto JSON"):
        load_config(p)
