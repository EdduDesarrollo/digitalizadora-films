from __future__ import annotations

import subprocess
from typing import List, Tuple

from print_scanner_app.installer.process_run import announce_step


def _run_capture(cmd: List[str]) -> Tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode, out


def run_system_diagnose() -> int:
    """Muestra estado de dpkg/apt (sin instalar nada)."""
    announce_step("=== Diagnóstico del sistema (apt/dpkg) ===\n")

    steps = [
        (["dpkg", "--audit"], "Paquetes rotos (dpkg --audit)"),
        (["sudo", "apt-get", "check"], "Comprobación apt-get check"),
        (["apt-mark", "showhold"], "Paquetes retenidos (held)"),
    ]
    problems = 0
    for cmd, title in steps:
        announce_step(f"--- {title} ---")
        code, out = _run_capture(cmd)
        if out:
            announce_step(out)
        else:
            announce_step("(sin salida)")
        if code != 0:
            problems += 1
        announce_step("")

    announce_step("--- Paquetes en estado anómalo (dpkg -l) ---")
    _, all_pkgs = _run_capture(["dpkg", "-l"])
    # Estados: iU=unpacked, iF=config-failed, iH=half-installed, rc=config restante
    bad_states = ("iU", "iF", "iH", "iG", "iR", "rc")
    bad_lines = [ln for ln in (all_pkgs or "").splitlines() if any(s in ln[:5] for s in bad_states)]
    if bad_lines:
        problems += 1
        for ln in bad_lines[:40]:
            announce_step(ln)
        if len(bad_lines) > 40:
            announce_step(f"... y {len(bad_lines) - 40} más")
    else:
        announce_step("No se detectaron estados anómalos obvios en dpkg -l")

    announce_step(
        "\n=== Reparación recomendada (ejecutar en orden) ===\n"
        "  sudo dpkg --configure -a\n"
        "  sudo apt --fix-broken install -y\n"
        "  sudo apt update\n"
        "  python3 print_scanner_app/installer/install.py\n"
    )
    return 1 if problems else 0
