from __future__ import annotations

import getpass
import glob
import grp
import os
import pwd
from pathlib import Path
from typing import List, Optional


def find_usb_lp_devices(pattern: str = "/dev/usb/lp*") -> List[Path]:
    return sorted(Path(p) for p in glob.glob(pattern))


def device_is_writable(device: Path | str) -> bool:
    path = str(device)
    if not os.path.exists(path):
        return False
    return os.access(path, os.W_OK | os.R_OK)


def describe_device_permissions(device: Path | str) -> str:
    """Estado del nodo de dispositivo para diagnóstico en logs."""
    dev = str(device)
    if not os.path.exists(dev):
        return f"{dev}: no existe (¿impresora enchufada?)"

    st = os.stat(dev)
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)

    mode = oct(st.st_mode & 0o777)
    user = getpass.getuser()
    try:
        group_names = [grp.getgrgid(g).gr_name for g in os.getgroups()]
    except (KeyError, OSError):
        group_names = []

    return (
        f"{dev}: modo={mode} dueño={owner} grupo={group} "
        f"usuario={user} grupos=[{', '.join(group_names)}] "
        f"escribible={device_is_writable(dev)}"
    )


def lp_permission_hint(device: Path | str) -> str:
    detail = describe_device_permissions(device)
    return (
        f"Sin permiso de escritura en la impresora.\n"
        f"  {detail}\n"
        "Solución (en terminal):\n"
        "  python3 print_scanner_app/installer/install.py\n"
        "  (instala udev y ajusta permisos; luego desenchufe y enchufe la USB)\n"
        "O manualmente:\n"
        "  sudo tee /etc/udev/rules.d/99-thermal-scanner-lp.rules < print_scanner_app/installer/udev/99-thermal-scanner-lp.rules\n"
        "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
        "  sudo chmod a+rw /dev/usb/lp*\n"
        "  sudo usermod -aG lp $USER   # y cerrar sesión, o: newgrp lp"
    )


def first_lp_device(*, require_writable: bool = True) -> Optional[Path]:
    devs = find_usb_lp_devices()
    if not devs:
        return None
    if require_writable:
        for d in devs:
            if device_is_writable(d):
                return d
        return devs[0]
    return devs[0]
