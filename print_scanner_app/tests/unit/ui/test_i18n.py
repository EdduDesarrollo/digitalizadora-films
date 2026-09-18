"""Tests del loader i18n (JSON + fallback)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from print_scanner_app.ui import i18n


@pytest.fixture(autouse=True)
def _reset_i18n():
    i18n.reload_catalogs()
    i18n.set_language("es")
    i18n.reset_popup_count()
    yield
    i18n.set_language("es")
    i18n.reset_popup_count()


def test_es_and_en_have_same_keys():
    base = Path(i18n.translations_dir())
    es = json.loads((base / "es.json").read_text(encoding="utf-8"))
    en = json.loads((base / "en.json").read_text(encoding="utf-8"))
    assert set(es) == set(en)
    assert es
    assert en


def test_normalize_invalid_falls_back_to_es():
    assert i18n.normalize_language("fr") == "es"
    assert i18n.normalize_language("") == "es"
    assert i18n.normalize_language(None) == "es"
    assert i18n.set_language("nope") == "es"


def test_t_switches_language():
    i18n.set_language("es")
    assert i18n.t("btn.digitize") == "Digitalizar"
    i18n.set_language("en")
    assert i18n.t("btn.digitize") == "Digitize"


def test_target_language_label():
    i18n.set_language("es")
    assert i18n.target_language_label() == "EN"
    i18n.set_language("en")
    assert i18n.target_language_label() == "ES"


def test_status_uses_digitalizacion_not_digitacion():
    from print_scanner_app.ui.presenters.app_presenter import AppPresenter

    i18n.set_language("es")
    hint = AppPresenter().status_hint()
    assert "Digitalización:" in hint
    assert "Digitación:" not in hint


def test_popup_counter():
    assert not i18n.has_open_popup()
    i18n.begin_popup()
    assert i18n.has_open_popup()
    i18n.end_popup()
    assert not i18n.has_open_popup()
    i18n.end_popup()
    assert not i18n.has_open_popup()
