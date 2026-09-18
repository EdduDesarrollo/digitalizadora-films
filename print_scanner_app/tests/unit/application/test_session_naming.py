import pytest

from print_scanner_app.application.session_naming import normalized_codigo_referencia, raw_pending_file_key_from_config


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  abc  ", "ABC"),
        ("", ""),
        ("x", "X"),
    ],
)
def test_normalized_codigo_referencia(raw, expected):
    assert normalized_codigo_referencia(raw) == expected


def test_raw_pending_file_key_with_codigo():
    cfg = {"PREFIJO_ARCHIVO": "PREF", "CODIGO_REFERENCIA": "  hola  "}
    assert raw_pending_file_key_from_config(cfg) == "PREF-HOLA"


def test_raw_pending_file_key_empty_codigo_uses_placeholder():
    cfg = {"PREFIJO_ARCHIVO": "X", "CODIGO_REFERENCIA": ""}
    assert raw_pending_file_key_from_config(cfg) == "_sin_codigo_"


def test_raw_pending_file_key_empty_prefijo_returns_codigo_only():
    cfg = {"PREFIJO_ARCHIVO": "", "CODIGO_REFERENCIA": "abc"}
    assert raw_pending_file_key_from_config(cfg) == "ABC"
