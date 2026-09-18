import pytest

import os

from print_scanner_app.infrastructure.printer.printer_device import (
    describe_device_permissions,
    find_usb_lp_devices,
    first_lp_device,
    lp_permission_hint,
)


def test_find_lp_glob_no_crash():
    find_usb_lp_devices("/dev/nonexistent_lp_pattern_*")


def test_first_lp_device_returns_first_sorted(tmp_path, monkeypatch: pytest.MonkeyPatch):
    a = tmp_path / "lp1"
    b = tmp_path / "lp0"
    a.write_text("x")
    b.write_text("x")
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.printer.printer_device.glob.glob",
        lambda pattern: [str(b), str(a)],
    )
    assert first_lp_device() == b


def test_first_lp_device_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.printer.printer_device.glob.glob",
        lambda pattern: [],
    )
    assert first_lp_device() is None


def test_first_lp_device_prefers_writable(tmp_path, monkeypatch: pytest.MonkeyPatch):
    ro = tmp_path / "lp0"
    rw = tmp_path / "lp1"
    ro.write_bytes(b"")
    rw.write_bytes(b"")
    os.chmod(ro, 0o000)
    os.chmod(rw, 0o600)
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.printer.printer_device.glob.glob",
        lambda pattern: [str(ro), str(rw)],
    )
    assert first_lp_device() == rw


def test_lp_permission_hint_contains_dev():
    assert "chmod" in lp_permission_hint("/dev/usb/lp2")


def test_describe_device_permissions_missing():
    assert "no existe" in describe_device_permissions("/dev/usb/lp_no_existe_xyz")
