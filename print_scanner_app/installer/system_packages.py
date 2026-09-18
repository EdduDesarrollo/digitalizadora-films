from __future__ import annotations

import subprocess
from typing import Callable, List, Sequence

from print_scanner_app.installer.dependency_check import DependencyReport, check_commands
from print_scanner_app.installer.process_run import announce_step, failure_message

Run = Callable[..., subprocess.CompletedProcess]

_APT_REPAIR_NOTES = (
    "Repare el sistema manualmente y vuelva a ejecutar el instalador:\n"
    "  sudo dpkg --configure -a\n"
    "  sudo apt --fix-broken install -y\n"
    "  sudo apt update && sudo apt upgrade -y"
)


def dpkg_package_installed(package: str) -> bool:
    try:
        r = subprocess.run(
            ["dpkg", "-s", package],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def filter_missing_apt_packages(packages: Sequence[str]) -> List[str]:
    return [p for p in packages if not dpkg_package_installed(p)]


def repair_apt(*, dry_run: bool, run: Run) -> DependencyReport:
    missing_bins = check_commands(["apt", "sudo", "dpkg"])
    if missing_bins:
        return DependencyReport(ok=False, notes=["apt/sudo/dpkg no disponible para reparación"])

    if dry_run:
        return DependencyReport(ok=True, notes=["dry-run: repararía apt/dpkg"])

    announce_step("\n[1b/3] Reparando dependencias rotas (dpkg / apt fix-broken)...")
    for cmd in (
        ["sudo", "dpkg", "--configure", "-a"],
        ["sudo", "apt", "--fix-broken", "install", "-y"],
    ):
        r = run(cmd)
        if r.returncode != 0:
            return DependencyReport(
                ok=False,
                notes=[
                    failure_message(r, f"falló {' '.join(cmd)}"),
                    _APT_REPAIR_NOTES,
                ],
            )
    return DependencyReport(ok=True, notes=["Reparación apt/dpkg OK"])


def ensure_apt_updated(*, dry_run: bool, run: Run) -> DependencyReport:
    missing_bins = check_commands(["apt", "sudo"])
    if missing_bins:
        return DependencyReport(ok=False, notes=["apt/sudo no disponible para apt update"])

    if dry_run:
        return DependencyReport(ok=True, notes=["dry-run: apt update"])

    announce_step("\n[1/3] Actualizando índices de paquetes (apt update)...")
    r = run(["sudo", "apt", "update"])
    if r.returncode != 0:
        return DependencyReport(
            ok=False,
            notes=[failure_message(r, "apt update falló")],
        )
    return DependencyReport(ok=True, notes=["apt update OK"])


def ensure_apt_packages(
    packages: Sequence[str],
    *,
    dry_run: bool,
    run: Run,
    optional: Sequence[str] = (),
) -> DependencyReport:
    missing_bins = check_commands(["apt", "dpkg"])
    if missing_bins:
        return DependencyReport(ok=False, system_missing=list(packages), notes=["apt no disponible"])

    required = list(packages)
    opt = list(optional)

    if dry_run:
        notes = [f"dry-run: instalaría apt (requeridos): {required}"]
        if opt:
            notes.append(f"dry-run: instalaría apt (opcionales): {opt}")
        return DependencyReport(ok=True, notes=notes)

    reports: List[DependencyReport] = []
    if required:
        reports.append(_apt_install(required, run=run, required=True))
    if opt:
        reports.append(_apt_install(opt, run=run, required=False))

    if not reports:
        return DependencyReport(ok=True)

    out = DependencyReport(ok=True)
    for rep in reports:
        out.system_missing.extend(rep.system_missing)
        out.notes.extend(rep.notes)
        out.ok = out.ok and rep.ok
    return out


def _apt_install(packages: Sequence[str], *, run: Run, required: bool) -> DependencyReport:
    label = "requeridos" if required else "opcionales"
    to_install = filter_missing_apt_packages(packages)
    if not to_install:
        return DependencyReport(
            ok=True,
            notes=[f"apt ({label}): ya instalados — {', '.join(packages)}"],
        )

    announce_step(f"\n[2/3] Instalando paquetes de sistema ({label}), uno por uno:")
    failed: List[str] = []
    for pkg in to_install:
        announce_step(f"    • {pkg}")
        r = run(["sudo", "apt", "install", "-y", pkg])
        if r.returncode != 0:
            failed.append(pkg)
            announce_step(f"      ✗ falló: {failure_message(r, pkg)}")

    if failed:
        msg = f"No se pudieron instalar ({label}): {', '.join(failed)}"
        notes = [msg, _APT_REPAIR_NOTES]
        if required:
            return DependencyReport(ok=False, system_missing=failed, notes=notes)
        return DependencyReport(
            ok=True,
            notes=[f"apt opcional omitido ({', '.join(failed)}): ver salida anterior"],
        )

    return DependencyReport(
        ok=True,
        notes=[f"apt install OK ({label}): {', '.join(to_install)}"],
    )
