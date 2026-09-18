#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from print_scanner_app.installer.desktop_entry import install_launcher
from print_scanner_app.installer.dependency_check import DependencyReport, merge_reports
from print_scanner_app.installer.diagnose import run_system_diagnose
from print_scanner_app.installer.process_run import announce_step, run_install_command
from print_scanner_app.installer.printer_permissions import ensure_printer_permissions
from print_scanner_app.installer.python_packages import ensure_pip_requirements_file
from print_scanner_app.installer.system_packages import (
    ensure_apt_packages,
    ensure_apt_updated,
    repair_apt,
)

# Paquetes de sistema para cámara, Kivy (SDL2), portapapeles y reset USB.
_APT_REQUIRED = [
    "build-essential",
    "python3-dev",
    "python3-pip",
    "gphoto2",
    "libgphoto2-dev",
    "xclip",
    "usbutils",
    "libsdl2-dev",
    "libsdl2-image-dev",
    "libsdl2-mixer-dev",
    "libsdl2-ttf-dev",
    "libportmidi-dev",
    "libswscale-dev",
    "libavformat-dev",
    "libavcodec-dev",
    "zlib1g-dev",
]
_APT_OPTIONAL = [
    "entangle",
]


def _default_run(cmd, **kwargs):
    return run_install_command(cmd, **kwargs)


def setup_logging(log_file: Path, dry_run: bool) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("installer")
    if dry_run:
        log.info("Modo dry-run / check")
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instalador Print Scanner")
    parser.add_argument("--dry-run", action="store_true", help="No modificar sistema")
    parser.add_argument("--check", action="store_true", help="Solo verificar (alias de dry-run)")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Incluir requirements-dev.txt (pytest; solo desarrollo)",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Solo diagnosticar apt/dpkg (paquetes rotos); no instala nada",
    )
    parser.add_argument(
        "--desktop-only",
        action="store_true",
        help="Solo crear acceso directo en escritorio y menú (sin instalar dependencias)",
    )
    args = parser.parse_args(argv)

    if args.diagnose:
        return run_system_diagnose()

    if args.desktop_only:
        return _install_desktop_shortcut_only()

    dry_run = args.dry_run or args.check

    log_path = _ROOT / "print_scanner_app" / "logs" / "install.log"
    log = setup_logging(log_path, dry_run)

    run = _default_run
    reports: list[DependencyReport] = []

    if dry_run:
        announce_step("Modo verificación (--check / --dry-run): no se instalará nada.")
    else:
        announce_step(
            "Instalador Print Scanner — se mostrará el progreso de apt y pip en esta terminal."
        )
        announce_step(f"Log detallado: {log_path}\n")

    if not dry_run:
        reports.append(ensure_apt_updated(dry_run=False, run=run))
        reports.append(repair_apt(dry_run=False, run=run))

    apt_report = ensure_apt_packages(
        _APT_REQUIRED,
        optional=_APT_OPTIONAL,
        dry_run=dry_run,
        run=run,
    )
    reports.append(apt_report)

    runtime_req = _ROOT / "requirements-runtime.txt"
    if dry_run or apt_report.ok:
        reports.append(
            ensure_pip_requirements_file(runtime_req, dry_run=dry_run, run=run)
        )
    else:
        announce_step(
            "\nOmitiendo pip: primero hay que resolver los paquetes de sistema (apt). "
            "Sin libgphoto2-dev / SDL2, gphoto2 y kivy no se instalarán bien."
        )
        reports.append(
            DependencyReport(
                ok=False,
                notes=["pip omitido porque falló apt (dependencias de sistema)"],
            )
        )

    if args.dev:
        dev_req = _ROOT / "requirements-dev.txt"
        reports.append(
            ensure_pip_requirements_file(dev_req, dry_run=dry_run, run=run)
        )

    reports.append(ensure_printer_permissions(dry_run=dry_run, run=run))

    merged = merge_reports(*reports)
    log.info("Reporte dependencias ok=%s", merged.ok)
    if merged.python_missing:
        log.warning("Python faltante: %s", ", ".join(merged.python_missing))
    if merged.system_missing:
        log.warning("Sistema faltante: %s", ", ".join(merged.system_missing))
    for note in merged.notes:
        log.info("%s", note)

    if not dry_run and merged.ok:
        return _install_desktop_shortcut_only(log=log)
    elif merged.ok:
        announce_step("\nVerificación OK: todas las dependencias están presentes.")
    else:
        announce_step("\nInstalación incompleta. Revise los mensajes anteriores y el log.")
        if merged.system_missing:
            announce_step(
                "\nSi apt reporta «paquetes rotos», ejecute en otra terminal:\n"
                "  sudo dpkg --configure -a\n"
                "  sudo apt --fix-broken install -y\n"
                "Luego vuelva a lanzar: python3 print_scanner_app/installer/install.py"
            )

    return 0 if merged.ok else 2


def _install_desktop_shortcut_only(log: logging.Logger | None = None) -> int:
    """Crea .desktop en Escritorio/Desktop y en ~/.local/share/applications."""
    announce_step("\nCreando acceso directo en el escritorio y menú de aplicaciones...")
    try:
        desk_path, apps_path = install_launcher(
            repo_root=_ROOT,
            python_executable=sys.executable,
        )
    except Exception as e:  # noqa: BLE001
        if log:
            log.error("No se pudo escribir .desktop: %s", e)
        announce_step(f"Error al crear acceso directo: {e}")
        return 3
    if log:
        log.info("Escrito %s y %s", desk_path, apps_path)
    announce_step(f"Escritorio: {desk_path}")
    announce_step(f"Menú de apps: {apps_path}")
    announce_step(
        "Si no aparece el icono en GNOME: clic derecho → «Permitir lanzar» "
        "o vuelva a ejecutar el instalador con la impresora ya configurada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
