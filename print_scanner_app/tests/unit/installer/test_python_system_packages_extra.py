import subprocess

import pytest

from print_scanner_app.installer import install as install_mod
from print_scanner_app.installer.dependency_check import DependencyReport
from print_scanner_app.installer.python_packages import ensure_pip_packages, import_available
from print_scanner_app.installer.system_packages import ensure_apt_packages, repair_apt


def test_ensure_pip_install_failure(monkeypatch: pytest.MonkeyPatch):
    def bad_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "pip error")

    r = ensure_pip_packages(["nonexistent_pkg___zzz"], dry_run=False, run=bad_run)
    assert not r.ok


def test_ensure_apt_failure(monkeypatch: pytest.MonkeyPatch):
    def bad_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "apt error")

    r = ensure_apt_packages(["x"], dry_run=False, run=bad_run)
    assert not r.ok


def test_ensure_apt_when_apt_binary_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.installer.system_packages.check_commands",
        lambda cmds: ["apt"],
    )
    r = ensure_apt_packages(["p"], dry_run=False, run=lambda *a, **k: None)
    assert r.ok is False


def test_repair_apt_dry_run():
    r = repair_apt(dry_run=True, run=lambda *a, **k: None)
    assert r.ok


def test_main_skips_pip_when_apt_fails(monkeypatch: pytest.MonkeyPatch, tmp_path):
    root = tmp_path / "repo"
    (root / "print_scanner_app" / "logs").mkdir(parents=True)
    monkeypatch.setattr(install_mod, "_ROOT", root)
    monkeypatch.setattr(install_mod, "ensure_apt_updated", lambda *a, **k: DependencyReport(ok=True))
    monkeypatch.setattr(install_mod, "repair_apt", lambda *a, **k: DependencyReport(ok=True))
    monkeypatch.setattr(
        install_mod,
        "ensure_printer_permissions",
        lambda *a, **k: DependencyReport(ok=True),
    )
    monkeypatch.setattr(
        install_mod,
        "ensure_apt_packages",
        lambda *a, **k: DependencyReport(ok=False, system_missing=["x"]),
    )
    pip_called = {"n": 0}

    def pip(*a, **k):
        pip_called["n"] += 1
        return DependencyReport(ok=True)

    monkeypatch.setattr(install_mod, "ensure_pip_requirements_file", pip)
    assert install_mod.main([]) == 2
    assert pip_called["n"] == 0


def test_import_available_false_for_missing():
    assert import_available("modulo_inexistente_xyz_12345") is False
