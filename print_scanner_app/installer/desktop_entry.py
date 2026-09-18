from __future__ import annotations

import os
import subprocess
from pathlib import Path
from textwrap import dedent

from print_scanner_app.infrastructure.system.env_tools import ASSETS_DIR


def user_desktop_dir() -> Path:
    """Carpeta de escritorio (Desktop, Escritorio vía XDG, etc.)."""
    home = Path.home()
    xdg_dirs = home / ".config" / "user-dirs.dirs"
    if xdg_dirs.is_file():
        for raw in xdg_dirs.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("XDG_DESKTOP_DIR="):
                val = line.split("=", 1)[1].strip().strip('"')
                val = val.replace("$HOME", str(home))
                return Path(val)
    for name in ("Desktop", "Escritorio"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    return home / "Desktop"


def user_applications_dir() -> Path:
    return Path.home() / ".local" / "share" / "applications"


def resolve_app_icon(repo_root: Path) -> str:
    """Ruta absoluta al icono del acceso directo (`Utils/Images/film_icon.png`)."""
    for name in ("film_icon.png", "icon.png"):
        candidate = repo_root.joinpath(*ASSETS_DIR, name)
        if candidate.is_file():
            return str(candidate.resolve())
    return "camera-photo"


def render_desktop_file(
    *,
    name: str,
    exec_path: str,
    icon_path: str,
    working_dir: str | None = None,
    comment: str = "Digitalizadora de films",
    categories: str = "Graphics;Photography;",
) -> str:
    wd_line = f"Path={working_dir}\n" if working_dir else ""
    return dedent(
        f"""\
        [Desktop Entry]
        Version=1.0
        Type=Application
        Name={name}
        Comment={comment}
        Exec={exec_path}
        Icon={icon_path}
        {wd_line}Terminal=false
        Categories={categories}
        StartupNotify=true
        """
    ).strip() + "\n"


def write_desktop(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    _trust_desktop_file(path)


def _trust_desktop_file(path: Path) -> None:
    """GNOME/Ubuntu: marcar .desktop como de confianza para que se muestre y ejecute."""
    if True:  # gio metadata::trusted ayuda en GNOME/Ubuntu aunque no sea GNOME puro
        try:
            subprocess.run(
                ["gio", "set", str(path), "metadata::trusted", "true"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(
                ["chmod", "+x", str(path)],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def install_launcher(
    *,
    repo_root: Path,
    python_executable: str,
    app_name: str = "Print Scanner",
) -> tuple[Path, Path]:
    """
    Crea acceso directo en el escritorio y entrada en el menú de aplicaciones.
    Devuelve (ruta_escritorio, ruta_applications).

    El id técnico del menú es ``print-scanner-app.desktop``.
    """
    main_py = repo_root / "print_scanner_app" / "app" / "main.py"
    exec_line = f'{python_executable} "{main_py}"'
    icon = resolve_app_icon(repo_root)
    content = render_desktop_file(
        name=app_name,
        exec_path=exec_line,
        icon_path=icon,
        working_dir=str(repo_root.resolve()),
    )
    desktop_path = user_desktop_dir() / f"{app_name}.desktop"
    apps_path = user_applications_dir() / "print-scanner-app.desktop"
    write_desktop(desktop_path, content)
    write_desktop(apps_path, content)
    # Limpia acceso directo legado si existe.
    legacy = user_desktop_dir() / "Thermal Scanner.desktop"
    if legacy.is_file() and legacy.resolve() != desktop_path.resolve():
        try:
            legacy.unlink()
        except OSError:
            pass
    return desktop_path, apps_path
