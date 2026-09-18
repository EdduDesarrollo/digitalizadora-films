import subprocess

from print_scanner_app.infrastructure.camera.gphoto_client import GPhotoClient, gphoto_cli_usb_ports, list_camera_addresses


def test_cli_ports_parse():
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            "Canon EOS\nusb:001,025\n",
            "",
        )

    ports = gphoto_cli_usb_ports(run=run, timeout=1)
    assert ports == ["usb:001,025"]


def test_list_addresses_fallback_cli(monkeypatch):
    c = GPhotoClient(gp_module=None)
    monkeypatch.setattr(c, "autodetect", lambda: [])

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "  usb:002,010\n", "")

    addrs = list_camera_addresses(c, run=run)
    assert addrs == [("unknown", "usb:002,010")]
