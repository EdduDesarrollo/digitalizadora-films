"""Popup de configuración de umbralización (`UMBRAL_GREY_PERFORACION`)."""

from __future__ import annotations

import logging
import threading
import time
from io import BytesIO
from typing import TYPE_CHECKING, Callable

from print_scanner_app.ui.i18n import bind_popup_tracking, t

if TYPE_CHECKING:
    from print_scanner_app.ui.presenters.app_presenter import AppPresenter

_log = logging.getLogger(__name__)


def _threshold_rgb_bytes(jpeg: bytes, umbral_grey: int) -> tuple[bytes, int, int] | None:
    """Máscara ``gray > ug`` → RGB bytes (paridad con debug_thresh_full)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        gray = Image.open(BytesIO(jpeg)).convert("L")
        arr = np.asarray(gray)
        t = max(0, min(255, int(umbral_grey)))
        mask = (arr > t).astype(np.uint8) * 255
        rgb = np.stack([mask, mask, mask], axis=-1)
        h, w = mask.shape
        return rgb.tobytes(), int(w), int(h)
    except Exception:  # noqa: BLE001
        return None


class UmbralizacionDialogs:
    @classmethod
    def open(
        cls,
        presenter: "AppPresenter",
        *,
        on_open_popup: Callable[[object], None] | None = None,
        on_busy_closing: Callable[[], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> bool:
        """
        Abre el popup (asume que el caller ya detuvo el pipeline de img1 y
        llamó ``begin_umbralizacion_preview``).

        ``on_busy_closing``: cursor wait al pulsar Aceptar/Cancelar, antes del cierre.
        """
        log = logger or _log
        try:
            from kivy.clock import Clock
            from kivy.graphics.texture import Texture
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.image import Image as KivyImage
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
            from kivy.uix.slider import Slider

            from print_scanner_app.ui.widgets.menu_button import MenuButton
        except Exception as e:  # noqa: BLE001
            log.error("Umbralización UI: Kivy no disponible: %s", e)
            if on_finished:
                on_finished()
            return False

        initial = int(presenter.get_umbral_grey())
        state = {
            "ug": initial,
            "running": True,
            "latest": None,  # (bytes, w, h) frame umbralizado
            "token": 0,
            "rendered": -1,
            "last_jpeg": None,
            "thresh_dirty": True,
        }
        lock = threading.Lock()

        root = BoxLayout(orientation="vertical", spacing=10, padding=12)
        preview = KivyImage(allow_stretch=True, keep_ratio=True, size_hint=(1, 1))
        root.add_widget(preview)

        value_label = Label(
            text=t("umbralizacion.value", value=initial),
            size_hint_y=None,
            height=28,
            font_size="16sp",
        )
        root.add_widget(value_label)

        slider = Slider(
            min=0,
            max=255,
            value=float(initial),
            step=1,
            size_hint_y=None,
            height=40,
        )
        root.add_widget(slider)

        row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=48)
        btn_cancel = MenuButton(text=t("common.cancel"), size_hint_x=1)
        btn_ok = MenuButton(text=t("common.accept"), size_hint_x=1)
        row.add_widget(btn_cancel)
        row.add_widget(btn_ok)
        root.add_widget(row)

        popup = Popup(
            title=t("umbralizacion.config_title"),
            content=root,
            size_hint=(0.92, 0.92),
            auto_dismiss=False,
        )
        bind_popup_tracking(popup)

        def _push_thresh(jpeg: bytes, ug: int) -> None:
            frame = _threshold_rgb_bytes(jpeg, ug)
            if frame is None:
                return
            fb, w, h = frame
            with lock:
                state["latest"] = (fb, w, h)
                state["token"] += 1
                state["thresh_dirty"] = False

        def _on_slider(_inst, value):
            ug = max(0, min(255, int(round(float(value)))))
            with lock:
                state["ug"] = ug
                jpeg = state["last_jpeg"]
                state["thresh_dirty"] = True
            value_label.text = t("umbralizacion.value", value=ug)
            if jpeg:
                _push_thresh(jpeg, ug)

        slider.bind(value=_on_slider)

        def _apply_frame(frame_bytes: bytes, width: int, height: int) -> None:
            if not frame_bytes or width <= 0 or height <= 0:
                return
            tex = preview.texture
            if tex is None or tex.size != (width, height):
                tex = Texture.create(size=(width, height), colorfmt="rgb")
                tex.flip_vertical()
                preview.texture = tex
            tex.blit_buffer(frame_bytes, colorfmt="rgb", bufferfmt="ubyte")
            preview.canvas.ask_update()

        def _render_tick(_dt):
            with lock:
                if not state["running"]:
                    return False
                token = state["token"]
                if token == state["rendered"]:
                    return True
                latest = state["latest"]
                state["rendered"] = token
            if latest is None:
                return True
            fb, w, h = latest
            _apply_frame(fb, w, h)
            return True

        def _worker():
            fps = 8.0
            try:
                fps = float(presenter.preview_fps_target())
            except Exception:  # noqa: BLE001
                pass
            interval = 1.0 / max(2.0, min(fps, 15.0))
            while True:
                with lock:
                    if not state["running"]:
                        break
                    ug = int(state["ug"])
                t0 = time.perf_counter()
                jpeg = presenter.read_umbralizacion_preview_jpeg()
                if jpeg:
                    with lock:
                        state["last_jpeg"] = jpeg
                    _push_thresh(jpeg, ug)
                elapsed = time.perf_counter() - t0
                time.sleep(max(0.0, interval - elapsed))

        worker = threading.Thread(target=_worker, daemon=True)
        render_ev = Clock.schedule_interval(_render_tick, 1.0 / 30.0)

        finished = {"done": False}

        def _finish():
            if finished["done"]:
                return
            finished["done"] = True
            with lock:
                state["running"] = False
            try:
                render_ev.cancel()
            except Exception:  # noqa: BLE001
                pass
            if on_finished:
                on_finished()

        def _cancel(_inst=None):
            if on_busy_closing is not None:
                on_busy_closing()
            Clock.schedule_once(lambda _dt: popup.dismiss(), 0)

        def _accept(_inst=None):
            if on_busy_closing is not None:
                on_busy_closing()
            with lock:
                ug = int(state["ug"])

            def _do_accept(_dt):
                presenter.set_umbral_grey(ug)
                log.info("UMBRAL_GREY_PERFORACION actualizado: %s", ug)
                popup.dismiss()

            Clock.schedule_once(_do_accept, 0)

        btn_cancel.bind(on_release=_cancel)
        btn_ok.bind(on_release=_accept)
        popup.bind(on_dismiss=lambda *_a: _finish())

        worker.start()
        if on_open_popup is not None:
            on_open_popup(popup)
        else:
            popup.open()
        return True
