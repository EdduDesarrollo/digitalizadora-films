from unittest.mock import patch

from print_scanner_app.ui.textinput_paste import read_system_clipboard_text


def test_read_system_clipboard_xclip():
    with patch("shutil.which", return_value="/usr/bin/xclip"):
        with patch(
            "subprocess.run",
            return_value=type("R", (), {"returncode": 0, "stdout": "serial-abc\n"})(),
        ):
            assert read_system_clipboard_text().startswith("serial-abc")
