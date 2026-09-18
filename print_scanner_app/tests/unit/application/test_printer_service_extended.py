"""Escenarios mockeados de `PrinterService`."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import print_scanner_app.application.services.printer_service as pr_svc
from print_scanner_app.application.services.printer_service import PrinterService


@pytest.fixture
def fake_escpos_module(monkeypatch: pytest.MonkeyPatch):
    inner = MagicMock()
    file_instance = MagicMock()
    file_instance._raw = MagicMock()
    inner.File = MagicMock(return_value=file_instance)
    fake = types.SimpleNamespace(printer=inner)
    monkeypatch.setitem(__import__("sys").modules, "escpos", fake)
    return inner


def test_connect_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_escpos_module):
    dev = tmp_path / "lp9"
    dev.write_text("x")
    monkeypatch.setattr(pr_svc, "first_lp_device", lambda: dev)

    assert PrinterService().connect(retries=pr_svc.RetryConfig(max_attempts=2, delay_seconds=0))
    fake_escpos_module.File.assert_called_once()


def test_connect_oserror_then_retry_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_escpos_module):
    dev = tmp_path / "lp9"
    dev.write_text("x")
    monkeypatch.setattr(pr_svc, "first_lp_device", lambda: dev)

    n = {"c": 0}

    def flaky_open(path):
        n["c"] += 1
        if n["c"] == 1:
            raise OSError("busy")
        m = MagicMock()
        m.reset = MagicMock()
        m._raw = MagicMock()
        return m

    monkeypatch.setattr(pr_svc.EscposClient, "open", staticmethod(flaky_open))

    ok = PrinterService().connect(retries=pr_svc.RetryConfig(max_attempts=3, delay_seconds=0))
    assert ok


def test_connect_gives_up_calls_usb_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dev = tmp_path / "lp0"
    dev.write_text("x")
    monkeypatch.setattr(pr_svc, "first_lp_device", lambda: dev)
    monkeypatch.setattr(pr_svc, "device_is_writable", lambda _p: True)

    monkeypatch.setattr(
        pr_svc.EscposClient,
        "open",
        staticmethod(lambda p: (_ for _ in ()).throw(OSError("fail"))),
    )
    reset = MagicMock()
    monkeypatch.setattr(pr_svc, "reset_usb_camara_e_impresora", reset)

    assert not PrinterService().connect(retries=pr_svc.RetryConfig(max_attempts=1, delay_seconds=0))
    reset.assert_called_once()


def test_move_film_retries_reconnect_then_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dev = tmp_path / "lp9"
    dev.write_text("x")
    monkeypatch.setattr(pr_svc, "first_lp_device", lambda: dev)
    monkeypatch.setattr(pr_svc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pr_svc, "reset_usb_camara_e_impresora", lambda: 1)

    calls = {"n": 0}

    class Client:
        def advance_pixels(self, px):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("busy")

        def reset(self):
            pass

        def _raw(self, _):
            pass

    monkeypatch.setattr(pr_svc.EscposClient, "open", staticmethod(lambda _p: Client()))
    svc = PrinterService()
    assert svc.connect(retries=pr_svc.RetryConfig(max_attempts=1, delay_seconds=0))
    assert svc.move_film(10, retries=pr_svc.RetryConfig(max_attempts=2, delay_seconds=0))


def test_send_image_retries_then_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dev = tmp_path / "lp9"
    dev.write_text("x")
    monkeypatch.setattr(pr_svc, "first_lp_device", lambda: dev)
    monkeypatch.setattr(pr_svc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pr_svc, "reset_usb_camara_e_impresora", lambda: 1)

    calls = {"n": 0}

    class Client:
        def advance_pixels(self, px):
            pass

        def send_image(self, img):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("busy")

        def reset(self):
            pass

        def _raw(self, _):
            pass

    monkeypatch.setattr(pr_svc.EscposClient, "open", staticmethod(lambda _p: Client()))
    svc = PrinterService()
    assert svc.connect(retries=pr_svc.RetryConfig(max_attempts=1, delay_seconds=0))
    assert svc.send_image("img", retries=pr_svc.RetryConfig(max_attempts=2, delay_seconds=0))
