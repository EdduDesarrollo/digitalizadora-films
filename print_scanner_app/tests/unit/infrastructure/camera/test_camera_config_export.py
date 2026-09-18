from __future__ import annotations

from print_scanner_app.infrastructure.camera.camera_config_export import (
    export_camera_config_tree,
    is_retryable_camera_io_error,
    merge_camera_config,
)


class _GpErr(Exception):
    def __init__(self, code: int | None = None, msg: str = ""):
        super().__init__(msg)
        self.code = code


class _Child:
    def __init__(self, name: str, value=None, children=None):
        self._name = name
        self._value = value
        self._children = children or []

    def get_name(self):
        return self._name

    def get_value(self):
        if self._value is _RAISE:
            raise _GpErr(-110, "I/O in progress")
        return self._value

    def count_children(self):
        return len(self._children)

    def get_child(self, i):
        return self._children[i]


_RAISE = object()


class _Cam:
    def __init__(self, root):
        self._root = root

    def get_config(self):
        return self._root


def test_merge_camera_config():
    assert merge_camera_config({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {"a": 1, "b": 3, "c": 4}
    assert merge_camera_config(None, {"x": 1}) == {"x": 1}


def test_export_camera_config_tree_walk():
    root = _Child(
        "main",
        children=[
            _Child("imgsettings", children=[_Child("imageformat", "RAW")]),
            _Child("other", 42),
        ],
    )
    out = export_camera_config_tree(_Cam(root), _GpErr)
    assert out.get("main/imgsettings/imageformat") == "RAW"
    assert out.get("main/other") == 42


def test_is_retryable_camera_io_error():
    assert is_retryable_camera_io_error(_GpErr(-110, "I/O"))
    assert is_retryable_camera_io_error(_GpErr(-53, "Could not claim"))
    assert not is_retryable_camera_io_error(ValueError("other"))
