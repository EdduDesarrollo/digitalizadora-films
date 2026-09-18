import json

from print_scanner_app.infrastructure.storage.config_repository import (
    ConfigRepository,
    DEFAULT_CONFIG,
    load_config,
    output_directory_configured,
    parse_numero_frame_value,
    resolve_output_directory,
)


def test_default_prefijo_empty():
    assert DEFAULT_CONFIG["PREFIJO_ARCHIVO"] == ""


def test_load_merge_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"CAMARA": "ABC"}), encoding="utf-8")
    d = load_config(p)
    assert d["CAMARA"] == "ABC"
    assert d["PREFIJO_ARCHIVO"] == ""
    assert d.get("NUMERO_FRAME") == 0


def test_resolve_output_directory(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    cfg = {"DIRECTORIO": str(out)}
    assert resolve_output_directory(cfg) == str(out.resolve())
    assert resolve_output_directory({"DIRECTORIO": ""}) == ""
    assert not output_directory_configured({"DIRECTORIO": ""})
    assert output_directory_configured(cfg)


def test_save_roundtrip(tmp_path):
    p = tmp_path / "c.json"
    r = ConfigRepository(p)
    r.save({"DIRECTORIO": "/tmp/x", "CAMARA": ""})
    d = r.load()
    assert d["DIRECTORIO"] == "/tmp/x"


def test_parse_numero_frame_value_valid():
    assert parse_numero_frame_value(42) == (42, False)
    assert parse_numero_frame_value("17") == (17, False)
    assert parse_numero_frame_value(3.0) == (3, False)


def test_parse_numero_frame_value_invalid_rewrites():
    assert parse_numero_frame_value(-1) == (0, True)
    assert parse_numero_frame_value("x") == (0, True)
    assert parse_numero_frame_value("") == (0, True)
    assert parse_numero_frame_value(None) == (0, True)
    assert parse_numero_frame_value(True) == (0, True)
    assert parse_numero_frame_value(3.7) == (0, True)
