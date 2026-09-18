from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from print_scanner_app.installer.dependency_check import DependencyReport
from print_scanner_app.installer.process_run import announce_step, failure_message

Run = Callable[..., subprocess.CompletedProcess]

# Nombre pip (normalizado a minúsculas) -> módulo para importlib.
PIP_IMPORT_MODULE: dict[str, str] = {
    "kivy": "kivy",
    "gphoto2": "gphoto2",
    "python-escpos": "escpos",
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pillow": "PIL",
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "pytest-mock": "pytest_mock",
}

_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:"
    r"(?:[<>=!~]=|===|~=)\s*[^\s#]+)?\s*(?:,\s*[^\s#]+)*\s*$"
)


def pip_distribution_name(requirement_line: str) -> str | None:
    """Extrae el nombre del paquete pip de una línea de requirements (sin comentarios)."""
    line = requirement_line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    m = _REQ_LINE.match(line)
    if not m:
        return None
    return m.group(1)


def load_requirements_file(path: Path) -> List[str]:
    """Líneas instalables de un archivo requirements (*.txt)."""
    if not path.is_file():
        return []
    specs: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        specs.append(line)
    return specs


def import_module_for_pip_name(pip_name: str) -> str:
    key = pip_name.lower()
    if key in PIP_IMPORT_MODULE:
        return PIP_IMPORT_MODULE[key]
    return key.replace("-", "_").split("[")[0]


def import_available(module: str) -> bool:
    """Comprueba import real (no solo find_spec); detecta extensiones rotas."""
    if importlib.util.find_spec(module) is None:
        return False
    try:
        importlib.import_module(module)
        return True
    except Exception:  # noqa: BLE001 — ImportError, OSError en .so, etc.
        return False


def missing_imports_for_specs(specs: Sequence[str]) -> List[str]:
    missing: List[str] = []
    for spec in specs:
        dist = pip_distribution_name(spec)
        if dist is None:
            continue
        mod = import_module_for_pip_name(dist)
        if not import_available(mod):
            missing.append(spec)
    return missing


def pip_install_args() -> List[str]:
    """Flags extra para pip en distros con PEP 668 (p. ej. Ubuntu 24.04)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode == 0 and "--break-system-packages" in (r.stdout or ""):
        return ["--break-system-packages"]
    return []


def ensure_pip_packages(
    pip_names: Iterable[str],
    *,
    dry_run: bool,
    run: Run,
) -> DependencyReport:
    specs = list(pip_names)
    return _ensure_pip_specs(specs, dry_run=dry_run, run=run)


def ensure_pip_requirements_file(
    requirements_path: Path,
    *,
    dry_run: bool,
    run: Run,
) -> DependencyReport:
    specs = load_requirements_file(requirements_path)
    if not specs and not requirements_path.is_file():
        return DependencyReport(
            ok=False,
            notes=[f"No existe {requirements_path}"],
        )
    return _ensure_pip_specs(specs, dry_run=dry_run, run=run, label=str(requirements_path))


def _ensure_pip_specs(
    specs: List[str],
    *,
    dry_run: bool,
    run: Run,
    label: str = "pip",
) -> DependencyReport:
    missing = missing_imports_for_specs(specs)
    if not missing:
        return DependencyReport(ok=True)

    if dry_run:
        return DependencyReport(
            ok=False,
            python_missing=missing,
            notes=[f"dry-run ({label}): faltan {', '.join(missing)}"],
        )

    announce_step(f"\n[3/3] Instalando paquetes Python ({label}), uno por uno:")
    failed: List[str] = []
    extra = pip_install_args()

    for spec in missing:
        announce_step(f"    • {spec}")
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            *extra,
            spec,
        ]
        r = run(cmd)
        if r.returncode != 0:
            failed.append(spec)
            announce_step(f"      ✗ pip falló: {failure_message(r, spec)}")
            continue
        if spec in missing_imports_for_specs([spec]):
            failed.append(spec)
            dist = pip_distribution_name(spec) or spec
            mod = import_module_for_pip_name(dist)
            announce_step(
                f"      ✗ pip terminó pero no se puede importar «{mod}» "
                f"(¿faltan librerías de sistema? p. ej. libgphoto2-dev para gphoto2)"
            )

    if failed:
        notes = [
            "No se pudieron instalar o importar: " + ", ".join(failed),
            f"Pruebe manualmente: {sys.executable} -m pip install --user {' '.join(extra)} " + " ".join(failed),
        ]
        return DependencyReport(ok=False, python_missing=failed, notes=notes)

    return DependencyReport(ok=True, notes=[f"pip install OK ({label})"])
