from __future__ import annotations

import getpass
import grp
import os
import subprocess
from pathlib import Path
from typing import Callable, List

from print_scanner_app.installer.dependency_check import DependencyReport
from print_scanner_app.installer.process_run import announce_step, failure_message

try:
    from print_scanner_app.infrastructure.printer.printer_device import (
        describe_device_permissions,
        find_usb_lp_devices,
    )
except ImportError:
    describe_device_permissions = None  # type: ignore[misc, assignment]
    find_usb_lp_devices = None  # type: ignore[misc, assignment]

Run = Callable[..., subprocess.CompletedProcess]

_RULES_NAME = "99-thermal-scanner-lp.rules"
_RULES_SRC = Path(__file__).resolve().parent / "udev" / _RULES_NAME
_RULES_DST = Path(f"/etc/udev/rules.d/{_RULES_NAME}")


def _user_in_group(group: str, username: str | None = None) -> bool:
    user = username or getpass.getuser()
    try:
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        return False
    try:
        members = grp.getgrgid(gid).gr_mem
    except KeyError:
        return False
    if user in members:
        return True
    # Grupo primario o secundario del proceso actual
    try:
        import pwd

        pw = pwd.getpwnam(user)
        return gid in os.getgrouplist(user, pw.pw_gid)
    except (KeyError, OSError):
        return False


def ensure_printer_permissions(*, dry_run: bool, run: Run) -> DependencyReport:
    """
    Instala regla udev para /dev/usb/lp* y añade al usuario al grupo lp.
    Tras añadir al grupo hace falta cerrar sesión o reiniciar (o newgrp lp).
    """
    user = os.environ.get("USER") or getpass.getuser()
    notes: List[str] = []

    if not _RULES_SRC.is_file():
        return DependencyReport(ok=False, notes=[f"No se encuentra {_RULES_SRC}"])

    if dry_run:
        in_lp = _user_in_group("lp", user)
        return DependencyReport(
            ok=True,
            notes=[
                f"dry-run: instalaría udev en {_RULES_DST}",
                f"dry-run: usermod -aG lp {user} (en grupo lp: {in_lp})",
            ],
        )

    announce_step("\n[4/4] Permisos impresora térmica (/dev/usb/lp*)...")

    if _RULES_DST.is_file():
        try:
            if _RULES_DST.read_text(encoding="utf-8") == _RULES_SRC.read_text(encoding="utf-8"):
                notes.append(f"Regla udev ya presente: {_RULES_DST}")
            else:
                announce_step(f"    Actualizando {_RULES_DST}")
                _install_rules_file(run)
                notes.append("Regla udev actualizada")
        except OSError:
            _install_rules_file(run)
            notes.append("Regla udev instalada")
    else:
        announce_step(f"    Instalando regla udev → {_RULES_DST}")
        _install_rules_file(run)
        notes.append("Regla udev instalada")

    for cmd in (
        ["sudo", "udevadm", "control", "--reload-rules"],
        ["sudo", "udevadm", "trigger", "subsystem-match=usbmisc"],
        ["sudo", "udevadm", "trigger", "subsystem-match=usb"],
    ):
        r = run(cmd)
        if r.returncode != 0:
            notes.append(failure_message(r, "udevadm trigger"))

    _apply_immediate_lp_chmod(run, notes)

    in_lp = _user_in_group("lp", user)
    if not in_lp:
        announce_step(f"    Añadiendo usuario «{user}» al grupo lp (requiere sudo)...")
        r = run(["sudo", "usermod", "-aG", "lp", user])
        if r.returncode != 0:
            return DependencyReport(
                ok=False,
                notes=[
                    failure_message(r, "usermod -aG lp falló"),
                    f"Ejecute manualmente: sudo usermod -aG lp {user}",
                ],
            )
        notes.append(f"Usuario {user} añadido al grupo lp")
        in_lp = False  # hasta reiniciar sesión
    else:
        notes.append(f"Usuario {user} ya está en el grupo lp")

    if not in_lp:
        announce_step(
            "\n⚠ Si tras chmod sigue sin acceso: cierre sesión y vuelva a entrar "
            f"(grupo lp para «{user}»), o ejecute: newgrp lp\n"
            "   Desenchufe y enchufe la impresora USB.\n"
        )
        notes.append("Reinicio de sesión recomendado si chmod no bastó")

    announce_step(
        "\nDesenchufe y enchufe la impresora USB para aplicar la regla udev.\n"
        "Compruebe: ls -l /dev/usb/lp*  (debe ser crw-rw-rw- o grupo lp con su usuario en lp)\n"
    )

    return DependencyReport(ok=True, notes=notes)


def _apply_immediate_lp_chmod(run: Run, notes: List[str]) -> None:
    """chmod inmediato en nodos existentes (no requiere cerrar sesión)."""
    if find_usb_lp_devices is None:
        return
    devs = find_usb_lp_devices()
    if not devs:
        announce_step("    (ningún /dev/usb/lp* detectado aún; enchufe la impresora y repita chmod)")
        return
    paths = [str(d) for d in devs]
    announce_step(f"    Permisos inmediatos: chmod a+rw {' '.join(paths)}")
    r = run(["sudo", "chmod", "a+rw", *paths])
    if r.returncode == 0:
        notes.append(f"chmod a+rw OK: {', '.join(paths)}")
        if describe_device_permissions:
            for d in devs:
                announce_step(f"    → {describe_device_permissions(d)}")
    else:
        notes.append(failure_message(r, "chmod en /dev/usb/lp* falló"))


def _install_rules_file(run: Run) -> None:
    content = _RULES_SRC.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["sudo", "tee", str(_RULES_DST)],
        input=content,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError((proc.stderr or proc.stdout or "sudo tee falló").strip())
