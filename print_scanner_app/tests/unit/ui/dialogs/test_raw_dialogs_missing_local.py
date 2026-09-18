"""Tests del mensaje de popup RAW pendientes sin copia local (sin Kivy)."""

from print_scanner_app.ui.dialogs.raw_dialogs import RawDialogs


def test_format_missing_local_copy_lists_up_to_five():
    ids = [f"RAW-{i}.CR3" for i in range(7)]
    msg = RawDialogs.format_missing_local_copy_message(ids)
    assert "RAW-0.CR3" in msg
    assert "RAW-4.CR3" in msg
    assert "RAW-5.CR3" not in msg.split("… y")[0]
    assert "… y 2 más" in msg


def test_format_missing_local_copy_empty_ids_returns_body_only():
    msg = RawDialogs.format_missing_local_copy_message([])
    assert "Algunos archivos figuraban como pendientes" in msg
    assert "… y" not in msg
