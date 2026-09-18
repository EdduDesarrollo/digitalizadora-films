from __future__ import annotations

import os
from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def ensure_dir(path: PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_destination_path(base_dir: PathLike, *relative_parts: str) -> Path:
    """Une rutas y normaliza sin salir de base (symlink bypass simple)."""
    base = Path(base_dir).resolve()
    target = base.joinpath(*relative_parts).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError(f"Ruta destino fuera de {base}") from e
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    return target
