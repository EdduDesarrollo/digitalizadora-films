from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from print_scanner_app.infrastructure.camera.camera_config_locale import (
    CAPTURETARGET_PATH,
    get_config_widget,
    is_memory_card_choice,
    read_widget_value,
    resolve_choice_value,
    should_skip_config_path,
    should_skip_config_value,
    widget_has_choices,
)
from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
    filter_camera_config_to_whitelist,
)

WARNING_CONFIG_MANUAL = (
    "Warning! No se pudo configurar la camara. Revisar configuración manualmente."
)

WARNING_MODEL_MISMATCH = (
    "Warning! Modelo de cámara no coincide con config.json "
    "(esperado: {expected}, detectado: {detected}). "
    "No se aplicó CONFIG_CAMARA. Revisar configuración manualmente."
)

INFO_CAMERAMODEL_MISSING = (
    "cameramodel no en JSON; se aplica CONFIG_CAMARA sin verificación de modelo"
)

CRITICAL_WIDGET_PATHS = frozenset({CAPTURETARGET_PATH})


@dataclass
class ApplyConfigResult:
    """
    Resultado del apply de CONFIG_CAMARA.

    ok es False si hay fallos en paths críticos o model_mismatch=True.
    """

    ok: bool = True
    applied: list[str] = field(default_factory=list)
    failed: list[tuple[str, str, list[str]]] = field(default_factory=list)
    skipped_readonly: list[str] = field(default_factory=list)
    model_mismatch: bool = False
    expected_model: str | None = None
    detected_model: str | None = None


def normalize_camera_config(configuraciones: Mapping[str, Any] | None) -> dict[str, Any]:
    """
    Normaliza estructura de config de cámara:
    - acepta None / no-mapping -> {}
    - descarta claves vacías
    - limpia espacios en rutas
    """
    if not isinstance(configuraciones, Mapping):
        return {}
    out: dict[str, Any] = {}
    for k, v in configuraciones.items():
        key = str(k).strip()
        if not key:
            continue
        out[key] = v
    return out


def _navigate_widget(config: Any, path: str, gp: Any) -> Any | None:
    try:
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


def _value_for_widget(
    widget: Any,
    path: str,
    valor: Any,
    gp: Any,
) -> Any | None:
    if should_skip_config_value(path, valor, widget, gp):
        return None
    if isinstance(valor, str) and valor.lower() in ("none", "null"):
        return None
    if isinstance(valor, str) and widget_has_choices(widget, gp):
        resolved = resolve_choice_value(widget, valor, path, gp)
        if resolved is not None:
            return resolved
        choices = []
        try:
            from print_scanner_app.infrastructure.camera.camera_config_locale import (
                get_widget_choices,
            )

            choices = get_widget_choices(widget, gp)
        except Exception:
            pass
        if should_skip_config_value(path, valor, widget, gp):
            return None
        return None
    return valor


def apply_camera_configurations(
    camera: Any,
    configuraciones: Mapping[str, Any],
    gp: Any,
    *,
    logger: logging.Logger | None = None,
    model_mismatch: bool = False,
    expected_model: str | None = None,
    detected_model: str | None = None,
) -> ApplyConfigResult:
    conf = filter_camera_config_to_whitelist(normalize_camera_config(configuraciones))
    result = ApplyConfigResult(
        expected_model=expected_model,
        detected_model=detected_model,
    )
    if not conf:
        return result

    if model_mismatch:
        result.model_mismatch = True
        result.ok = False
        return result

    try:
        config = camera.get_config()
    except Exception:
        result.ok = False
        return result

    pending: list[tuple[str, Any, Any]] = []

    for ruta_completa, valor in conf.items():
        if should_skip_config_path(ruta_completa):
            result.skipped_readonly.append(ruta_completa)
            continue

        widget = _navigate_widget(config, ruta_completa, gp)
        if widget is None:
            result.failed.append((ruta_completa, str(valor), []))
            continue

        if should_skip_config_path(ruta_completa, widget, gp):
            if ruta_completa not in result.skipped_readonly:
                result.skipped_readonly.append(ruta_completa)
            continue

        if should_skip_config_value(ruta_completa, valor, widget, gp):
            result.skipped_readonly.append(ruta_completa)
            continue

        valor_a_establecer = _value_for_widget(widget, ruta_completa, valor, gp)
        if valor_a_establecer is None and isinstance(valor, str) and widget_has_choices(
            widget, gp
        ):
            if should_skip_config_value(ruta_completa, valor, widget, gp):
                result.skipped_readonly.append(ruta_completa)
                continue
            from print_scanner_app.infrastructure.camera.camera_config_locale import (
                get_widget_choices,
            )

            choices = get_widget_choices(widget, gp)
            result.failed.append((ruta_completa, str(valor), choices))
            continue

        if valor_a_establecer is None and should_skip_config_value(
            ruta_completa, valor, widget, gp
        ):
            result.skipped_readonly.append(ruta_completa)
            continue

        try:
            gp.gp_widget_set_value(widget, valor_a_establecer)
            pending.append((ruta_completa, valor, widget))
        except gp.GPhoto2Error:
            from print_scanner_app.infrastructure.camera.camera_config_locale import (
                get_widget_choices,
            )

            choices = get_widget_choices(widget, gp) if widget_has_choices(widget, gp) else []
            result.failed.append((ruta_completa, str(valor), choices))
        except Exception:
            result.failed.append((ruta_completa, str(valor), []))

    if pending:
        try:
            camera.set_config(config)
            result.applied = [p[0] for p in pending]
        except Exception:
            for ruta, valor, _w in pending:
                result.failed.append((ruta, str(valor), []))
            result.applied = []

    critical_failed = [f for f in result.failed if f[0] in CRITICAL_WIDGET_PATHS]
    result.ok = len(critical_failed) == 0 and not result.model_mismatch

    if critical_failed and logger:
        logger.warning("%s", WARNING_CONFIG_MANUAL)
        for ruta, deseado, choices in critical_failed:
            trunc = choices[:5]
            extra = "..." if len(choices) > 5 else ""
            logger.warning(
                "CONFIG_CAMARA fallida: %s deseado=%r choices=%r%s",
                ruta,
                deseado,
                trunc,
                extra,
            )
    elif result.failed and logger:
        logger.debug(
            "CONFIG: %s path(s) no aplicados (no críticos); applied=%s skipped=%s",
            len(result.failed),
            len(result.applied),
            len(result.skipped_readonly),
        )

    _revalidate_critical_paths(camera, gp, conf, logger)

    return result


def _revalidate_critical_paths(
    camera: Any,
    gp: Any,
    conf: dict[str, Any],
    logger: logging.Logger | None,
) -> None:
    if CAPTURETARGET_PATH not in conf:
        return
    widget = get_config_widget(camera, gp, CAPTURETARGET_PATH)
    if widget is None:
        return
    current = read_widget_value(widget, gp)
    if current and not is_memory_card_choice(current):
        if logger:
            logger.warning(
                "%s (post-apply: capturetarget=%r)",
                WARNING_CONFIG_MANUAL,
                current,
            )


def apply_configurations_to_camera(
    camera: Any,
    configuraciones: Mapping[str, Any],
    gp: Any,
    *,
    logger: logging.Logger | None = None,
    model_mismatch: bool = False,
    expected_model: str | None = None,
    detected_model: str | None = None,
) -> bool:
    """Compatibilidad: devuelve ApplyConfigResult.ok."""
    return apply_camera_configurations(
        camera,
        configuraciones,
        gp,
        logger=logger,
        model_mismatch=model_mismatch,
        expected_model=expected_model,
        detected_model=detected_model,
    ).ok
