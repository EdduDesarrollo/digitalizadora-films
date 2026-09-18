import subprocess

import pytest

from print_scanner_app.infrastructure.system import usb_tools


def test_usbreset_command_prefers_fixed_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools.os.path, "isfile", lambda p: str(p) == "/usr/bin/usbreset")
    assert usb_tools.usbreset_command() == "/usr/bin/usbreset"


def test_usbreset_command_falls_back_to_which(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools.shutil, "which", lambda name: "/opt/bin/usbreset" if name == "usbreset" else None)
    monkeypatch.setattr(usb_tools.os.path, "isfile", lambda p: False)
    assert usb_tools.usbreset_command() == "/opt/bin/usbreset"


def test_usbreset_command_none_when_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools.shutil, "which", lambda name: None)
    monkeypatch.setattr(usb_tools.os.path, "isfile", lambda p: False)
    assert usb_tools.usbreset_command() is None


def test_execute_usbreset_file_not_found_from_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/fake/usbreset")

    def run(cmd, **kwargs):
        raise FileNotFoundError()

    ok, code, out, err = usb_tools.execute_usbreset("001/002", run=run)
    assert not ok and code == -1 and "no encontrado" in err


def test_execute_usbreset_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/fake/usbreset")

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    ok, code, out, err = usb_tools.execute_usbreset("001/002", run=run)
    assert not ok and code == -124 and "timeout" in err


def test_list_usb_devices_no_binary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: None)
    assert usb_tools.list_usb_devices_by_keywords(["cam"]) == []


def test_list_usb_devices_nonzero_rc_empty_stdout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/x")

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "err")

    assert usb_tools.list_usb_devices_by_keywords(["x"], run=run) == []


def test_list_usb_devices_nonzero_rc_with_stdout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/x")
    out = "  Number 002/007 ID xx Canon Camera\n"

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, out, "")

    devs = usb_tools.list_usb_devices_by_keywords(["canon"], run=run)
    assert devs and devs[0][0] == "002/007"


def test_reset_usb_bad_address():
    assert not usb_tools.reset_usb_address("not-usb")


def test_default_run_invokes_subprocess_run(monkeypatch: pytest.MonkeyPatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(usb_tools.subprocess, "run", fake_run)
    r = usb_tools._default_run(("x", "y"))
    assert seen == [["x", "y"]]
    assert r.returncode == 0


def test_reset_usb_address_parses_and_calls_execute(monkeypatch: pytest.MonkeyPatch):
    seen = []

    def ex(path, **kwargs):
        seen.append(path)
        return True, 0, "", ""

    monkeypatch.setattr(usb_tools, "execute_usbreset", ex)
    assert usb_tools.reset_usb_address("usb:1,2") is True
    assert seen == ["001/002"]


def test_execute_usbreset_no_cmd(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: None)
    ok, code, out, err = usb_tools.execute_usbreset("001/002")
    assert not ok and code == -1


def test_list_devices_subprocess_error(monkeypatch: pytest.MonkeyPatch):
    def boom(cmd, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/x")
    assert usb_tools.list_usb_devices_by_keywords(["cam"], run=boom) == []


def test_reset_camara_impresora(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(usb_tools, "list_usb_devices_by_keywords", lambda *a, **k: [("001/002", "Canon")])
    monkeypatch.setattr(
        usb_tools,
        "execute_usbreset",
        lambda *a, **k: (True, 0, "", ""),
    )
    assert usb_tools.reset_usb_camara_e_impresora() >= 1
