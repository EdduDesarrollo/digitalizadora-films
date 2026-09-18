"""Tests del helper de umbralización (máscara gray > ug)."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image

from print_scanner_app.ui.dialogs.umbralizacion_dialog import _threshold_rgb_bytes


def test_threshold_rgb_bytes_splits_on_umbral():
    arr = np.zeros((20, 30), dtype=np.uint8)
    arr[:, :10] = 0
    arr[:, 10:] = 255
    img = Image.fromarray(arr, mode="L")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    out = _threshold_rgb_bytes(buf.getvalue(), 128)
    assert out is not None
    fb, w, h = out
    assert (w, h) == (30, 20)
    rgb = np.frombuffer(fb, dtype=np.uint8).reshape(h, w, 3)
    assert int(rgb[:, :8, 0].max()) == 0
    assert int(rgb[:, 12:, 0].min()) == 255
