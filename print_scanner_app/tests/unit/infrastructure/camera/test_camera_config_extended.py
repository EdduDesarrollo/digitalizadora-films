from print_scanner_app.infrastructure.camera.camera_config import (
    apply_camera_configurations,
    apply_configurations_to_camera,
    normalize_camera_config,
)


class _GP:
    GP_OK = 0

    class GPhoto2Error(Exception):
        pass


def test_get_config_raises_returns_false():
    class Cam:
        def get_config(self):
            raise RuntimeError("usb")

    assert (
        apply_configurations_to_camera(
            Cam(),
            {"main/imgsettings/iso": 100},
            _GP,
        )
        is False
    )


def test_apply_success_minimal():
    class Widget:
        pass

    class Cam:
        def __init__(self):
            self.saved = False

        def get_config(self):
            return Widget()

        def set_config(self, c):
            self.saved = True

    gp = _GP()

    def get_child(widget, name):
        return gp.GP_OK, Widget()

    def set_val(widget, v):
        pass

    gp.gp_widget_get_child_by_name = get_child
    gp.gp_widget_set_value = set_val

    cam = Cam()
    ok = apply_configurations_to_camera(
        cam,
        {"main/settings/capturetarget": "Memory card"},
        gp,
    )
    assert ok is True
    assert cam.saved is True


def test_apply_none_string_uses_none_value():
    class Widget:
        pass

    class Cam:
        def __init__(self):
            self.values = []

        def get_config(self):
            return Widget()

        def set_config(self, c):
            pass

    gp = _GP()
    calls = []

    def get_child(widget, name):
        return gp.GP_OK, Widget()

    def set_val(widget, v):
        calls.append(v)

    gp.gp_widget_get_child_by_name = get_child
    gp.gp_widget_set_value = set_val

    cam = Cam()
    ok = apply_configurations_to_camera(cam, {"main/imgsettings/iso": "none"}, gp)
    assert ok is True
    assert calls == [None]


def test_gp_ok_failure_counts_as_failed():
    class Widget:
        pass

    class Cam:
        def get_config(self):
            return Widget()

        def set_config(self, c):
            raise AssertionError("no aplicadas")

    gp = _GP()

    def get_child(widget, name):
        return -1, None

    gp.gp_widget_get_child_by_name = get_child
    gp.gp_widget_set_value = lambda w, v: None

    cam = Cam()
    assert (
        apply_configurations_to_camera(
            cam,
            {"main/imgsettings/iso": 100},
            gp,
        )
        is True
    )


def test_gphoto2error_on_set_increments_fallidas_only():
    class Widget:
        pass

    class Cam:
        def __init__(self):
            self.saved = False

        def get_config(self):
            return Widget()

        def set_config(self, c):
            self.saved = True

    gp = _GP()

    class Boom(Exception):
        pass

    gp.GPhoto2Error = Boom

    def get_child(widget, name):
        return gp.GP_OK, Widget()

    def set_val(widget, v):
        raise Boom("x")

    gp.gp_widget_get_child_by_name = get_child
    gp.gp_widget_set_value = set_val

    cam = Cam()
    assert (
        apply_configurations_to_camera(
            cam,
            {"main/imgsettings/iso": 1},
            gp,
        )
        is True
    )
    assert cam.saved is False


def test_mixed_fail_and_success_still_sets_config():
    class Widget:
        pass

    class Cam:
        def __init__(self):
            self.saved = False

        def get_config(self):
            return Widget()

        def set_config(self, c):
            self.saved = True

    gp = _GP()
    n = {"calls": 0}

    def get_child(widget, name):
        n["calls"] += 1
        if name == "aperture":
            return -99, None
        return gp.GP_OK, Widget()

    gp.gp_widget_get_child_by_name = get_child
    gp.gp_widget_set_value = lambda w, v: None

    cam = Cam()
    ok = apply_configurations_to_camera(
        cam,
        {
            "main/capturesettings/aperture": "16",
            "main/imgsettings/iso": 250,
        },
        gp,
    )
    assert ok is True
    assert cam.saved is True


def test_normalize_camera_config_filters_invalid():
    assert normalize_camera_config(None) == {}
    assert normalize_camera_config({"": 1, " /ok ": 2}) == {"/ok": 2}


def _choice_widget_gp(choices: list[str]):
    """Widget con choices para tests de resolución locale."""

    class Widget:
        pass

    class _GP:
        GP_OK = 0

        class GPhoto2Error(Exception):
            pass

    gp = _GP()
    values_set = []

    def count(_w):
        return len(choices)

    def get_choice(_w, i):
        return gp.GP_OK, choices[i]

    def set_val(_w, v):
        values_set.append(v)

    gp.gp_widget_count_choices = count
    gp.gp_widget_get_choice = get_choice
    gp.gp_widget_set_value = set_val
    gp.gp_widget_get_readonly = lambda _w: (gp.GP_OK, 0)

    def get_child(widget, name):
        return gp.GP_OK, Widget()

    gp.gp_widget_get_child_by_name = get_child
    return gp, values_set


def test_apply_memory_card_es_choices():
    gp, values_set = _choice_widget_gp(["Tarjeta de memoria", "RAM Interna"])

    class Cam:
        def __init__(self):
            self.saved = False

        def get_config(self):
            return object()

        def set_config(self, c):
            self.saved = True

    conf = {
        "main/settings/capturetarget": "Memory card",
    }
    result = apply_camera_configurations(Cam(), conf, gp)
    assert result.ok
    assert "main/settings/capturetarget" in result.applied
    assert values_set == ["Tarjeta de memoria"]


def test_apply_model_mismatch_skips_loop():
    class Cam:
        def get_config(self):
            raise AssertionError("no apply")

    result = apply_camera_configurations(
        Cam(),
        {"main/settings/capturetarget": "Memory card"},
        _GP(),
        model_mismatch=True,
    )
    assert not result.ok
    assert result.model_mismatch
    assert result.applied == []
