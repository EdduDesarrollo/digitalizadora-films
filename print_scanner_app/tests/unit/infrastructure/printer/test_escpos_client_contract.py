import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from print_scanner_app.infrastructure.printer.escpos_client import EscposClient


def test_escpos_requires_init():
    c = EscposClient()
    with pytest.raises(RuntimeError):
        c.reset()


def test_escpos_raw_without_printer_raises():
    c = EscposClient()
    with pytest.raises(RuntimeError, match="no inicializada"):
        c._raw(b"\x00")


def test_escpos_open_and_reset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    inner = MagicMock()
    inst = MagicMock()
    inst._raw = MagicMock()
    inner.File = MagicMock(return_value=inst)
    fake = types.SimpleNamespace(printer=inner)
    monkeypatch.setitem(sys.modules, "escpos", fake)

    dev = tmp_path / "lp9"
    dev.write_text("x")
    c = EscposClient.open(dev)
    c.reset()

    inner.File.assert_called_once_with(str(dev))
    inst._raw.assert_called_once_with(b"\x1b@")


def test_escpos_advance_pixels_uses_image_and_raw(monkeypatch: pytest.MonkeyPatch):
    inst = MagicMock()
    c = EscposClient(_printer=inst)
    c.advance_pixels(12)
    inst.image.assert_called_once()
    inst._raw.assert_called_once_with(b"\n")


def test_escpos_send_image_delegates():
    inst = MagicMock()
    c = EscposClient(_printer=inst)
    c.send_image("img")
    inst.image.assert_called_once_with("img")
