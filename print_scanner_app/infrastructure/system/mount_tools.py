from __future__ import annotations

import os
import subprocess
from typing import Callable, List

Run = Callable[..., subprocess.CompletedProcess]


def _default_run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def unmount_camera_mounts(*, run: Run = _default_run) -> bool:
    """
    Desmonta GVFS gphoto2/mtp.
    Devuelve True si al menos un `gio mount -s` tuvo éxito.
    """
    desmontado = False
    for scheme in ("gphoto2", "mtp"):
        try:
            r = run(["gio", "mount", "-s", scheme], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                desmontado = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    gvfs_base = f"/run/user/{os.getuid()}/gvfs"
    if os.path.exists(gvfs_base):
        try:
            for entry in os.listdir(gvfs_base):
                if "gphoto2:" in entry or "mtp:" in entry:
                    mount_path = os.path.join(gvfs_base, entry)
                    try:
                        run(["gio", "mount", "-u", mount_path], check=False, timeout=5)
                        desmontado = True
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass
        except OSError:
            pass
    return desmontado
