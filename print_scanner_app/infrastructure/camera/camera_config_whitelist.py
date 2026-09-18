"""Claves CONFIG_CAMARA persistibles y aplicables (preset de digitación)."""

from __future__ import annotations

from typing import Any, Mapping

from print_scanner_app.infrastructure.camera.camera_config_locale import (
    CAMERAMODEL_PATH,
    CAPTURETARGET_PATH,
)

# Orden estable; solo estas rutas entran en JSON, diff Entangle y apply en arranque.
CONFIG_CAMARA_WHITELIST: frozenset[str] = frozenset(
    {
        CAMERAMODEL_PATH,
        CAPTURETARGET_PATH,
        "main/imgsettings/iso",
        "main/imgsettings/whitebalance",
        "main/imgsettings/colortemperature",
        "main/imgsettings/whitebalanceadjusta",
        "main/imgsettings/whitebalanceadjustb",
        "main/imgsettings/colorspace",
        "main/imgsettings/imageformat",
        "main/imgsettings/imageformatsd",
        "main/imgsettings/imageformatcf",
        "main/capturesettings/shutterspeed",
        "main/capturesettings/aperture",
        "main/capturesettings/picturestyle",
        "main/capturesettings/meteringmode",
        "main/capturesettings/focusmode",
        "main/capturesettings/autoexposuremode",
        "main/capturesettings/autoexposuremodedial",
        "main/capturesettings/drivemode",
        "main/capturesettings/afmethod",
        "main/capturesettings/exposurecompensation",
        "main/capturesettings/continuousaf",
        "main/capturesettings/highisonr",
    }
)


def filter_camera_config_to_whitelist(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Conserva solo claves whitelist; descarta export completo legacy."""
    if not isinstance(config, Mapping):
        return {}
    return {k: v for k, v in config.items() if str(k).strip() in CONFIG_CAMARA_WHITELIST}


def has_preset_camera_config(config: Mapping[str, Any] | None) -> bool:
    """True si hay al menos una clave whitelist distinta de capturetarget/cameramodel."""
    filtered = filter_camera_config_to_whitelist(config)
    if not filtered:
        return False
    non_invariant = {
        k
        for k in filtered
        if k not in (CAPTURETARGET_PATH, CAMERAMODEL_PATH)
    }
    return bool(non_invariant)


def diff_camera_config(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Claves whitelist cuyo valor cambió entre snapshots."""
    b = filter_camera_config_to_whitelist(before)
    a = filter_camera_config_to_whitelist(after)
    out: dict[str, Any] = {}
    for key in CONFIG_CAMARA_WHITELIST:
        if key not in a:
            continue
        if key not in b or b[key] != a[key]:
            out[key] = a[key]
    return out
