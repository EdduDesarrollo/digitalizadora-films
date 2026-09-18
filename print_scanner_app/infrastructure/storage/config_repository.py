from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Set, Tuple

# Claves conocidas de config; se preservan entradas desconocidas al guardar.
NUMERO_FRAME_KEY = "NUMERO_FRAME"

DEFAULT_CONFIG: Dict[str, Any] = {
    "PREFIJO_ARCHIVO": "",
    "CAMARA": "",
    "DIRECTORIO": "",
    "CODIGO_REFERENCIA": "",
    "CONFIG_CAMARA": {},
    "UMBRAL_PX_BLANCOS": 2000,
    # Último número de frame mostrado en UI / usado en lógica de captura (`docs/NUMERO_FRAME_CONFIG.md`).
    NUMERO_FRAME_KEY: 0,
    # Log detallado de estado en cada run_capture_tick (solo diagnóstico).
    "DEBUG_CAPTURE_TICK_TRACE": False,
}


def parse_numero_frame_value(raw: Any) -> Tuple[int, bool]:
    """
    Interpreta `NUMERO_FRAME` desde JSON.

    Returns:
        (n, needs_rewrite): entero >= 0 para `frame_count` / UI; `needs_rewrite` si el valor en
        disco era inválido y debe normalizarse guardando `n` (típicamente 0).
    """
    if raw is None:
        return 0, True
    if isinstance(raw, bool):
        return 0, True
    if isinstance(raw, int):
        if raw < 0:
            return 0, True
        return raw, False
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return 0, True
        if not float(raw).is_integer():
            return 0, True
        n = int(raw)
        if n < 0:
            return 0, True
        return n, False
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return 0, True
        try:
            n = int(s, 10)
        except ValueError:
            return 0, True
        if n < 0:
            return 0, True
        return n, False
    return 0, True

EXPECTED_KEYS: Set[str] = set(DEFAULT_CONFIG.keys())


def resolve_output_directory(cfg: Mapping[str, Any]) -> str:
    """Ruta absoluta de salida desde `DIRECTORIO` (ignora `CARPETA_DESTINO` legacy)."""
    d = str(cfg.get("DIRECTORIO") or "").strip()
    if not d:
        return ""
    return str(Path(d).expanduser().resolve())


def output_directory_configured(cfg: Mapping[str, Any]) -> bool:
    """True si `DIRECTORIO` resuelve a un directorio existente."""
    path = resolve_output_directory(cfg)
    return bool(path) and Path(path).is_dir()


def default_config_merged(path: Path | None = None) -> Dict[str, Any]:
    if path and path.is_file():
        data = load_config(path)
        return data
    return dict(DEFAULT_CONFIG)


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("config.json debe ser un objeto JSON")
    merged: Dict[str, Any] = dict(DEFAULT_CONFIG)
    merged.update(raw)
    return merged


def save_config(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dict(data), f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def validate_expected_keys(data: Mapping[str, Any]) -> Set[str]:
    """Devuelve claves esperadas ausentes (solo informativo)."""
    return EXPECTED_KEYS - set(data.keys())


class ConfigRepository:
    """Acceso a config.json del proyecto."""

    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Dict[str, Any]:
        if not self._path.is_file():
            return dict(DEFAULT_CONFIG)
        return load_config(self._path)

    def save(self, data: MutableMapping[str, Any]) -> None:
        save_config(self._path, data)

    def update_key(self, key: str, value: Any) -> Dict[str, Any]:
        cfg = self.load()
        cfg[key] = value
        self.save(cfg)
        return cfg
