"""Resolución de choices gphoto2 según locale (libgphoto2-l10n)."""

from __future__ import annotations

import logging
import re
from typing import Any

# Canon EOS M6 Mark II — índice 1 = tarjeta, 0 = RAM (D2)
_CAPTURETARGET_MEMORY_CARD_INDEX = 1
_CANON_M6_II_NORMALIZED = "canon eos m6 mark ii"

CAPTURETARGET_PATH = "main/settings/capturetarget"
CAMERAMODEL_PATH = "main/status/cameramodel"

CHOICE_ALIASES: dict[str, list[str]] = {
    "memory_card": [
        "Memory card",
        "Tarjeta de memoria",
        "Tarjeta",
    ],
    "internal_ram": [
        "Internal RAM",
        "RAM Interna",
        "Interna",
    ],
    "imageformat_craw_small": [
        "cRAW + S2",
        "cRAW + Smaller JPEG",
        "Crudo + JPEG pequeño",
    ],
    "drive_single": ["Single", "Individual", "Uno", "Única"],
    "focus_manual": ["Manual"],
    "af_live": ["Live", "En vivo", "LiveZone"],
    "wb_color_temp": [
        "Color Temperature",
        "Temperatura de color",
        "Color Temperatura",
    ],
    "picture_neutral": ["Neutral", "Neutro"],
    "metering_evaluative": ["Evaluative", "Evaluativa", "Evaluado"],
    "none_choice": ["None", "Ninguno"],
    "off_choice": ["Off", "Desactivar", "inactiva", "off"],
    "on_choice": ["On", "Activar"],
    "high_iso_nr": ["High", "Alta"],
}

PATH_TO_SEMANTIC: dict[str, str] = {
    "capturetarget": "memory_card",
    "imageformat": "imageformat_craw_small",
    "imageformatsd": "imageformat_craw_small",
    "imageformatcf": "imageformat_craw_small",
    "drivemode": "drive_single",
    "focusmode": "focus_manual",
    "afmethod": "af_live",
    "whitebalance": "wb_color_temp",
    "picturestyle": "picture_neutral",
    "meteringmode": "metering_evaluative",
    "manualfocusdrive": "none_choice",
    "eosremoterelease": "none_choice",
    "continuousaf": "off_choice",
    "highisonr": "high_iso_nr",
    "aeb": "off_choice",
    "movieservoaf": "on_choice",
}

_SKIP_PATH_PREFIXES = ("main/status/", "main/actions/")
_SKIP_PATHS_EXACT = frozenset(
    {
        "main/settings/movierecordtarget",  # video fuera de alcance (diseño)
    }
)

_RAM_PATTERNS = re.compile(
    r"ram|interna|internal|sdram",
    re.IGNORECASE,
)
_CARD_PATTERNS = re.compile(
    r"memory\s*card|tarjeta|card|memoria",
    re.IGNORECASE,
)


def normalize_model_name(s: str | None) -> str:
    if not s:
        return ""
    t = str(s).strip()
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def camera_models_match(expected: str | None, detected: str | None) -> bool:
    exp = normalize_model_name(expected)
    if not exp:
        return True
    det = normalize_model_name(detected)
    return exp == det


def is_widget_readonly(widget: Any, gp: Any) -> bool:
    try:
        ret, ro = gp.gp_widget_get_readonly(widget)
        if ret < gp.GP_OK:
            return False
        return bool(ro)
    except Exception:
        return False


def should_skip_config_path(
    path: str,
    widget: Any | None = None,
    gp: Any | None = None,
) -> bool:
    p = str(path).strip()
    if p in _SKIP_PATHS_EXACT:
        return True
    if any(p.startswith(prefix) for prefix in _SKIP_PATH_PREFIXES):
        return True
    if widget is not None and gp is not None and is_widget_readonly(widget, gp):
        return True
    return False


