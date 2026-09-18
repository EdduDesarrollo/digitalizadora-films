from print_scanner_app.installer.printer_permissions import ensure_printer_permissions


def test_ensure_printer_permissions_dry_run():
    r = ensure_printer_permissions(dry_run=True, run=lambda *a, **k: None)
    assert r.ok
    assert any("udev" in n for n in r.notes)
