from __future__ import annotations

from pathlib import Path

from print_scanner_app.infrastructure.system.env_tools import (
    ASSETS_DIR,
    project_asset_path,
    project_logo_path,
    project_root_from_here,
)


def test_project_logo_path_points_to_utils_images(tmp_path):
    (tmp_path / "print_scanner_app").mkdir()
    assets = tmp_path.joinpath(*ASSETS_DIR)
    assets.mkdir(parents=True)
    (assets / "logo.png").write_bytes(b"png")
    p = project_logo_path(tmp_path / "print_scanner_app" / "app")
    assert p == tmp_path / "Utils" / "Images" / "logo.png"
    assert p.is_file()


def test_project_asset_path_under_assets_dir(tmp_path):
    (tmp_path / "print_scanner_app").mkdir()
    assets = tmp_path.joinpath(*ASSETS_DIR)
    assets.mkdir(parents=True)
    (assets / "film_icon.png").write_bytes(b"ico")
    p = project_asset_path("film_icon.png", tmp_path / "print_scanner_app" / "app")
    assert p == assets / "film_icon.png"
    assert p.is_file()


def test_project_root_from_here_finds_print_scanner_app(tmp_path):
    mod = tmp_path / "print_scanner_app"
    mod.mkdir()
    root = project_root_from_here(mod / "ui")
    assert root == tmp_path