def should_skip_config_value(
    path: str,
    valor: Any,
    widget: Any | None,
    gp: Any | None,
) -> bool:
    """Valores no aplicables (índices internos, auto implícito, etc.)."""
    seg = _path_last_segment(path)
    sval = str(valor).strip()
    if seg == "liveviewsize" and (
        sval.lower().startswith("val ")
        or sval.lower().startswith("valor ")
        or "desconocido" in sval.lower()
    ):
        return True
    if seg == "aperture" and widget is not None and gp is not None:
        choices = get_widget_choices(widget, gp)
        if choices == ["implicit auto"] or choices == ["auto"]:
            return True
    if seg == "bracketmode" and "desconocido" in sval.lower():
        return True
    return False


def get_widget_choices(widget: Any, gp: Any) -> list[str]:
    try:
        count = gp.gp_widget_count_choices(widget)
        if count <= 0:
            return []
        out: list[str] = []
        for i in range(count):
            ret, choice = gp.gp_widget_get_choice(widget, i)
            if ret >= gp.GP_OK and choice is not None:
                out.append(str(choice))
        return out
    except Exception:
        return []


def widget_has_choices(widget: Any, gp: Any) -> bool:
    return len(get_widget_choices(widget, gp)) > 0


def _normalize_choice_label(label: str) -> str:
    t = str(label).strip()
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def is_memory_card_choice(label: str) -> bool:
    if not label:
        return False
    if _RAM_PATTERNS.search(label) and not _CARD_PATTERNS.search(label):
        return False
    return bool(_CARD_PATTERNS.search(label))


def is_internal_ram_choice(label: str) -> bool:
    if not label:
        return False
    return bool(_RAM_PATTERNS.search(label))


def _path_last_segment(path: str) -> str:
    parts = [p for p in str(path).split("/") if p]
    return parts[-1] if parts else ""


def _semantic_for_path(path: str) -> str | None:
    return PATH_TO_SEMANTIC.get(_path_last_segment(path))


def _exact_choice_match(desired: str, choices: list[str]) -> str | None:
    if desired in choices:
        return desired
    d = _normalize_choice_label(desired)
    matches = [c for c in choices if _normalize_choice_label(c) == d]
    if len(matches) == 1:
        return matches[0]
    return None


def _single_normalized_match(desired: str, choices: list[str]) -> str | None:
    d = _normalize_choice_label(desired)
    matches = [c for c in choices if _normalize_choice_label(c) == d]
    if len(matches) == 1:
        return matches[0]
    return None


def _choice_matching_aliases(semantic: str, choices: list[str]) -> str | None:
    aliases = CHOICE_ALIASES.get(semantic, [])
    normalized_aliases = {_normalize_choice_label(a) for a in aliases}
    matches: list[str] = []
    for c in choices:
        nc = _normalize_choice_label(c)
        if nc in normalized_aliases:
            matches.append(c)
            continue
        for a in aliases:
            if _normalize_choice_label(a) == nc:
                matches.append(c)
                break
    if len(matches) == 1:
        return matches[0]
    return None


def _choice_craw_prefix(choices: list[str]) -> str | None:
    matches = [c for c in choices if str(c).upper().startswith("CRAW")]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        for c in matches:
            if "S2" in c or "Smaller" in c or "pequeño" in c.lower():
                return c
        return matches[0]
    return None


def choice_for_semantic(widget: Any, semantic: str, gp: Any) -> str | None:
    choices = get_widget_choices(widget, gp)
    if not choices:
        return None

    if semantic == "memory_card":
        for c in choices:
            if is_memory_card_choice(c) and not is_internal_ram_choice(c):
                return c
        alias_hit = _choice_matching_aliases(semantic, choices)
        if alias_hit:
            return alias_hit
        return None

    if semantic == "internal_ram":
        for c in choices:
            if is_internal_ram_choice(c):
                return c
        return _choice_matching_aliases(semantic, choices)

    if semantic == "imageformat_craw_small":
        craw = _choice_craw_prefix(choices)
        if craw:
            return craw
        return _choice_matching_aliases(semantic, choices)

    return _choice_matching_aliases(semantic, choices)


