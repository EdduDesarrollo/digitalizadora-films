"""
Convención de nombre de sesión / archivo.

`NOMBRE_ARCHIVO` = PREFIJO_ARCHIVO + '-' + CODIGO_REFERENCIA normalizado.
El archivo de pendientes es `Utils/Pending_raws/raw_pendientes_{NOMBRE_ARCHIVO}.txt`.
El basename destino de cada RAW en disco es `{NOMBRE_ARCHIVO}-{frame:06d}.cr3`.
"""

from __future__ import annotations

from typing import Any, Mapping


def normalized_codigo_referencia(raw: str) -> str:
    return (raw or "").strip().upper()


def normalized_prefijo_archivo(raw: str) -> str:
    return (raw or "").strip().upper()


def raw_pending_file_key_from_config(cfg: Mapping[str, Any]) -> str:
    prefijo = normalized_prefijo_archivo(str(cfg.get("PREFIJO_ARCHIVO", "")))
    codigo = normalized_codigo_referencia(str(cfg.get("CODIGO_REFERENCIA", "")))
    if not codigo:
        return "_sin_codigo_"
    if not prefijo:
        return codigo
    return f"{prefijo}-{codigo}"
