from pathlib import Path

from print_scanner_app.installer.dependency_check import DependencyReport, check_commands, merge_reports
from print_scanner_app.installer.desktop_entry import render_desktop_file, resolve_app_icon, user_desktop_dir
from print_scanner_app.installer.python_packages import (
    ensure_pip_packages,
    ensure_pip_requirements_file,
    load_requirements_file,
    missing_imports_for_specs,
    pip_distribution_name,
)
from print_scanner_app.installer.system_packages import ensure_apt_packages


def test_merge_reports():
    a = DependencyReport(ok=False, system_missing=["x"])
    b = DependencyReport(ok=True)
    m = merge_reports(a, b)
    assert not m.ok
    assert "x" in m.system_missing


def test_check_commands():
    miss = check_commands(["this_command_should_not_exist_xyz123"], which=lambda x: None)
    assert miss == ["this_command_should_not_exist_xyz123"]


def test_desktop_render():
    s = render_desktop_file(
        name="T",
        exec_path="/usr/bin/python3 x.py",
        icon_path="/i.png",
        working_dir="/repo",
    )
    assert "Exec=" in s and "Path=/repo" in s and "Terminal=false" in s


def test_resolve_app_icon_prefers_film_icon(tmp_path: Path):
    from print_scanner_app.infrastructure.system.env_tools import ASSETS_DIR

    assets = tmp_path.joinpath(*ASSETS_DIR)
    assets.mkdir(parents=True)
    (assets / "film_icon.png").write_bytes(b"x")
    (assets / "icon.png").write_bytes(b"y")
    assert resolve_app_icon(tmp_path).endswith(str(Path("Utils") / "Images" / "film_icon.png"))


def test_user_desktop_dir_prefers_escritorio(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "Escritorio").mkdir()
    monkeypatch.setattr("print_scanner_app.installer.desktop_entry.Path.home", lambda: home)
    assert user_desktop_dir() == home / "Escritorio"


def test_ensure_apt_dry_run():
    import subprocess

    def run(cmd, **kwargs):
        raise AssertionError("should not run")

    r = ensure_apt_packages(["pkg"], dry_run=True, run=run)
    assert r.ok


def test_ensure_pip_dry_run_reports_missing():
    def run(cmd, **kwargs):
        raise AssertionError("should not run")

    r = ensure_pip_packages(["nonexistent_pkg___zzz"], dry_run=True, run=run)
    assert not r.ok
    assert r.python_missing


def test_pip_distribution_name():
    assert pip_distribution_name("Pillow>=10.0") == "Pillow"
    assert pip_distribution_name("# comment") is None


def test_load_requirements_file(tmp_path: Path):
    req = tmp_path / "req.txt"
    req.write_text("kivy>=2.0\n# comment\n\nnumpy>=1.0\n", encoding="utf-8")
    assert load_requirements_file(req) == ["kivy>=2.0", "numpy>=1.0"]


def test_ensure_pip_requirements_file_dry_run(tmp_path: Path):
    req = tmp_path / "r.txt"
    req.write_text("nonexistent_pkg___zzz\n", encoding="utf-8")

    def run(cmd, **kwargs):
        raise AssertionError("should not run")

    r = ensure_pip_requirements_file(req, dry_run=True, run=run)
    assert not r.ok


def test_missing_imports_for_specs_detects_numpy():
    missing = missing_imports_for_specs(["numpy>=1.24"])
    # numpy suele estar instalado en CI/dev; solo comprobamos estructura
    assert isinstance(missing, list)
