"""Cobertura de `install.main()` y `setup_logging` (TASK-I7)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from print_scanner_app.installer.dependency_check import DependencyReport
from print_scanner_app.installer import install as install_mod


@pytest.fixture
def fake_repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "print_scanner_app" / "logs").mkdir(parents=True)
    return root


def test_setup_logging_creates_file(tmp_path: Path):
    log_f = tmp_path / "install.log"
    log = install_mod.setup_logging(log_f, dry_run=True)
    assert isinstance(log, logging.Logger)
    assert log_f.is_file()


@pytest.fixture(autouse=True)
def _mock_apt_steps(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_updated",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "repair_apt",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_printer_permissions",
        lambda *a, **k: DependencyReport(ok=True),
    )


def test_main_dry_run_ok(monkeypatch: pytest.MonkeyPatch, fake_repo_root: Path):
    monkeypatch.setattr(install_mod, "_ROOT", fake_repo_root)
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_packages",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_pip_requirements_file",
        lambda *a, **k: DependencyReport(ok=True),
    )
    assert install_mod.main(["--dry-run"]) == 0


def test_main_returns_2_when_dependency_fail(monkeypatch: pytest.MonkeyPatch, fake_repo_root: Path):
    monkeypatch.setattr(install_mod, "_ROOT", fake_repo_root)
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_packages",
        lambda *a, **k: DependencyReport(ok=False, notes=["apt"]),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_pip_requirements_file",
        lambda *a, **k: DependencyReport(ok=True),
    )
    assert install_mod.main(["--dry-run"]) == 2


def test_main_writes_desktop_when_not_dry_run(monkeypatch: pytest.MonkeyPatch, fake_repo_root: Path, tmp_path: Path):
    (fake_repo_root / "print_scanner_app" / "app").mkdir(parents=True, exist_ok=True)
    (fake_repo_root / "print_scanner_app" / "app" / "main.py").write_text("# app\n", encoding="utf-8")
    monkeypatch.setattr(install_mod, "_ROOT", fake_repo_root)
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_packages",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_pip_requirements_file",
        lambda *a, **k: DependencyReport(ok=True),
    )
    desk = tmp_path / "Escritorio"
    desk.mkdir()
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    monkeypatch.setattr(
        "print_scanner_app.installer.desktop_entry.user_desktop_dir",
        lambda: desk,
    )
    monkeypatch.setattr(
        "print_scanner_app.installer.desktop_entry.user_applications_dir",
        lambda: apps,
    )

    assert install_mod.main([]) == 0
    assert (desk / "print_scanner.desktop").is_file()
    assert (apps / "print-scanner-app.desktop").is_file()
    assert "Name=Print Scanner" in (desk / "print_scanner.desktop").read_text(encoding="utf-8")


def test_main_returns_3_when_desktop_write_fails(monkeypatch: pytest.MonkeyPatch, fake_repo_root: Path):
    monkeypatch.setattr(install_mod, "_ROOT", fake_repo_root)
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_packages",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_pip_requirements_file",
        lambda *a, **k: DependencyReport(ok=True),
    )

    def boom(**_k):
        raise OSError("no write")

    monkeypatch.setattr(install_mod, "install_launcher", boom)
    assert install_mod.main([]) == 3


def test_desktop_only_flag(monkeypatch: pytest.MonkeyPatch, fake_repo_root: Path, tmp_path: Path):
    (fake_repo_root / "print_scanner_app" / "app").mkdir(parents=True, exist_ok=True)
    (fake_repo_root / "print_scanner_app" / "app" / "main.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(install_mod, "_ROOT", fake_repo_root)
    desk = tmp_path / "Desktop"
    desk.mkdir(parents=True)
    apps = tmp_path / "apps"
    apps.mkdir()
    monkeypatch.setattr(
        "print_scanner_app.installer.desktop_entry.user_desktop_dir",
        lambda: desk,
    )
    monkeypatch.setattr(
        "print_scanner_app.installer.desktop_entry.user_applications_dir",
        lambda: apps,
    )
    assert install_mod.main(["--desktop-only"]) == 0
    assert (desk / "print_scanner.desktop").is_file()


def test_default_run_invokes_subprocess(monkeypatch: pytest.MonkeyPatch):
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("print_scanner_app.installer.process_run.subprocess.run", mock_run)
    install_mod._default_run(["true"])
    mock_run.assert_called_once()
