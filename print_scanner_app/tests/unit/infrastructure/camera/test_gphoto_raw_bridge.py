from pathlib import Path

import pytest

from print_scanner_app.infrastructure.camera.gphoto_raw_bridge import GPhotoCameraRawAdapter


def test_adapter_find_save_delete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.gphoto_raw_bridge.find_raw_on_camera",
        lambda *a, **k: ("/store", "X.CR3"),
    )

    class CF:
        def save(self, p: str):
            Path(p).write_bytes(b"RAW")

    class GP:
        GP_FILE_TYPE_NORMAL = 0

        def CameraFile(self):
            return CF()

    class Cam:
        def file_get(self, folder, name, t, cf):
            pass

        def file_delete(self, folder, name):
            self.deleted = (folder, name)

    gp = GP()
    cam = Cam()
    adapter = GPhotoCameraRawAdapter(cam, gp)

    f, n = adapter.find_raw("X.CR3")
    assert f == "/store" and n == "X.CR3"

    dest = tmp_path / "out.cr3"
    adapter.save_raw_to("/", "X.CR3", dest)
    assert dest.read_bytes() == b"RAW"
    adapter.delete_raw("/", "X.CR3")
    assert cam.deleted == ("/", "X.CR3")


def test_save_raw_to_sets_mtime_to_download_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.gphoto_raw_bridge.find_raw_on_camera",
        lambda *a, **k: ("/store", "X.CR3"),
    )
    fixed = 1_700_000_000.0
    monkeypatch.setattr("print_scanner_app.infrastructure.camera.gphoto_raw_bridge.time.time", lambda: fixed)

    class CF:
        def save(self, p: str):
            Path(p).write_bytes(b"RAW")

    class GP:
        GP_FILE_TYPE_NORMAL = 0

        def CameraFile(self):
            return CF()

    class Cam:
        def file_get(self, folder, name, t, cf):
            pass

        def file_delete(self, folder, name):
            pass

    adapter = GPhotoCameraRawAdapter(Cam(), GP())
    dest = tmp_path / "t.cr3"
    adapter.save_raw_to("/", "X.CR3", dest)
    assert dest.stat().st_mtime == pytest.approx(fixed)


def test_save_raw_to_releases_camera_file_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import gc as py_gc
    import weakref

    monkeypatch.setattr(
        "print_scanner_app.infrastructure.camera.gphoto_raw_bridge.find_raw_on_camera",
        lambda *a, **k: ("/store", "X.CR3"),
    )
    refs: list = []

    class CF:
        def save(self, p: str):
            Path(p).write_bytes(b"RAW")

    class GP:
        GP_FILE_TYPE_NORMAL = 0

        def CameraFile(self):
            obj = CF()
            refs.append(weakref.ref(obj))
            return obj

    class Cam:
        def file_get(self, folder, name, t, cf):
            pass

    adapter = GPhotoCameraRawAdapter(Cam(), GP())
    adapter.save_raw_to("/", "X.CR3", tmp_path / "r.cr3")
    py_gc.collect()
    assert refs[0]() is None
