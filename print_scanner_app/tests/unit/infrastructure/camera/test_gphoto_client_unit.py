"""Tests unitarios de `gphoto_client` con doubles (sin hardware)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from print_scanner_app.domain.policies.retry_policy import RetryConfig
from print_scanner_app.infrastructure.camera import gphoto_client as gc


def test_gphoto_client_autodetect_with_fake_gp():
    class FakeGP:
        class Camera:
            @staticmethod
            def autodetect():
                return [("M", "usb:1,2")]

    c = gc.GPhotoClient(gp_module=FakeGP())
    assert c.autodetect() == [("M", "usb:1,2")]


def test_init_camera_first_try_ok(monkeypatch: pytest.MonkeyPatch):
    class Cam:
        def init(self):
            pass

        def set_port_info(self, x):
            pass

    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            return Cam()

        def PortInfoList(self):
            return PIL()

    gp = GP()
    cam = gc.init_camera_at_address(
        gp,
        "usb:1,1",
        retries=RetryConfig(max_attempts=2, delay_seconds=0),
        sleep_fn=lambda _: None,
        reset_on_fail=False,
    )
    assert isinstance(cam, Cam)


def test_get_camera_serial_direct_child():
    class Child:
        def get_value(self):
            return "  SN99  "

    class Cfg:
        def get_child_by_name(self, name):
            if name == "serialnumber":
                return Child()
            raise KeyError()

    class Cam:
        def get_config(self):
            return Cfg()

    assert gc.get_camera_serial(object(), Cam()) == "SN99"


def test_find_raw_in_root():
    class FL:
        def count(self):
            return 1

        def get_name(self, j):
            return "P.CR3"

    class Cam:
        def folder_list_files(self, p):
            return FL()

        def folder_list_folders(self, p):
            raise RuntimeError("no sub")

    f, n = gc.find_raw_on_camera(Cam(), None, "P.CR3", "/")
    assert f == "/" and n == "P.CR3"


def test_is_timeout_via_string():
    class GP:
        pass

    assert gc._is_timeout_err(RuntimeError("foo -10 bar"), GP())


def test_is_timeout_via_gphoto2error_code():
    class GP:
        class GPhoto2Error(Exception):
            pass

    err = GP.GPhoto2Error("x")
    err.code = -10
    assert gc._is_timeout_err(err, GP())


def test_gphoto_cli_usb_ports_parses_and_dedups():
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            "usb:001,002 y usb:003,004\nUSB:005,006",
            "",
        )

    ports = gc.gphoto_cli_usb_ports(run=run)
    assert ports == ["usb:001,002", "usb:003,004", "usb:005,006"]


def test_gphoto_cli_usb_ports_errors_return_empty():
    def fnf(cmd, **kwargs):
        raise FileNotFoundError()

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    def bad_rc(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "usb:1,1", "")

    assert gc.gphoto_cli_usb_ports(run=fnf) == []
    assert gc.gphoto_cli_usb_ports(run=timeout) == []
    assert gc.gphoto_cli_usb_ports(run=bad_rc) == []


def test_list_camera_addresses_dedup_autodetect_only():
    class FakeGP:
        class Camera:
            @staticmethod
            def autodetect():
                return [("A", "usb:1,1"), ("B", "usb:1,1")]

    def run(cmd, **kwargs):
        raise AssertionError("CLI solo si autodetect vacío")

    client = gc.GPhotoClient(gp_module=FakeGP())
    assert gc.list_camera_addresses(client, run=run) == [("A", "usb:1,1")]


def test_list_camera_addresses_cli_when_autodetect_empty():
    class FakeGP:
        class Camera:
            @staticmethod
            def autodetect():
                return []

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "line usb:9,9 end", "")

    client = gc.GPhotoClient(gp_module=FakeGP())
    assert gc.list_camera_addresses(client, run=run) == [("unknown", "usb:9,9")]


def test_list_camera_addresses_only_autodetect():
    class FakeGP:
        class Camera:
            @staticmethod
            def autodetect():
                return [("X", "usb:2,2")]

    def run(cmd, **kwargs):
        raise AssertionError("CLI no debe llamarse si hay autodetect")

    client = gc.GPhotoClient(gp_module=FakeGP())
    assert gc.list_camera_addresses(client, run=run) == [("X", "usb:2,2")]


def test_init_camera_timeout_then_ok():
    class Cam:
        _n = 0

        def init(self):
            Cam._n += 1
            if Cam._n < 2:
                raise RuntimeError("gphoto2 -10 timeout")

        def set_port_info(self, x):
            pass

    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            return Cam()

        def PortInfoList(self):
            return PIL()

    gp = GP()
    cam = gc.init_camera_at_address(
        gp,
        "usb:1,1",
        retries=RetryConfig(max_attempts=3, delay_seconds=0),
        sleep_fn=lambda _: None,
        reset_on_fail=False,
    )
    assert isinstance(cam, Cam)
    assert Cam._n == 2


def test_init_camera_non_timeout_raises():
    class Cam:
        def init(self):
            raise RuntimeError("lens blocked")

        def set_port_info(self, x):
            pass

    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            return Cam()

        def PortInfoList(self):
            return PIL()

    gp = GP()
    with pytest.raises(RuntimeError, match="lens"):
        gc.init_camera_at_address(
            gp,
            "usb:1,1",
            retries=RetryConfig(max_attempts=2, delay_seconds=0),
            sleep_fn=lambda _: None,
            reset_on_fail=False,
        )


def test_init_camera_exhausted_then_reset_usb(monkeypatch: pytest.MonkeyPatch):
    class Cam:
        _n = 0

        def init(self):
            Cam._n += 1
            if Cam._n < 3:
                raise RuntimeError("-10")

        def set_port_info(self, x):
            pass

    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            return Cam()

        def PortInfoList(self):
            return PIL()

    gp = GP()
    monkeypatch.setattr(gc, "reset_usb_address", lambda addr: True)
    cam = gc.init_camera_at_address(
        gp,
        "usb:1,1",
        retries=RetryConfig(max_attempts=2, delay_seconds=0),
        sleep_fn=lambda _: None,
        reset_on_fail=True,
    )
    assert isinstance(cam, Cam)
    assert Cam._n >= 3


def test_init_camera_exhausted_no_reset_raises_last(monkeypatch: pytest.MonkeyPatch):
    class Cam:
        def init(self):
            raise RuntimeError("err -10")

        def set_port_info(self, x):
            pass

    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            return Cam()

        def PortInfoList(self):
            return PIL()

    gp = GP()
    monkeypatch.setattr(gc, "reset_usb_address", lambda addr: False)
    with pytest.raises(RuntimeError, match="-10"):
        gc.init_camera_at_address(
            gp,
            "usb:1,1",
            retries=RetryConfig(max_attempts=1, delay_seconds=0),
            sleep_fn=lambda _: None,
            reset_on_fail=True,
        )


def test_get_camera_serial_walk_tree():
    class Leaf:
        def get_name(self):
            return "serialnumber"

        def get_value(self):
            return "  TREE42 "

        def count_children(self):
            return 0

        def get_child(self, i):
            raise IndexError

    class Root:
        def get_name(self):
            return "root"

        def get_value(self):
            return None

        def count_children(self):
            return 1

        def get_child(self, i):
            return Leaf()

    class Cam:
        def __init__(self):
            self._n = 0

        def get_config(self):
            self._n += 1
            if self._n == 1:
                raise RuntimeError("first fails")
            return Root()

    assert gc.get_camera_serial(object(), Cam()) == "TREE42"


def test_find_raw_latest_when_no_name():
    class FL:
        def count(self):
            return 2

        def get_name(self, j):
            return ("A.CR3", "Z.CR3")[j]

    class Cam:
        def folder_list_files(self, p):
            return FL()

        def folder_list_folders(self, p):
            raise RuntimeError("leaf")

    f, n = gc.find_raw_on_camera(Cam(), None, "", "/")
    assert f == "/" and n == "Z.CR3"


def test_find_raw_cache_folder_shortcut():
    cache = ["/cache"]

    class FLCache:
        def count(self):
            return 1

        def get_name(self, j):
            return "X.CR3"

    class FLRoot:
        def count(self):
            return 0

        def get_name(self, j):
            raise IndexError

    class Cam:
        def folder_list_files(self, p):
            if p == "/cache":
                return FLCache()
            return FLRoot()

        def folder_list_folders(self, p):
            raise RuntimeError("no")

    f, n = gc.find_raw_on_camera(Cam(), None, "X.CR3", "/", last_found_folder=cache)
    assert f == "/cache" and n == "X.CR3"


def test_find_raw_recurses_subfolder():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            if p == "/":
                return FL([])
            if p == "/DCIM":
                return FL(["R.CR3"])
            return FL([])

        def folder_list_folders(self, p):
            if p == "/":
                return FL(["DCIM"])
            return FL([])

    f, n = gc.find_raw_on_camera(Cam(), None, "R.CR3", "/")
    assert f == "/DCIM" and n == "R.CR3"


def test_init_camera_zero_attempts_raises_sin_resultado():
    class PIL:
        def load(self):
            pass

        def lookup_path(self, addr):
            return 0

        def __getitem__(self, i):
            return MagicMock()

    class GP:
        def Camera(self):
            raise AssertionError("no camera")

        def PortInfoList(self):
            return PIL()

    with pytest.raises(RuntimeError, match="sin resultado"):
        gc.init_camera_at_address(
            GP(),
            "usb:1,1",
            retries=RetryConfig(max_attempts=0, delay_seconds=0),
            sleep_fn=lambda _: None,
            reset_on_fail=False,
        )


def test_get_camera_serial_direct_none_value():
    class Child:
        def get_value(self):
            return None

    class Cfg:
        def get_child_by_name(self, name):
            return Child()

    class Cam:
        def get_config(self):
            return Cfg()

    assert gc.get_camera_serial(object(), Cam()) is None


def test_get_camera_serial_whitespace_only_becomes_none():
    class Child:
        def get_value(self):
            return "   \t  "

    class Cfg:
        def get_child_by_name(self, name):
            return Child()

    class Cam:
        def get_config(self):
            return Cfg()

    assert gc.get_camera_serial(object(), Cam()) is None


def test_get_camera_serial_walk_returns_none_when_unreadable():
    class Cam:
        def get_config(self):
            raise RuntimeError("always")

    assert gc.get_camera_serial(object(), Cam()) is None


def test_get_camera_serial_walk_skips_node_when_count_children_fails():
    class Opaque:
        def get_name(self):
            return "opaque"

        def get_value(self):
            return None

        def count_children(self):
            raise RuntimeError("no children")

        def get_child(self, i):
            raise IndexError

    class Root:
        def get_name(self):
            return "root"

        def get_value(self):
            return None

        def count_children(self):
            return 1

        def get_child(self, i):
            return Opaque()

    class Cam:
        _n = 0

        def get_config(self):
            self._n += 1
            if self._n == 1:
                raise RuntimeError("no direct")
            return Root()

    assert gc.get_camera_serial(object(), Cam()) is None


def test_buscar_en_carpeta_jpg_ext():
    class FL:
        def count(self):
            return 1

        def get_name(self, j):
            return "pic.JPG"

    class Cam:
        def folder_list_files(self, p):
            return FL()

    folder, name = gc._buscar_en_carpeta(Cam(), "/", None, False)
    assert folder == "/" and name == "pic.JPG"


def test_buscar_en_carpeta_list_files_raises():
    class Cam:
        def folder_list_files(self, p):
            raise OSError("e")

    assert gc._buscar_en_carpeta(Cam(), "/", "x.cr3", True) == (None, None)


def test_find_raw_nested_subfolder_returns_via_recursion():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            norm = p.replace("\\", "/")
            if norm == "/DCIM/SUB":
                return FL(["deep.CR3"])
            return FL([])

        def folder_list_folders(self, p):
            norm = p.replace("\\", "/")
            if norm == "/":
                return FL(["DCIM"])
            if norm == "/DCIM":
                return FL(["SUB"])
            return FL([])

    f, n = gc.find_raw_on_camera(Cam(), None, "deep.CR3", "/")
    assert f == "/DCIM/SUB" and n == "deep.CR3"


def test_find_raw_not_found_returns_none():
    class Empty:
        def count(self):
            return 0

        def get_name(self, j):
            raise IndexError

    class Cam:
        def folder_list_files(self, p):
            return Empty()

        def folder_list_folders(self, p):
            return Empty()

    assert gc.find_raw_on_camera(Cam(), None, "missing.CR3", "/") == (None, None)


def test_trigger_capture_and_get_raw_name():
    class FP:
        name = "R000123.CR3"

    class Cam:
        def capture(self, mode):
            return FP()

    class GP:
        GP_CAPTURE_IMAGE = object()

    assert gc.trigger_capture_and_get_raw_name(Cam(), GP()) == "R000123.CR3"


def test_jpg_basename_to_cr3_name():
    assert gc.jpg_basename_to_cr3_name("capt0000.jpg") == "capt0000.CR3"
    assert gc.jpg_basename_to_cr3_name("CAPT0001.JPG") == "CAPT0001.CR3"


def test_find_raw_on_camera_accepts_jpg_pendiente():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            if p == "/":
                return FL(["capt0000.CR3", "capt0000.jpg"])
            return FL([])

        def folder_list_folders(self, p):
            return FL([])

    f, n = gc.find_raw_on_camera(Cam(), None, "capt0000.jpg", "/")
    assert f == "/" and n == "capt0000.CR3"


def test_trigger_capture_jpg_resolves_to_cr3():
    """JPG reportado → CR3 derivado sin listar tarjeta."""

    class FP:
        name = "capt0002.jpg"

    class Cam:
        def capture(self, mode):
            return FP()

        def folder_list_files(self, p):
            raise AssertionError("no debe listar carpeta en camino feliz")

        def folder_list_folders(self, p):
            raise AssertionError("no debe listar carpetas en camino feliz")

    class GP:
        GP_CAPTURE_IMAGE = object()

    assert gc.trigger_capture_and_get_raw_name(Cam(), GP()) == "capt0002.CR3"


def test_trigger_capture_jpg_derives_cr3_when_not_yet_on_card():
    class FP:
        name = "capt0003.jpg"

    class Cam:
        def capture(self, mode):
            return FP()

        def folder_list_files(self, p):
            raise AssertionError("no debe listar en camino feliz con JPG reportado")

        def folder_list_folders(self, p):
            raise AssertionError("no debe listar en camino feliz con JPG reportado")

    class GP:
        GP_CAPTURE_IMAGE = object()

    assert gc.trigger_capture_and_get_raw_name(Cam(), GP()) == "capt0003.CR3"


def test_trigger_capture_and_get_raw_name_none_when_empty():
    class FP:
        name = "  "

    class Empty:
        def count(self):
            return 0

        def get_name(self, j):
            raise IndexError

    class Cam:
        def capture(self, mode):
            return FP()

        def folder_list_files(self, p):
            return Empty()

        def folder_list_folders(self, p):
            return Empty()

    class GP:
        GP_CAPTURE_IMAGE = object()

    assert gc.trigger_capture_and_get_raw_name(Cam(), GP()) is None


def test_trigger_capture_empty_name_fallback_find_latest():
    """Sin nombre reportado: un fallback acotado via find_latest."""

    class FP:
        name = ""

    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def capture(self, mode):
            return FP()

        def folder_list_files(self, p):
            if p == "/":
                return FL(["prev.CR3"])
            return FL([])

        def folder_list_folders(self, p):
            return FL([])

    class GP:
        GP_CAPTURE_IMAGE = object()

    assert gc.trigger_capture_and_get_raw_name(Cam(), GP()) == "prev.CR3"


def test_resolve_raw_name_cr3_reported_no_walk():
    class Cam:
        def folder_list_files(self, p):
            raise AssertionError("no walk")

        def folder_list_folders(self, p):
            raise AssertionError("no walk")

    assert gc.resolve_raw_name_after_capture(Cam(), None, "X.CR3") == "X.CR3"


def test_trigger_eos_remote_immediate_sets_immediate(monkeypatch):
    monkeypatch.setattr(gc, "_VIEWFINDER_OFF_SETTLE_S", 0.0)
    order: list[str] = []
    vf = type("W", (), {"value": 1})()
    rel = type("W", (), {"value": "None"})()

    class GP:
        GP_OK = 0

        @staticmethod
        def gp_widget_get_child_by_name(parent, name):
            if name == "main":
                return 0, "main"
            if name == "actions":
                return 0, "actions"
            if name == "viewfinder":
                return 0, vf
            if name == "eosremoterelease":
                return 0, rel
            return -1, None

        @staticmethod
        def gp_widget_set_value(widget, value):
            widget.value = value
            if widget is vf:
                order.append(f"vf:{value}")
            elif widget is rel:
                order.append(f"rel:{value}")

        @staticmethod
        def gp_widget_count_choices(widget):
            return 6

        @staticmethod
        def gp_widget_get_choice(widget, i):
            labels = [
                "None",
                "Press Half",
                "Press Full",
                "Release Half",
                "Release Full",
                "Immediate",
            ]
            return 0, labels[i]

    class Cam:
        def __init__(self):
            self.sets = []

        def get_config(self):
            return "cfg"

        def set_config(self, cfg):
            self.sets.append(cfg)

    cam = Cam()
    assert gc.trigger_eos_remote_immediate(cam, GP()) is True
    assert order[0] == "vf:0"
    assert "rel:Immediate" in order
    assert order.index("vf:0") < order.index("rel:Immediate")
    assert len(cam.sets) >= 2


def test_disable_viewfinder_best_effort_sets_zero():
    class W:
        def __init__(self):
            self.value = 1

    class GP:
        GP_OK = 0

        @staticmethod
        def gp_widget_get_child_by_name(parent, name):
            if name == "main":
                return 0, "main"
            if name == "actions":
                return 0, "actions"
            if name == "viewfinder":
                return 0, W()
            return -1, None

        @staticmethod
        def gp_widget_set_value(widget, value):
            widget.value = value

    class Cam:
        def __init__(self):
            self.sets = 0
            self.w = None

        def get_config(self):
            return "cfg"

        def set_config(self, cfg):
            self.sets += 1

    cam = Cam()
    # Patch path resolution to attach W we can inspect via set_value side effect
    values = []

    def set_value(widget, value):
        values.append(value)
        widget.value = value

    GP.gp_widget_set_value = staticmethod(set_value)
    assert gc.disable_viewfinder_best_effort(cam, GP()) is True
    assert values == [0]
    assert cam.sets == 1


def test_raw_exists_on_camera_true():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            return FL(["_MG_0001.CR3"])

        def folder_list_folders(self, p):
            return FL([])

    assert gc.raw_exists_on_camera(Cam(), None, "_MG_0001.CR3") is True
    assert gc.raw_exists_on_camera(Cam(), None, "_MG_0002.CR3") is False


def test_find_raw_folder_list_folders_raises():
    class Empty:
        def count(self):
            return 0

        def get_name(self, j):
            raise IndexError

    class Cam:
        def folder_list_files(self, p):
            return Empty()

        def folder_list_folders(self, p):
            raise RuntimeError("gvfs")

    assert gc.find_raw_on_camera(Cam(), None, "x.CR3", "/") == (None, None)


def test_capture_preview_bytes_ok():
    class CF:
        def get_data_and_size(self):
            return b"JPEGDATA"

    class Cam:
        def capture_preview(self, preview_file):
            assert preview_file is not None

    class GP:
        def CameraFile(self):
            return CF()

    assert gc.capture_preview_bytes(Cam(), GP()) == b"JPEGDATA"


def test_capture_preview_bytes_copies_non_bytes():
    class CF:
        def get_data_and_size(self):
            return bytearray(b"ABC")

    class Cam:
        def capture_preview(self, preview_file):
            pass

    class GP:
        def CameraFile(self):
            return CF()

    out = gc.capture_preview_bytes(Cam(), GP())
    assert out == b"ABC"
    assert isinstance(out, bytes)


def test_camera_file_scope_releases_ref_without_as_binding():
    import gc as py_gc
    import weakref

    refs: list = []

    class CF:
        pass

    class GP:
        def CameraFile(self):
            obj = CF()
            refs.append(weakref.ref(obj))
            return obj

    with gc.camera_file_scope(GP()):
        assert refs[0]() is not None
    py_gc.collect()
    assert refs[0]() is None


def test_capture_preview_bytes_failure_returns_none():
    class Cam:
        def capture_preview(self, preview_file):
            raise RuntimeError("boom")

    class GP:
        def CameraFile(self):
            return object()

    assert gc.capture_preview_bytes(Cam(), GP()) is None


def test_get_camera_serial_walk_depth_limit():
    class Deep:
        def __init__(self, n: int):
            self._n = n

        def get_name(self):
            return "node"

        def get_value(self):
            return None

        def count_children(self):
            return 1 if self._n < 45 else 0

        def get_child(self, i):
            return Deep(self._n + 1)

    class Cam:
        _pass = 0

        def get_config(self):
            self._pass += 1
            if self._pass == 1:
                raise RuntimeError("skip direct")
            return Deep(0)

    assert gc.get_camera_serial(object(), Cam()) is None


def test_get_camera_serial_walk_get_name_raises():
    class Bad:
        def get_name(self):
            raise RuntimeError("no")

        def count_children(self):
            return 0

        def get_child(self, i):
            raise IndexError

    class Root:
        def get_name(self):
            return "r"

        def get_value(self):
            return None

        def count_children(self):
            return 1

        def get_child(self, i):
            return Bad()

    class Cam:
        _p = 0

        def get_config(self):
            self._p += 1
            if self._p == 1:
                raise RuntimeError("x")
            return Root()

    assert gc.get_camera_serial(object(), Cam()) is None


def test_delete_jpeg_status_deleted_when_ok():
    class Cam:
        def file_delete(self, folder, name):
            return None

    assert gc.delete_jpeg_status(Cam(), None, "/", "a.jpg") == "deleted"


def test_delete_jpeg_status_absent_on_gphoto_file_not_found_code():
    gp = type("GP", (), {})()
    exc_type = type("GPhoto2Error", (Exception,), {})
    gp.GPhoto2Error = exc_type
    err = exc_type("missing")
    err.code = -107

    class Cam:
        def file_delete(self, folder, name):
            raise err

    assert gc.delete_jpeg_status(Cam(), gp, "/", "x.JPG") == "absent"


def test_delete_jpeg_status_raises_on_non_not_found():
    class Cam:
        def file_delete(self, folder, name):
            raise TimeoutError("busy")

    with pytest.raises(TimeoutError, match="busy"):
        gc.delete_jpeg_status(Cam(), None, "/", "a.jpg")


def test_is_not_found_error_message_fallback():
    class GP:
        pass

    assert gc.is_not_found_error(RuntimeError("no such file in store"), GP())
    assert not gc.is_not_found_error(RuntimeError("camera busy"), GP())


def test_find_latest_jpeg_on_camera_picks_sorted_name_in_folder():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            return FL(["IMG_2.JPG", "IMG_1.JPG"])

        def folder_list_folders(self, p):
            raise RuntimeError("leaf")

    f, n = gc.find_latest_jpeg_on_camera(Cam(), None, "/")
    assert f == "/" and n == "IMG_2.JPG"


def test_find_all_jpeg_paths_on_camera_recursive_case_insensitive():
    class FL:
        def __init__(self, names):
            self._names = names

        def count(self):
            return len(self._names)

        def get_name(self, j):
            return self._names[j]

    class Cam:
        def folder_list_files(self, p):
            if p == "/sub":
                return FL(["other.jpg", "target.JPG"])
            if p == "/":
                return FL([])
            return FL([])

        def folder_list_folders(self, p):
            if p == "/":
                return FL(["sub"])
            return FL([])

    hits = gc.find_all_jpeg_paths_on_camera(Cam(), None, "target.jpg", "/")
    assert hits == [("/sub", "target.JPG")]


def test_delete_jpeg_by_basename_deletes_all_matches():
    deleted: list[tuple[str, str]] = []

    class Cam:
        def folder_list_files(self, p):
            class FL:
                def count(self):
                    return 1

                def get_name(self, j):
                    return "x.JPG"

            return FL()

        def folder_list_folders(self, p):
            class FL:
                def count(self):
                    return 2 if p == "/" else 0

                def get_name(self, j):
                    return f"store{j}"

            return FL()

        def file_delete(self, folder, name):
            deleted.append((folder, name))

    assert gc.delete_jpeg_by_basename(Cam(), None, "x.JPG") == "deleted"
    assert len(deleted) >= 1


def test_delete_jpeg_by_basename_absent_when_not_found():
    class Cam:
        def folder_list_files(self, p):
            class FL:
                def count(self):
                    return 0

                def get_name(self, j):
                    return ""

            return FL()

        def folder_list_folders(self, p):
            class FL:
                def count(self):
                    return 0

                def get_name(self, j):
                    return ""

            return FL()

    assert gc.delete_jpeg_by_basename(Cam(), None, "missing.JPG") == "absent"
