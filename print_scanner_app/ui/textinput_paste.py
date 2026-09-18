"""Ctrl+V en TextInput cuando Kivy usa clipboard dummy (Linux sin xclip en el provider)."""

from __future__ import annotations

import subprocess
from typing import Any


def read_system_clipboard_text() -> str:
    import shutil

    for cmd in (
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
        ["wl-paste", "--no-newline"],
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
        except Exception:  # noqa: BLE001
            continue
        if result.returncode == 0 and result.stdout:
            return result.stdout.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def enable_ctrl_v_paste(text_input: Any) -> None:
    """Permite pegar con Ctrl+V (y Ctrl+Shift+V) en un TextInput de Kivy."""
    original = text_input.keyboard_on_key_down

    def keyboard_on_key_down(window, keycode, text, modifiers):
        key, _keycode = keycode
        mods = {str(m).lower() for m in modifiers}
        ctrl = "ctrl" in mods or "meta" in mods or "control" in mods
        paste_key = (text or "").lower() == "v" or key in (118, 86)
        if ctrl and paste_key:
            clip = read_system_clipboard_text()
            if clip:
                line = clip.split("\n", 1)[0]
                ti = text_input
                start = ti.cursor_index()
                left = ti.text[:start]
                right = ti.text[start:]
                ti.text = left + line + right
                ti.cursor = (len(left) + len(line), 0)
            return True
        if original is not None:
            return original(window, keycode, text, modifiers)
        return False

    text_input.keyboard_on_key_down = keyboard_on_key_down
