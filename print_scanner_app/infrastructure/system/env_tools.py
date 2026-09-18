from __future__ import annotations

from pathlib import Path

ASSETS_DIR = ("Utils", "Images")


def project_root_from_here(here: Path, marker: str = "print_scanner_app") -> Path:
    """Sube desde `here` hasta encontrar carpeta que contiene `marker`, o padres del repo."""
    cur = here.resolve()
    for p in [cur, *cur.parents]:
        if (p / marker).is_dir():
            return p
    return cur


def project_asset_path(name: str, here: Path | None = None) -> Path:
    """Ruta a un archivo bajo `Utils/Images/` en la raíz del repo."""
    base = here if here is not None else Path(__file__).resolve().parent
    root = project_root_from_here(base)
    return root.joinpath(*ASSETS_DIR, name)


def project_logo_path(here: Path | None = None) -> Path:
    """Ruta a `logo.png` en `Utils/Images/`."""
    return project_asset_path("logo.png", here)
