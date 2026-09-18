"""Selector de carpeta nativo vía zenity (Ubuntu Desktop y derivados con zenity en PATH)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

ZENITY_TIMEOUT_SEC = 120


def _zenity_start_directory(initial_path: str | None) -> str:
    """Ruta inicial para --filename= (debe terminar en separador para carpetas)."""
    raw = (initial_path or "").strip()
    if not raw:
        base = Path.home().resolve()
    else:
        p = Path(raw).expanduser()
        try:
            if p.is_dir():
                base = p.resolve()
            elif p.parent.is_dir():
                base = p.parent.resolve()
            else:
                base = Path.home().resolve()
        except OSError:
            base = Path.home().resolve()
    return str(base) + os.sep


def pick_directory_ubuntu_zenity(
    initial_path: str | None,
    *,
    timeout_sec: int = ZENITY_TIMEOUT_SEC,
) -> str | None:
    """
    Abre ``zenity --file-selection --directory``.

    Retorna ruta absoluta de un directorio existente, o ``None`` si el usuario
    canceló, zenity no está disponible, la salida es inválida o está vacía.
    Alcance oficial de producto: **Ubuntu** (otras distros con zenity pueden funcionar).
    """
    if sys.platform != "linux":
        return None
    zenity = shutil.which("zenity")
    if not zenity:
        return None
    start = _zenity_start_directory(initial_path)
    cmd = [
        zenity,
        "--file-selection",
        "--directory",
        "--modal",
        "--title=Cambiar directorio",
        f"--filename={start}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _log.warning("zenity (carpeta): timeout (%ss)", timeout_sec)
        return None
    except OSError as exc:
        _log.info("zenity (carpeta): no ejecutable: %s", exc)
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip()
    if not line:
        return None
    try:
        resolved = Path(line).expanduser().resolve(strict=False)
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return str(resolved)
