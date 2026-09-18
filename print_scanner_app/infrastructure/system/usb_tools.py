from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

UsbRun = Callable[..., subprocess.CompletedProcess]

_LINE_RE = re.compile(r"\s*Number\s+(\d+)/(\d+)\s+ID\s+\S+\s+(.+)")


def usbreset_command() -> Optional[str]:
    for p in ("/usr/bin/usbreset", "usbreset"):
        if p == "usbreset":
            w = shutil.which("usbreset")
            if w:
                return w
        elif os.path.isfile(p):
            return p
    return None


def _default_run(cmd: Sequence[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), **kw)


def execute_usbreset(
    identificador: str,
    *,
    run: UsbRun = _default_run,
    timeout: float = 15.0,
) -> Tuple[bool, int, str, str]:
    cmd_bin = usbreset_command()
    if not cmd_bin:
        return False, -1, "", "usbreset no encontrado"
    try:
        r = run([cmd_bin, identificador], capture_output=True, text=True, timeout=timeout)
        return (r.returncode == 0), r.returncode, (r.stdout or ""), (r.stderr or "")
    except FileNotFoundError:
        return False, -1, "", "usbreset no encontrado"
    except subprocess.TimeoutExpired:
        return False, -124, "", "timeout usbreset"


def reset_usb_address(addr: str, **kwargs) -> bool:
    """addr tipo usb:001,025 -> usbreset 001/025"""
    m = re.match(r"usb:(\d+),(\d+)", addr.strip(), re.IGNORECASE)
    if not m:
        return False
    bus, dev = m.group(1).zfill(3), m.group(2).zfill(3)
    ok, _, _, _ = execute_usbreset(f"{bus}/{dev}", **kwargs)
    return ok


def parse_usbreset_list(stdout: str, keywords: Sequence[str]) -> List[Tuple[str, str]]:
    """Parsea salida estándar de `usbreset` sin argumentos."""
    out: List[Tuple[str, str]] = []
    kws = [k.lower() for k in keywords]
    for line in stdout.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        bus, dev, desc = m.group(1).zfill(3), m.group(2).zfill(3), m.group(3)
        low = desc.lower()
        if any(k in low for k in kws):
            out.append((f"{bus}/{dev}", desc))
    return out


def list_usb_devices_by_keywords(keywords: Sequence[str], *, run: UsbRun = _default_run) -> List[Tuple[str, str]]:
    cmd = usbreset_command()
    if not cmd:
        return []
    try:
        r = run([cmd], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return []
    if r.returncode != 0 and not r.stdout:
        return []
    return parse_usbreset_list(r.stdout or "", keywords)


def reset_usb_camara_e_impresora(*, run: UsbRun = _default_run) -> int:
    """Reset software de cámara e impresora; devuelve cantidad exitosa."""
    reseteados = 0
    groups = [
        (["canon", "camera"], "cámara"),
        (["printer", "pos", "impresora"], "impresora"),
    ]
    for tipos, _nombre in groups:
        for path, _desc in list_usb_devices_by_keywords(tipos, run=run):
            ok, _, _, _ = execute_usbreset(path, run=run)
            if ok:
                reseteados += 1
    return reseteados


@dataclass
class UsbResetResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
