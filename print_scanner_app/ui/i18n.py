"""Carga de traducciones UI desde ``translations/{lang}.json``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

UI_LANGUAGE_KEY = "UI_LANGUAGE"
DEFAULT_LANGUAGE = "es"
SUPPORTED_LANGUAGES = frozenset({"es", "en"})

_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
_log = logging.getLogger(__name__)

_language: str = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}
_catalog_cache: dict[str, dict[str, str]] = {}
_open_popup_count: int = 0


def translations_dir() -> Path:
    return _TRANSLATIONS_DIR


def normalize_language(raw: Any) -> str:
    lang = str(raw or "").strip().lower()
    if lang in SUPPORTED_LANGUAGES:
        return lang
    return DEFAULT_LANGUAGE


def available_languages() -> list[str]:
    found: list[str] = []
    if not _TRANSLATIONS_DIR.is_dir():
        return list(SUPPORTED_LANGUAGES)
    for path in sorted(_TRANSLATIONS_DIR.glob("*.json")):
        code = path.stem.strip().lower()
        if code:
            found.append(code)
    return found or list(SUPPORTED_LANGUAGES)


def _load_catalog(lang: str) -> dict[str, str]:
    if lang in _catalog_cache:
        return _catalog_cache[lang]
    path = _TRANSLATIONS_DIR / f"{lang}.json"
    data: dict[str, str] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {str(k): str(v) for k, v in raw.items()}
        except Exception as e:  # noqa: BLE001
            _log.warning("No se pudo cargar traducciones %s: %s", path, e)
    _catalog_cache[lang] = data
    return data


def reload_catalogs() -> None:
    """Invalida cache (útil en tests)."""
    global _catalog
    _catalog_cache.clear()
    _catalog = _load_catalog(_language)


def get_language() -> str:
    return _language


def set_language(raw: Any) -> str:
    """Fija idioma (inválido → es) y recarga catálogo. Retorna idioma efectivo."""
    global _language, _catalog
    _language = normalize_language(raw)
    _catalog = _load_catalog(_language)
    if not _catalog and _language != DEFAULT_LANGUAGE:
        _catalog = _load_catalog(DEFAULT_LANGUAGE)
    return _language


def t(key: str, **kwargs: Any) -> str:
    """
    Resuelve ``key`` en el idioma actual.
    Fallback: ES → la propia key.
    """
    text = _catalog.get(key)
    if text is None and _language != DEFAULT_LANGUAGE:
        text = _load_catalog(DEFAULT_LANGUAGE).get(key)
    if text is None:
        _log.debug("i18n key faltante: %s", key)
        text = key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception as e:  # noqa: BLE001
            _log.warning("i18n format falló key=%s: %s", key, e)
            return text
    return text


def target_language_label() -> str:
    """Texto del botón: idioma destino (EN si estamos en es, ES si en en)."""
    return "EN" if _language == "es" else "ES"


def begin_popup() -> None:
    global _open_popup_count
    _open_popup_count += 1


def end_popup() -> None:
    global _open_popup_count
    _open_popup_count = max(0, _open_popup_count - 1)


def has_open_popup() -> bool:
    return _open_popup_count > 0


def reset_popup_count() -> None:
    """Solo tests."""
    global _open_popup_count
    _open_popup_count = 0


def bind_popup_tracking(popup: Any) -> None:
    """Incrementa contador al abrir vía ``open()`` wrap; decrementa en dismiss."""
    if getattr(popup, "_i18n_tracked", False):
        return
    popup._i18n_tracked = True
    original_open = popup.open

    def tracked_open(*args, **kwargs):
        begin_popup()

        def _on_dismiss(*_a):
            end_popup()
            try:
                popup.unbind(on_dismiss=_on_dismiss)
            except Exception:  # noqa: BLE001
                pass

        try:
            popup.bind(on_dismiss=_on_dismiss)
        except Exception:  # noqa: BLE001
            end_popup()
            raise
        return original_open(*args, **kwargs)

    popup.open = tracked_open


# Carga inicial
set_language(DEFAULT_LANGUAGE)