def choice_index_for_capturetarget_memory_card(
    gp: Any,
    widget: Any,
    *,
    detected_model: str | None = None,
) -> int | None:
    norm = normalize_model_name(detected_model)
    if norm != _CANON_M6_II_NORMALIZED:
        return None
    choices = get_widget_choices(widget, gp)
    if len(choices) > _CAPTURETARGET_MEMORY_CARD_INDEX:
        label = choices[_CAPTURETARGET_MEMORY_CARD_INDEX]
        if is_memory_card_choice(label):
            return _CAPTURETARGET_MEMORY_CARD_INDEX
    return None


def choice_label_at_index(widget: Any, index: int, gp: Any) -> str | None:
    choices = get_widget_choices(widget, gp)
    if 0 <= index < len(choices):
        return choices[index]
    return None


def resolve_choice_value(
    widget: Any,
    desired: str,
    path: str,
    gp: Any,
) -> str | None:
    choices = get_widget_choices(widget, gp)
    if not choices:
        return None

    hit = _exact_choice_match(desired, choices)
    if hit:
        return hit

    semantic = _semantic_for_path(path)
    if semantic:
        via_sem = choice_for_semantic(widget, semantic, gp)
        if via_sem:
            return via_sem
        alias_hit = _choice_matching_aliases(semantic, choices)
        if alias_hit:
            return alias_hit
        if semantic == "imageformat_craw_small":
            craw = _choice_craw_prefix(choices)
            if craw:
                return craw

    partial = _single_normalized_match(desired, choices)
    if partial:
        return partial

    return None


def get_config_widget(camera: Any, gp: Any, path: str) -> Any | None:
    try:
        config = camera.get_config()
        partes = [p for p in str(path).split("/") if p]
        widget_actual = config
        for parte in partes:
            gp_ok, widget_hijo = gp.gp_widget_get_child_by_name(widget_actual, parte)
            if gp_ok < gp.GP_OK:
                return None
            widget_actual = widget_hijo
        return widget_actual
    except Exception:
        return None


def read_widget_value(widget: Any, gp: Any) -> str | None:
    try:
        ret, value = gp.gp_widget_get_value(widget)
        if ret < gp.GP_OK:
            return None
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def read_camera_model_from_device(
    camera: Any,
    gp: Any,
    *,
    logger: logging.Logger | None = None,
) -> str | None:
    widget = get_config_widget(camera, gp, CAMERAMODEL_PATH)
    if widget is None:
        if logger:
            logger.debug("No se pudo leer %s", CAMERAMODEL_PATH)
        return None
    return read_widget_value(widget, gp)


def ensure_capture_target_memory_card(
    camera: Any,
    gp: Any,
    *,
    logger: logging.Logger | None = None,
    detected_model: str | None = None,
) -> bool:
    from print_scanner_app.infrastructure.camera.camera_config import WARNING_CONFIG_MANUAL

    widget = get_config_widget(camera, gp, CAPTURETARGET_PATH)
    if widget is None:
        if logger:
            logger.warning("%s", WARNING_CONFIG_MANUAL)
        return False

    choice: str | None = choice_for_semantic(widget, "memory_card", gp)
    if not choice:
        idx = choice_index_for_capturetarget_memory_card(
            gp, widget, detected_model=detected_model
        )
        if idx is not None:
            choice = choice_label_at_index(widget, idx, gp)

    if not choice:
        if logger:
            logger.warning("%s", WARNING_CONFIG_MANUAL)
        return False

    try:
        config = camera.get_config()
        w = get_config_widget(camera, gp, CAPTURETARGET_PATH)
        if w is None:
            if logger:
                logger.warning("%s", WARNING_CONFIG_MANUAL)
            return False
        gp.gp_widget_set_value(w, choice)
        camera.set_config(config)
        w2 = get_config_widget(camera, gp, CAPTURETARGET_PATH)
        current = read_widget_value(w2, gp) if w2 else None
        if current and is_memory_card_choice(current):
            return True
        if logger:
            logger.warning("%s", WARNING_CONFIG_MANUAL)
        return False
    except Exception:
        if logger:
            logger.warning("%s", WARNING_CONFIG_MANUAL)
        return False
