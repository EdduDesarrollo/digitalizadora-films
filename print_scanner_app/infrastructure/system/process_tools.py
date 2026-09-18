from __future__ import annotations

import os
import subprocess
from typing import Callable, List

Run = Callable[..., subprocess.CompletedProcess]


def _default_run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def kill_processes_using_device(
    device_path: str,
    *,
    run: Run = _default_run,
    own_pid: int | None = None,
) -> List[str]:
    """
    Intenta matar procesos del usuario que usan el dispositivo (sin sudo).
    Devuelve PIDs a los que se envió kill (pueden haber fallado silenciosamente).
    """
    pid_self = str(own_pid if own_pid is not None else os.getpid())
    killed: List[str] = []
    try:
        r = run(["fuser", device_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return killed
    if r.returncode != 0:
        return killed
    pids = (r.stdout or "").strip().split()
    for pid in pids:
        if pid == pid_self:
            continue
        try:
            run(["kill", "-9", pid], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            killed.append(pid)
        except subprocess.CalledProcessError:
            pass
    return killed
