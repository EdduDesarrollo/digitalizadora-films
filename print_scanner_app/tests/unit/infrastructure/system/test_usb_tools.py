import subprocess

from print_scanner_app.infrastructure.system import usb_tools


def test_parse_usbreset_list():
    stdout = """
  Number 001/032 ID 04a9:1234 Canon Digital Camera
  Number 002/001 ID abcd:ffff Some Printer POS
"""
    cams = usb_tools.parse_usbreset_list(stdout, ["canon", "camera"])
    assert cams and cams[0][0] == "001/032"


def test_execute_usbreset_mock(monkeypatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/fake/usbreset")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ok, code, out, err = usb_tools.execute_usbreset("001/032", run=fake_run)
    assert ok and code == 0


def test_list_devices_mock(monkeypatch):
    monkeypatch.setattr(usb_tools, "usbreset_command", lambda: "/x")

    def fake_run(cmd, **kwargs):
        out = "  Number 001/032 ID x Canon Camera\n"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    devs = usb_tools.list_usb_devices_by_keywords(["camera"], run=fake_run)
    assert devs[0][0] == "001/032"
