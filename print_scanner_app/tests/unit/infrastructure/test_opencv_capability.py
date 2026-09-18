import sys

import pytest


def test_linux_without_display_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    from print_scanner_app.infrastructure.debug.opencv_capability import (
        alignment_debug_unavailable_reason,
        alignment_debug_visual_available,
    )

    assert alignment_debug_unavailable_reason() is not None
    assert not alignment_debug_visual_available()
