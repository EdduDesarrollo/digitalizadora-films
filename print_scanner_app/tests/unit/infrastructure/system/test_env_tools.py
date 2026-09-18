from pathlib import Path

from print_scanner_app.infrastructure.system.env_tools import project_root_from_here


def test_project_root_finds_print_scanner_app(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "print_scanner_app").mkdir(parents=True)
    here = root / "print_scanner_app" / "app"
    here.mkdir(parents=True)
    assert project_root_from_here(here) == root


def test_project_root_fallback(tmp_path: Path):
    assert project_root_from_here(tmp_path / "orphan") == tmp_path / "orphan"
