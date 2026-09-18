"""Tests de resolución locale gphoto2 (sin hardware)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from print_scanner_app.infrastructure.camera.camera_config import WARNING_CONFIG_MANUAL
from print_scanner_app.infrastructure.camera.camera_config_locale import (
    CAPTURETARGET_PATH,
    camera_models_match,
    choice_for_semantic,
    choice_index_for_capturetarget_memory_card,
    ensure_capture_target_memory_card,
    get_widget_choices,
    is_internal_ram_choice,
    is_memory_card_choice,
    normalize_model_name,
    read_camera_model_from_device,
    resolve_choice_value,
)


class _GP:
    GP_OK = 0

    class GPhoto2Error(Exception):
        pass


def _radio_widget(choices: list[str], *, current: str | None = None):
    w = MagicMock()
    state = {"current": current if current is not None else (choices[0] if choices else "")}

    def count(_widget):
        return len(choices)

    def get_choice(_widget, i):
        return _GP.GP_OK, choices[i]

    def get_value(_widget):
        return _GP.GP_OK, state["current"]

    def set_value(_widget, v):
        state["current"] = v

    gp = _GP()
    gp.gp_widget_count_choices = count
    gp.gp_widget_get_choice = get_choice
    gp.gp_widget_get_value = get_value
    gp.gp_widget_set_value = set_value
    gp.gp_widget_get_readonly = lambda _w: (_GP.GP_OK, 0)
    return w, gp, state


def test_normalize_model_name():
    assert normalize_model_name("  Canon   EOS M6 Mark II  ") == "canon eos m6 mark ii"


def test_camera_models_match_empty_expected():
    assert camera_models_match(None, "Canon EOS M6 Mark II")
    assert camera_models_match("", "x")


def test_camera_models_match_case_insensitive():
    assert camera_models_match("Canon EOS M6 Mark II", "canon eos m6 mark ii")


def test_is_memory_card_and_ram():
    assert is_memory_card_choice("Memory card")
    assert is_memory_card_choice("Tarjeta de memoria")
    assert is_internal_ram_choice("RAM Interna")
    assert is_internal_ram_choice("Internal RAM")
    assert not is_memory_card_choice("RAM Interna")


def test_get_widget_choices():
    w, gp, _ = _radio_widget(["Memory card", "Internal RAM"])
    assert get_widget_choices(w, gp) == ["Memory card", "Internal RAM"]


def test_resolve_choice_en_desired_en():
    w, gp, _ = _radio_widget(["Memory card", "Internal RAM"])
    assert (
        resolve_choice_value(w, "Memory card", CAPTURETARGET_PATH, gp) == "Memory card"
    )


def test_resolve_choice_en_desired_es_on_en_widget():
    w, gp, _ = _radio_widget(["Memory card", "Internal RAM"])
    assert (
        resolve_choice_value(w, "Tarjeta de memoria", CAPTURETARGET_PATH, gp)
        == "Memory card"
    )


def test_resolve_choice_es_widget():
    w, gp, _ = _radio_widget(["Tarjeta de memoria", "RAM Interna"])
    assert (
        resolve_choice_value(w, "Memory card", CAPTURETARGET_PATH, gp)
        == "Tarjeta de memoria"
    )


def test_resolve_imageformat_craw():
    w, gp, _ = _radio_widget(
        ["Large RAW", "cRAW + S2", "cRAW + Smaller JPEG"],
    )
    assert (
        resolve_choice_value(w, "cRAW + S2", "main/imgsettings/imageformat", gp)
        == "cRAW + S2"
    )


def test_choice_for_semantic_ram_only_returns_none():
    w, gp, _ = _radio_widget(["RAM Interna", "Internal RAM"])
    assert choice_for_semantic(w, "memory_card", gp) is None


def test_choice_index_m6_only():
    w, gp, _ = _radio_widget(["RAM Interna", "Tarjeta de memoria"])
    assert (
        choice_index_for_capturetarget_memory_card(
            gp, w, detected_model="Canon EOS M6 Mark II"
        )
        == 1
    )
    assert (
        choice_index_for_capturetarget_memory_card(gp, w, detected_model="Other") is None
    )


def test_read_camera_model_from_device(monkeypatch: pytest.MonkeyPatch):
    model_w = MagicMock()
    gp = _GP()

    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.get_config_widget",
        lambda _cam, _gp, path: model_w if path.endswith("cameramodel") else None,
    )
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.read_widget_value",
        lambda _w, _gp: "Canon EOS M6 Mark II",
    )
    assert read_camera_model_from_device(MagicMock(), gp) == "Canon EOS M6 Mark II"


def test_ensure_capture_target_memory_card_en(monkeypatch: pytest.MonkeyPatch):
    w, gp, state = _radio_widget(
        ["Memory card", "Internal RAM"],
        current="Internal RAM",
    )

    class Cam:
        def get_config(self):
            return object()

        def set_config(self, _c):
            pass

    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.get_config_widget",
        lambda _c, _g, path: w if path == CAPTURETARGET_PATH else None,
    )
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.read_widget_value",
        lambda _w, _g: state["current"],
    )

    ok = ensure_capture_target_memory_card(
        Cam(),
        gp,
        logger=logging.getLogger("test"),
        detected_model="Canon EOS M6 Mark II",
    )
    assert ok
    assert state["current"] == "Memory card"


def test_ensure_capture_target_fails_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    w, gp, state = _radio_widget(["RAM Interna"], current="RAM Interna")
    caplog.set_level(logging.WARNING)

    class Cam:
        def get_config(self):
            return object()

        def set_config(self, _c):
            pass

    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.get_config_widget",
        lambda _c, _g, path: w if path == CAPTURETARGET_PATH else None,
    )
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.camera_config_locale.read_widget_value",
        lambda _w, _g: state["current"],
    )
    log = logging.getLogger("test.ensure.fail")
    ok = ensure_capture_target_memory_card(
        Cam(), gp, logger=log, detected_model="Other"
    )
    assert not ok
    assert WARNING_CONFIG_MANUAL in caplog.text
