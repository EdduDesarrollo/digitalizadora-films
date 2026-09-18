from __future__ import annotations

import subprocess
import sys
from typing import Sequence


def announce_step(message: str) -> None:
    """Mensaje visible en terminal (además del log del instalador)."""
    print(message, flush=True)


def run_install_command(
    cmd: Sequence[str],
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Ejecuta un comando mostrando su salida en la terminal (apt, pip, etc.).
    Ignora capture_output/text para no ocultar el progreso al usuario.
    """
    kwargs.pop("capture_output", None)
    kwargs.pop("text", None)
    announce_step(f"\n>>> {' '.join(str(c) for c in cmd)}")
    return subprocess.run(list(cmd), **kwargs)


def failure_message(result: subprocess.CompletedProcess, fallback: str) -> str:
    captured = ((result.stderr or "") + (result.stdout or "")).strip()
    if captured:
        return captured
    return f"{fallback} (código de salida {result.returncode})"
