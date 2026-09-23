from __future__ import annotations

import logging
import threading
import time
from io import BytesIO

from print_scanner_app.ui.presenters.app_presenter import AppPresenter

PAUSE_PREVIEW_REOPEN_TIMEOUT_S = 60.0


def _patch_linux_cutbuffer_if_missing() -> None:
    """
    En Linux, si no hay xclip/xsel, Kivy deja CutBuffer en None y además puede registrar
    un log CRITICAL ruidoso. Sincronizamos un shim en clipboard + textinput para que
    TextInput (popups de código, umbral, etc.) no dependa de binarios X11 opcionales.
    """
    import sys

    if sys.platform != "linux":
        return
    import kivy.core.clipboard as kc
    import kivy.uix.textinput as ti

    if kc.CutBuffer is not None:
        ti.CutBuffer = kc.CutBuffer
        return

    class _CutbufferShim:
        __slots__ = ()

        def get_cutbuffer(self) -> str:
            return ""

        def set_cutbuffer(self, _data) -> None:
            pass

    shim = _CutbufferShim()
    kc.CutBuffer = shim
    ti.CutBuffer = shim


def run_modular_app(
    logger: logging.Logger,
    *,
    session_label: str | None = None,
    auto_startup: bool = True,
    startup_reset_usb: bool = True,
) -> None:
    """UI Kivy principal."""
    import os

    os.environ["KIVY_NO_ARGS"] = "1"
    # Sin xclip/xsel (Wayland o desktop mínimo) Kivy prueba providers que fallan al importar.
    # `dummy` evita esa cadena; el cutbuffer X11 se completa con `_patch_linux_cutbuffer_if_missing`.
    os.environ.setdefault("KIVY_CLIPBOARD", "dummy")

    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.graphics.texture import Texture
    from kivy.graphics import Color, Line, Rectangle
    from kivy.uix.anchorlayout import AnchorLayout
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.image import Image as KivyImage
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.textinput import TextInput

    _patch_linux_cutbuffer_if_missing()

    from print_scanner_app.application.session_naming import normalized_codigo_referencia
    from print_scanner_app.app.container import default_container
    from print_scanner_app.ui import i18n
    from print_scanner_app.ui.dialogs import CameraDialogs, ErrorDialogs, ExitDialogs, RawDialogs
    from print_scanner_app.ui.i18n import UI_LANGUAGE_KEY, bind_popup_tracking, t, target_language_label
    from print_scanner_app.ui.widgets.custom_file_chooser import CustomFileChooser
    from print_scanner_app.ui.widgets.menu_button import MenuButton

    try:
        from PIL import Image as PilImage
    except Exception:  # noqa: BLE001
        PilImage = None

    container = default_container(logger, session_label=session_label)
    presenter = AppPresenter(container=container, logger=logger)
    presenter.hydrate_numero_frame_from_config()
    try:
        i18n.set_language(container.config_repo.load().get(UI_LANGUAGE_KEY))
    except Exception:  # noqa: BLE001
        i18n.set_language("es")

    def _on_alignment_timeout():
        from kivy.clock import Clock

        Clock.schedule_once(
            lambda _dt: ErrorDialogs.show_error(t("align.timeout"), title=t("common.error_bang")),
            0,
        )

    presenter.set_alignment_timeout_callback(_on_alignment_timeout)

    class ThermalModularApp(App):
        def build(self):
            self.title = "Print Scanner"
            self.capture_loop_started = False
            self.sidebar_expanded = True
            self.hotkeys_enabled = True
            self._key_handler_bound = False
            self._format_selected = False
            self._codigo_splash_done = False
            self._startup_wizard_active = False
            self._preview_worker_running = False
            self._preview_worker_thread = None
            self._preview_render_event = None
            self._preview_lock = threading.Lock()
            self._latest_preview_frame = None
            self._latest_preview_token = 0
            self._last_rendered_preview_token = -1
            self._preview_worker_iter = 0
            self._preview_showing_logo = False
            self._exit_cleanup_done = False
            self._startup_banner_collapsed = False
            self._busy_cursor = None
            self._pause_preview_timeout_ev = None
            self._pause_preview_baseline_token = -1

            try:
                Window.maximize()
            except Exception:  # noqa: BLE001
                pass
            try:
                Window.top = 0
                Window.left = 0
            except Exception:  # noqa: BLE001
                pass
            Window.clearcolor = (0.1, 0.1, 0.1, 1.0)
            Window.bind(on_request_close=self._on_request_close)

            from print_scanner_app.ui.kivy_busy_cursor import KivyBusyCursor

            self._busy_cursor = KivyBusyCursor(Clock, Window)

            root = BoxLayout(orientation="horizontal", padding=10, spacing=8)
            left_layout = BoxLayout(orientation="vertical", spacing=8)
            self.sidebar = BoxLayout(
                orientation="vertical",
                spacing=0,
                size_hint_x=None,
                width=120,
                padding=(0, 0, 0, 0),
            )
            with self.sidebar.canvas.before:
                self._sidebar_bg_color = Color(0.3, 0.3, 0.3, 1.0)
                self._sidebar_bg_rect = Rectangle(pos=self.sidebar.pos, size=self.sidebar.size)
            self.sidebar.bind(pos=self._sync_sidebar_background, size=self._sync_sidebar_background)

            self.status_line = Label(
                text=presenter.status_hint(),
                font_size=14,
                size_hint_y=None,
                height=36,
                halign="left",
                valign="middle",
            )
            self.status_line.bind(size=lambda *_: setattr(self.status_line, "text_size", self.status_line.size))
            self.info_line = Label(
                text=self._build_top_info_text(),
                font_size=13,
                size_hint_y=None,
                height=32,
                halign="left",
                valign="middle",
            )
            self.info_line.bind(size=lambda *_: setattr(self.info_line, "text_size", self.info_line.size))
            self.startup_line = Label(
                text=t("startup.dash") if auto_startup else t("startup.skipped"),
                font_size=12,
                size_hint_y=None,
                height=28,
                halign="left",
                valign="middle",
            )
            self.startup_line.bind(size=lambda *_: setattr(self.startup_line, "text_size", self.startup_line.size))
            left_layout.add_widget(self.status_line)
            left_layout.add_widget(self.info_line)
            left_layout.add_widget(self.startup_line)

            self.preview_container = FloatLayout(size_hint=(1, 1))
            with self.preview_container.canvas.before:
                self._preview_bg_color = Color(0.05, 0.05, 0.05, 1)
                self._preview_bg_rect = Rectangle(pos=self.preview_container.pos, size=self.preview_container.size)
            self.preview_container.bind(pos=self._sync_preview_background, size=self._sync_preview_background)
            self.preview_image = KivyImage(
                size_hint=(1, 1),
                pos_hint={"center_x": 0.5, "center_y": 0.5},
                fit_mode="contain",
                allow_stretch=True,
            )
            self.preview_container.add_widget(self.preview_image)
            self._show_logo_in_preview()
            self.preview_image.bind(
                pos=lambda *_: self._refresh_preview_panel(),
                size=lambda *_: self._refresh_preview_panel(),
            )
            left_layout.add_widget(self.preview_container)

            dl_progress = ProgressBar(max=100, value=0, size_hint_y=None, height=18)

            def refresh_status():
                self.status_line.text = presenter.status_hint()
                self.info_line.text = self._build_top_info_text()
                self._apply_dynamic_colors()
                self._apply_digitization_ui_lock()
                self._refresh_preview_panel()
                self._refresh_download_button_state()

            def show_printer_clean_popup():
                from print_scanner_app.ui.dialogs.printer_clean_dialog import PrinterCleanDialogs

                PrinterCleanDialogs.show(on_open=self._open_popup_disabling_hotkeys)

            presenter.register_printer_clean_refresh_status_callback(refresh_status)
            presenter.register_printer_clean_popup_callback(show_printer_clean_popup)

            def _cancel_pause_preview_timeout():
                ev = self._pause_preview_timeout_ev
                if ev is not None:
                    ev.cancel()
                    self._pause_preview_timeout_ev = None

            def _complete_pause_preview_transition(_dt=None):
                if not presenter.is_pause_transitioning():
                    return
                _cancel_pause_preview_timeout()
                if self._busy_cursor is not None:
                    self._busy_cursor.clear()
                presenter.end_pause_transition()
                refresh_status()

            def _force_exit_after_preview_timeout():
                presenter.end_pause_transition()
                presenter.exit_via_use_case()
                App.get_running_app().stop()

            def _on_pause_preview_timeout(_dt):
                self._pause_preview_timeout_ev = None
                if not presenter.is_pause_transitioning():
                    return
                if self._busy_cursor is not None:
                    self._busy_cursor.clear()
                ErrorDialogs.show_error(
                    t("pause.preview_timeout"),
                    title=t("common.error"),
                    on_ok=_force_exit_after_preview_timeout,
                )

            def _arm_pause_preview_timeout(_dt=None):
                if not presenter.is_pause_transitioning():
                    return
                self._pause_preview_baseline_token = self._latest_preview_token
                _cancel_pause_preview_timeout()
                self._pause_preview_timeout_ev = Clock.schedule_once(
                    _on_pause_preview_timeout,
                    PAUSE_PREVIEW_REOPEN_TIMEOUT_S,
                )
                refresh_status()

            def _start_pause_ui_transition(_dt=None):
                presenter.begin_pause_transition()
                if self._busy_cursor is not None:
                    self._busy_cursor.show_wait()
                refresh_status()

            def _on_pause_accepted():
                Clock.schedule_once(_start_pause_ui_transition, 0)

            def _on_pause_capture_closed():
                Clock.schedule_once(_arm_pause_preview_timeout, 0)

            self._complete_pause_preview_transition = _complete_pause_preview_transition
            presenter.register_pause_accepted_callback(_on_pause_accepted)
            presenter.register_pause_capture_closed_callback(_on_pause_capture_closed)

            def run_startup_async(*, start_preview_after: bool = False):
                self.startup_line.text = t("startup.in_progress")

                def work():
                    out = presenter.run_startup(reset_usb_first=startup_reset_usb)

                    def ui(_dt):
                        if out is None:
                            self.startup_line.text = t("startup.internal_error")
                        else:
                            if not out.camera_assigned:
                                self.startup_line.text = t(
                                    "startup.camera_failed",
                                    printer=t("startup.printer_ok") if out.printer_ok else t("startup.printer_failed"),
                                    usb_resets=out.usb_resets,
                                )
                            else:
                                self.startup_line.text = t(
                                    "startup.camera_ok",
                                    printer=t("startup.printer_ok") if out.printer_ok else t("startup.printer_failed"),
                                    usb_resets=out.usb_resets,
                                )
                        # Una sola sesión a la vez: preview solo tras assign_camera + exit.
                        if start_preview_after:
                            self._start_preview_pipeline()
                        refresh_status()
                        Clock.schedule_once(lambda _t: self._collapse_startup_banner(), 5.0)

                    Clock.schedule_once(ui, 0)

                threading.Thread(target=work, daemon=True).start()

            def do_retry_camera(_inst=None):
                logger.info("Reintentando asignación de cámara…")

                def work():
                    r = presenter.run_retry_camera()

                    def ui(_dt):
                        if r.ok:
                            msg = t(
                                "camera.retry_ok",
                                usb=r.usb_address or "—",
                                serial=r.serial or "—",
                            )
                            logger.info("%s", msg)
                            CameraDialogs.show_retry_result(True, msg)
                        else:
                            msg = t(
                                "camera.retry_fail",
                                error=r.error or t("camera.retry_fail_fallback"),
                            )
                            logger.info("%s", msg)
                            CameraDialogs.show_retry_result(False, msg)
                        refresh_status()

                    Clock.schedule_once(ui, 0)

                threading.Thread(target=work, daemon=True).start()

            self.btn_retry_camera = MenuButton(text=t("btn.retry_camera"))
            self.btn_retry_camera.bind(on_release=do_retry_camera)
            btn_retry = self.btn_retry_camera

            def set_fmt(fmt: str):
                if presenter.set_format(fmt):
                    self._format_selected = True
                    logger.info("Formato activo: %s", fmt)
                    if self._startup_wizard_active:
                        self._end_startup_wizard()
                else:
                    logger.info("No se pudo cambiar formato")
                refresh_status()

            def do_change_dir(_inst=None):
                from print_scanner_app.ui.directory_prompt import prompt_output_directory

                def on_dir_ok():
                    logger.info("Directorio actualizado")
                    refresh_status()

                prompt_output_directory(
                    presenter,
                    on_success=on_dir_ok,
                    on_open_popup=self._open_popup_disabling_hotkeys,
                    refresh_status=refresh_status,
                )

            def do_open_dir(_inst=None):
                ok = presenter.open_current_directory()
                logger.info("%s", "Directorio abierto" if ok else "No se pudo abrir directorio")
                refresh_status()

            def do_move_film_1px(_inst=None):
                r = presenter.move_film_pixels(1)
                if r.ok:
                    logger.info("Film: movido 1 px (impresora)")
                else:
                    logger.warning("Film: no se pudo mover 1 px (impresora)")
                refresh_status()

            def do_frame_x_frame(_inst=None):
                if not self._codigo_splash_done:
                    ErrorDialogs.show_error(
                        t("fxf.need_codigo"),
                        title=t("session.title"),
                    )
                    return
                if not self._format_selected:
                    logger.info("Seleccioná formato antes de Frame x Frame")
                    do_set_format_popup()
                    return
                if presenter.is_frame_by_frame_busy():
                    return
                if presenter.is_digitalizing() and not presenter.is_paused():
                    return
                if presenter.is_pause_transitioning():
                    return
                if presenter.needs_output_directory_setup():
                    ErrorDialogs.show_error(
                        t("fxf.need_directory"),
                        title=t("fxf.title"),
                    )
                    return

                from kivy.uix.boxlayout import BoxLayout
                from kivy.uix.label import Label
                from kivy.uix.popup import Popup

                box = BoxLayout(orientation="vertical", padding=20, spacing=10)
                box.add_widget(Label(text=t("fxf.taking_frame"), font_size="18sp"))
                pop = Popup(
                    title=t("fxf.capturing_title"),
                    content=box,
                    size_hint=(None, None),
                    size=(300, 150),
                    auto_dismiss=False,
                )
                self._open_popup_disabling_hotkeys(pop)

                def work():
                    r = presenter.run_capture_frame_by_frame()

                    def ui(_dt):
                        if pop.parent:
                            pop.dismiss()
                        if not r.ok and (r.error or "").strip():
                            ErrorDialogs.show_error(r.error or t("common.error"), title=t("fxf.title"))
                        elif r.ok:
                            logger.info("Frame x Frame: captura OK")
                        refresh_status()

                    Clock.schedule_once(ui, 0)

                threading.Thread(target=work, daemon=True).start()

            def do_inc_frame(_inst=None):
                n = presenter.increment_frame(1)
                logger.info("Contador frame manual: %s", n)
                refresh_status()

            def do_set_frame(_inst=None):
                from print_scanner_app.ui.textinput_focus import focus_text_input

                box = BoxLayout(orientation="vertical", spacing=8, padding=10)
                ti = TextInput(
                    text=str(presenter.get_frame()),
                    multiline=False,
                    input_filter="int",
                    size_hint_y=None,
                    height=40,
                )
                row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
                b_ok = MenuButton(text=t("common.apply"), size_hint_x=1)
                b_cancel = MenuButton(text=t("common.cancel"), size_hint_x=1)
                row.add_widget(b_ok)
                row.add_widget(b_cancel)
                box.add_widget(ti)
                box.add_widget(row)
                pop = Popup(title=t("frame.edit_title"), content=box, size_hint=(None, None), size=(420, 200))

                def apply_frame(_x):
                    raw = (ti.text or "").strip()
                    if not raw:
                        ErrorDialogs.show_error(
                            t("config.empty_value"),
                            title=t("frame.edit_title"),
                        )
                        return
                    n = presenter.set_frame(int(raw))
                    logger.info("Frame seteado: %s", n)
                    pop.dismiss()
                    refresh_status()

                b_ok.bind(on_release=apply_frame)
                b_cancel.bind(on_release=lambda _x: pop.dismiss())
                ti.bind(on_text_validate=lambda *_: apply_frame(None))
                focus_text_input(ti)
                self._open_popup_disabling_hotkeys(pop)

            def do_start_dig(_inst=None):
                if not self._codigo_splash_done:
                    ErrorDialogs.show_error(
                        t("fxf.need_codigo"),
                        title=t("session.title"),
                    )
                    return
                if not self._format_selected:
                    logger.info("Seleccioná formato antes de digitalizar")
                    do_set_format_popup()
                    return
                if presenter.is_digitalizing() and presenter.is_paused():
                    r = presenter.run_resume_digitization()
                else:
                    r = presenter.run_start_digitization()
                logger.info(
                    "%s",
                    "Digitación: iniciada / reanudada"
                    if r.ok
                    else ("Digitación: %s" % (r.error or "no disponible")),
                )
                refresh_status()
                if not r.ok:
                    err_l = (r.error or "").lower()
                    msg = (r.error or "").strip()
                    if msg:
                        ErrorDialogs.show_error(msg, title=t("digitization.title"))
                    elif presenter.is_debug_ui_active() and "ya activa" in err_l:
                        ErrorDialogs.show_error(
                            t("digitization.already_running"),
                            title=t("digitization.title"),
                        )
                    return
                if r.ok and presenter.is_debug_ui_active():
                    Clock.schedule_once(lambda _dt: presenter.run_capture_tick(), 0)
                if self.capture_loop_started:
                    return

                def capture_loop():
                    while True:
                        presenter.wait_until_capture_tick_allowed()
                        interval = presenter.capture_tick_interval_seconds()
                        changed = presenter.run_capture_tick()
                        if changed:
                            Clock.schedule_once(lambda _dt: refresh_status(), 0)
                        if presenter.is_debug_alignment_waiting():
                            time.sleep(min(interval, 0.05))
                        else:
                            time.sleep(interval)

                self.capture_loop_started = True
                threading.Thread(target=capture_loop, daemon=True).start()

            def do_pause_dig(_inst=None):
                r = presenter.run_pause_digitization()
                logger.info(
                    "%s",
                    "Digitación: en pausa"
                    if r.ok
                    else "Pausa: no aplica (iniciá digitación antes o sin Container)",
                )
                refresh_status()

            def do_resume_dig(_inst=None):
                r = presenter.run_resume_digitization()
                logger.info(
                    "%s",
                    "Digitación: reanudada"
                    if r.ok
                    else ("Reanudar: %s" % (r.error or "no aplica")),
                )
                refresh_status()
                if not r.ok and (r.error or "").strip():
                    ErrorDialogs.show_error(r.error.strip(), title=t("digitization.title"))
                if r.ok and presenter.is_debug_ui_active():
                    Clock.schedule_once(lambda _dt: presenter.run_capture_tick(), 0)

            def do_stop_dig(_inst=None):
                r = presenter.run_stop_digitization()
                logger.info(
                    "%s",
                    "Digitación: detenida" if r.ok else "Detener: no disponible (sin Container)",
                )
                refresh_status()

            def _run_download(on_done=None):
                from kivy.core.window import Window

                from print_scanner_app.application.dto.results import DownloadRawsResult

                self._stop_preview_pipeline()
                busy = self._busy_cursor
                busy.show_wait()
                logger.info("Descargando RAWs…")
                dl_progress.value = 0

                def work():
                    def prog(i, t, msg):
                        pct = 100.0 * float(i) / float(max(t, 1))
                        Clock.schedule_once(lambda _dt, p=pct: setattr(dl_progress, "value", p), 0)
                        logger.info("%s", msg)

                    try:
                        r = presenter.run_download_pending(progress=prog)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Descarga: excepción no controlada")
                        r = DownloadRawsResult(error=str(exc))

                    def apply_ui(_dt):
                        try:
                            dl_progress.value = 100
                            RawDialogs.show_download_outcome(
                                downloaded=len(r.downloaded),
                                not_found=len(r.not_found),
                                batch_folder=r.batch_folder,
                                error=r.error,
                            )
                            if r.missing_local_copy_ids:
                                RawDialogs.show_raw_pending_missing_local_copy(r.missing_local_copy_ids)
                            logger.info(
                                "Descarga: %s descargados, %s no encontrados, carpeta %s, error=%s",
                                len(r.downloaded),
                                len(r.not_found),
                                r.batch_folder,
                                r.error,
                            )
                        finally:
                            busy.clear()
                            presenter.reopen_camera_preview_after_download()
                            self._start_preview_pipeline()
                            refresh_status()
                            if on_done is not None:
                                on_done()

                    Clock.schedule_once(apply_ui, 0)

                threading.Thread(target=work, daemon=True).start()

            def do_download(_inst=None):
                if not self._codigo_splash_done:
                    ErrorDialogs.show_error(
                        t("fxf.need_codigo"),
                        title=t("session.title"),
                    )
                    return
                pending = presenter.pending_raw_count()
                if pending <= 0:
                    ErrorDialogs.show_error(t("raw.none_pending"), title=t("raw.download_title"))
                    return
                RawDialogs.confirm_download(pending, _run_download)

            def _do_exit_confirmed():
                busy = self._busy_cursor
                if busy is not None:
                    busy.show_wait()
                try:
                    self._perform_exit_cleanup()
                    r = presenter.exit_via_use_case(release_camera=False)
                    logger.info("ExitAppUseCase ejecutado: ok=%s", r.ok)
                finally:
                    if busy is not None:
                        busy.clear()
                App.get_running_app().stop()

            def do_exit(_inst=None):
                pending = presenter.pending_raw_count()
                if pending > 0:
                    def _save_and_exit():
                        _run_download(on_done=_do_exit_confirmed)

                    ExitDialogs.confirm_exit_with_pending(
                        pending_count=pending,
                        on_save_and_exit=_save_and_exit,
                        on_exit_without_saving=_do_exit_confirmed,
                    )
                    return
                ExitDialogs.confirm_exit(_do_exit_confirmed)

            def do_toggle_overlay(_inst=None):
                enabled = presenter.toggle_overlay()
                self._refresh_preview_panel()
                logger.info("Cuadrícula %s", "activada" if enabled else "desactivada")
                refresh_status()

            def do_toggle_perforation_side(_inst=None):
                side = presenter.toggle_perforation_side()
                if side is None:
                    return False
                logger.info("Lado perforación: %s", side)
                self._refresh_preview_panel()
                refresh_status()
                return True

            def do_toggle_sidebar(_inst=None):
                self.sidebar_expanded = not self.sidebar_expanded
                self.sidebar.width = 120 if self.sidebar_expanded else 40
                self.sidebar_toggle.text = ">" if self.sidebar_expanded else "<"
                self.sidebar_buttons_layout.opacity = 1 if self.sidebar_expanded else 0
                self.sidebar_buttons_layout.disabled = not self.sidebar_expanded
                self._rebuild_sidebar_header()

            def do_toggle_language(_inst=None):
                if i18n.has_open_popup():
                    return
                if presenter.is_digitalizing() and not presenter.is_paused():
                    return
                new_lang = "en" if i18n.get_language() == "es" else "es"
                i18n.set_language(new_lang)
                presenter.persist_config_key(UI_LANGUAGE_KEY, new_lang)
                self._apply_ui_language()
                refresh_status()

            def do_set_format_popup(_inst=None):
                box = BoxLayout(orientation="vertical", spacing=6, padding=[10, 16, 10, 8])
                formats = ["8mm", "super8", "16mm", "35mm"]
                disabled_formats = {"8mm", "super8"}
                row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=56)
                for fmt in formats:
                    label = "35mm\n(beta)" if fmt == "35mm" else fmt
                    b = MenuButton(text=label, size_hint_x=1, height=56)
                    if fmt in disabled_formats:
                        b.disabled = True
                    else:
                        b.bind(on_release=lambda _x, f=fmt: (set_fmt(f), pop.dismiss()))
                    row.add_widget(b)
                box.add_widget(Label(text=t("format.select_label"), size_hint_y=None, height=28))
                box.add_widget(row)
                pop = Popup(
                    title=t("format.initial_title"),
                    content=box,
                    size_hint=(None, None),
                    size=(560, 160),
                )
                self._open_popup_disabling_hotkeys(pop)

            def do_threshold_popup(_inst=None):
                from print_scanner_app.ui.textinput_focus import focus_text_input

                box = BoxLayout(orientation="vertical", spacing=8, padding=10)
                ti = TextInput(
                    text=str(presenter.get_threshold()),
                    multiline=False,
                    input_filter="int",
                    size_hint_y=None,
                    height=40,
                )
                row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
                b_ok = MenuButton(text=t("common.save"), size_hint_x=1)
                b_cancel = MenuButton(text=t("common.cancel"), size_hint_x=1)
                row.add_widget(b_ok)
                row.add_widget(b_cancel)
                box.add_widget(Label(text=t("threshold.label"), size_hint_y=None, height=28))
                box.add_widget(ti)
                box.add_widget(row)
                pop = Popup(title=t("threshold.config_title"), content=box, size_hint=(None, None), size=(420, 220))

                def save_threshold(_x):
                    value = int(ti.text or "0")
                    presenter.set_threshold(value)
                    logger.info("Umbral actualizado: %s", value)
                    pop.dismiss()
                    refresh_status()

                b_ok.bind(on_release=save_threshold)
                b_cancel.bind(on_release=lambda _x: pop.dismiss())
                ti.bind(on_text_validate=lambda *_: save_threshold(None))
                focus_text_input(ti)
                self._open_popup_disabling_hotkeys(pop)

            def do_umbralizacion_popup(_inst=None):
                if presenter.is_digitalizing() and not presenter.is_paused():
                    return
                if presenter.is_pause_transitioning():
                    return
                if presenter.is_umbralizacion_active():
                    return

                busy = self._busy_cursor
                if busy is not None:
                    busy.show_wait()

                def _open_after_cursor(_dt):
                    self._stop_preview_pipeline()
                    err = presenter.begin_umbralizacion_preview()
                    if err:
                        presenter.end_umbralizacion_preview()
                        self._start_preview_pipeline()
                        if busy is not None:
                            busy.clear()
                        ErrorDialogs.show_error(err, title=t("umbralizacion.title"))
                        refresh_status()
                        return

                    from print_scanner_app.ui.dialogs.umbralizacion_dialog import UmbralizacionDialogs

                    def on_busy_closing():
                        if busy is not None:
                            busy.show_wait()

                    def on_open(popup):
                        self._open_popup_disabling_hotkeys(popup)
                        if busy is not None:
                            busy.clear()

                    def on_finished():
                        def _restore(_dt2):
                            try:
                                presenter.end_umbralizacion_preview()
                                self._start_preview_pipeline()
                            finally:
                                if busy is not None:
                                    busy.clear()
                                refresh_status()

                        # Dejar que el cursor wait se pinte antes de cerrar sesión.
                        Clock.schedule_once(_restore, 0)

                    UmbralizacionDialogs.open(
                        presenter,
                        on_open_popup=on_open,
                        on_busy_closing=on_busy_closing,
                        on_finished=on_finished,
                        logger=logger,
                    )

                Clock.schedule_once(_open_after_cursor, 0)

            def do_toggle_debug(_inst=None):
                enabled = presenter.toggle_debug_ui()
                logger.info("Modo debug UI: %s", "activado" if enabled else "desactivado")
                if not enabled:
                    from print_scanner_app.infrastructure.debug import close_alignment_debug_windows

                    close_alignment_debug_windows()

                def persist():
                    presenter.save_debug_capture_preference(enabled)

                threading.Thread(target=persist, daemon=True).start()
                refresh_status()

            def _restore_after_entangle_flow():
                from print_scanner_app.ui.dialogs.camera_settings_dialogs import CameraSettingsDialogs

                CameraSettingsDialogs.dismiss_saving()
                if self._busy_cursor is not None:
                    self._busy_cursor.clear()
                presenter._entangle_flow_active = False
                self.hotkeys_enabled = True
                self._bind_hotkeys()
                self._start_preview_pipeline()
                refresh_status()

            def _run_entangle_post_wait(spawn_error: str | None):
                from print_scanner_app.ui.dialogs.camera_settings_dialogs import CameraSettingsDialogs

                if spawn_error:
                    if "No se encontró" in spawn_error:
                        CameraSettingsDialogs.show_entangle_not_found(
                            on_ok=_restore_after_entangle_flow,
                        )
                    else:
                        CameraSettingsDialogs.show_entangle_error(
                            spawn_error,
                            on_ok=_restore_after_entangle_flow,
                        )
                    return

                CameraSettingsDialogs.show_saving()
                busy = self._busy_cursor
                busy.show_wait()

                def work_post():
                    result = presenter.finish_after_entangle()

                    def ui(_dt):
                        if result.needs_user_choice:

                            def on_yes():
                                r2 = presenter.continue_after_entangle_save_failure_yes()
                                if r2.preview_failed and (r2.error or "").strip():
                                    CameraSettingsDialogs.show_entangle_error(
                                        r2.error or "No se pudo reabrir preview",
                                        on_ok=_restore_after_entangle_flow,
                                    )
                                else:
                                    _restore_after_entangle_flow()

                            def on_no():
                                CameraSettingsDialogs.dismiss_saving()
                                if busy is not None:
                                    busy.clear()
                                presenter._entangle_flow_active = True
                                self._stop_preview_pipeline()
                                presenter.prepare_for_entangle()

                                def work_retry():
                                    err2 = presenter.run_entangle_wait()

                                    def ui2(_dt):
                                        _run_entangle_post_wait(err2)

                                    Clock.schedule_once(ui2, 0)

                                threading.Thread(target=work_retry, daemon=True).start()

                            CameraSettingsDialogs.show_save_failed_choice(
                                on_yes=on_yes,
                                on_no=on_no,
                            )
                            return

                        if not result.ok:
                            if (result.error or "").strip():
                                CameraSettingsDialogs.show_entangle_error(
                                    result.error or "Error tras Entangle",
                                    on_ok=_restore_after_entangle_flow,
                                )
                            else:
                                _restore_after_entangle_flow()
                            return

                        logger.info("Ajustes: Entangle completado; CONFIG_CAMARA actualizado")
                        _restore_after_entangle_flow()

                    Clock.schedule_once(ui, 0)

                threading.Thread(target=work_post, daemon=True).start()

            def do_open_settings(_inst=None):
                reason = presenter.reject_camera_settings_reason()
                if reason:
                    from print_scanner_app.ui.dialogs.camera_settings_dialogs import CameraSettingsDialogs

                    CameraSettingsDialogs.show_blocked_active_digitization()
                    return
                if presenter.is_entangle_flow_active():
                    return

                presenter._entangle_flow_active = True
                self._stop_preview_pipeline()
                presenter.prepare_for_entangle()
                self.hotkeys_enabled = False
                self._unbind_hotkeys()

                def work_wait():
                    err = presenter.run_entangle_wait()

                    def ui(_dt):
                        _run_entangle_post_wait(err)

                    Clock.schedule_once(ui, 0)

                threading.Thread(target=work_wait, daemon=True).start()

            self.handlers = {
                "start": do_start_dig,
                "pause": do_pause_dig,
                "resume": do_resume_dig,
                "stop": do_stop_dig,
                "move_1px": do_move_film_1px,
                "frame_x_frame": do_frame_x_frame,
                "change_dir": do_change_dir,
                "open_dir": do_open_dir,
                "counter": do_inc_frame,
                "edit_frame": do_set_frame,
                "settings": do_open_settings,
                "threshold": do_threshold_popup,
                "umbralizacion": do_umbralizacion_popup,
                "debug": do_toggle_debug,
                "download": do_download,
                "exit": do_exit,
                "overlay": do_toggle_overlay,
                "perforation_side": do_toggle_perforation_side,
                "format": do_set_format_popup,
            }

            bottom_row = BoxLayout(
                orientation="horizontal",
                spacing=8,
                size_hint=(None, None),
                width=470,
                height=100,
            )
            self.btn_start = MenuButton(text=t("btn.digitize"))
            self.btn_pause = MenuButton(text=t("btn.pause"))
            self.btn_move = MenuButton(text=t("btn.move_1px"))
            self.btn_frame_x_frame = MenuButton(text=t("btn.frame_x_frame"))
            self.btn_start.bind(on_release=self.handlers["start"])
            self.btn_pause.bind(on_release=self.handlers["pause"])
            self.btn_move.bind(on_release=self.handlers["move_1px"])
            self.btn_frame_x_frame.bind(on_release=self.handlers["frame_x_frame"])
            bottom_row.add_widget(self.btn_start)
            bottom_row.add_widget(self.btn_pause)
            bottom_row.add_widget(self.btn_move)
            bottom_row.add_widget(self.btn_frame_x_frame)
            bottom_anchor = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(1, None), height=100)
            bottom_anchor.add_widget(bottom_row)
            left_layout.add_widget(bottom_anchor)
            left_layout.add_widget(dl_progress)

            self.sidebar_header = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=40,
                spacing=0,
            )
            self.sidebar_toggle = MenuButton(text=">", size_hint=(None, None), width=40, height=40)
            self.sidebar_toggle.bind(on_release=do_toggle_sidebar)
            self.btn_language = MenuButton(
                text=target_language_label(),
                size_hint=(None, None),
                width=40,
                height=40,
            )
            self.btn_language.bind(on_release=do_toggle_language)
            self.sidebar.add_widget(self.sidebar_header)
            self._rebuild_sidebar_header()
            self.sidebar_buttons_layout = BoxLayout(orientation="vertical", spacing=0, padding=(0, 0, 0, 0))
            self._sidebar_specs = [
                ("sidebar.umbralizacion", "umbralizacion"),
                ("sidebar.change_dir", "change_dir"),
                ("sidebar.open_dir", "open_dir"),
                ("sidebar.counter", "counter"),
                ("sidebar.edit_frame", "edit_frame"),
                ("sidebar.settings", "settings"),
                ("sidebar.threshold", "threshold"),
                ("sidebar.debug", "debug"),
                ("sidebar.overlay", "overlay"),
                ("sidebar.format", "format"),
                ("sidebar.download", "download"),
                ("sidebar.exit", "exit"),
            ]
            self.btn_download = None
            self.btn_settings = None
            self._sidebar_action_buttons: dict[str, object] = {}
            for key_i18n, key in self._sidebar_specs:
                btn = MenuButton(text=t(key_i18n), size_hint_y=None, height=58)
                btn.bind(on_release=self.handlers[key])
                self._sidebar_action_buttons[key] = btn
                if key == "download":
                    self.btn_download = btn
                if key == "settings":
                    self.btn_settings = btn
                self.sidebar_buttons_layout.add_widget(btn)
            self.sidebar.add_widget(self.sidebar_buttons_layout)

            root.add_widget(left_layout)
            root.add_widget(self.sidebar)
            self._begin_startup_wizard()

            def poll_debug_cv_keys(_dt):
                if presenter.poll_alignment_debug_keys():
                    refresh_status()

            self._debug_key_clock = Clock.schedule_interval(poll_debug_cv_keys, 0.05)
            refresh_status()

            def finish_config_wizard_post_steps():
                # Evitar carrera preview vs assign_camera (doble claim → -53 / PTP sucio).
                if auto_startup:
                    run_startup_async(start_preview_after=True)
                else:
                    self._start_preview_pipeline()
                    Clock.schedule_once(lambda _dt: self._collapse_startup_banner(), 2.0)
                if self._format_selected:
                    self._end_startup_wizard()
                else:
                    Clock.schedule_once(lambda _dt: do_set_format_popup(), 0.12)

            def open_codigo_startup_popup(_inst=None):
                cfg = presenter._container.config_repo.load()
                prefijo = str(cfg.get("PREFIJO_ARCHIVO") or "").strip()
                actual = str(cfg.get("CODIGO_REFERENCIA") or "")
                box = BoxLayout(orientation="vertical", spacing=10, padding=12)
                box.add_widget(
                    Label(
                        text=t("session.prompt", prefijo=prefijo),
                        size_hint_y=None,
                        height=56,
                        halign="center",
                    )
                )
                from print_scanner_app.ui.textinput_paste import enable_ctrl_v_paste

                ti = TextInput(
                    text=actual,
                    multiline=False,
                    size_hint_y=None,
                    height=40,
                )
                enable_ctrl_v_paste(ti)
                row = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=44)
                b_ok = MenuButton(text=t("common.ok"), size_hint_x=1)
                row.add_widget(b_ok)
                box.add_widget(ti)
                box.add_widget(row)
                pop = Popup(
                    title=t("session.title"),
                    content=box,
                    size_hint=(None, None),
                    size=(480, 260),
                    auto_dismiss=False,
                )

                def on_ok(_x):
                    nuevo = normalized_codigo_referencia(ti.text or "")
                    if not nuevo:
                        ErrorDialogs.show_error(
                            t("session.empty_codigo"),
                            title=t("session.filename_title"),
                        )
                        return
                    cur = normalized_codigo_referencia(actual)
                    if nuevo != cur:
                        cfg2 = presenter._container.config_repo.load()
                        cfg2["CODIGO_REFERENCIA"] = nuevo
                        presenter._container.config_repo.save(cfg2)
                        logger.info("CODIGO_REFERENCIA actualizado (sesión pendientes: nuevo archivo)")
                    def _after_codigo_dismiss(_popup, *_args):
                        pop.unbind(on_dismiss=_after_codigo_dismiss)
                        self._codigo_splash_done = True
                        refresh_status()
                        finish_config_wizard_post_steps()

                    pop.bind(on_dismiss=_after_codigo_dismiss)
                    pop.dismiss()

                b_ok.bind(on_release=on_ok)
                ti.bind(on_text_validate=lambda *_: on_ok(None))
                from print_scanner_app.ui.textinput_focus import focus_text_input

                focus_text_input(ti)
                self._open_popup_disabling_hotkeys(pop)

            def advance_config_wizard(_inst=None):
                cfg = presenter._container.config_repo.load()
                if not str(cfg.get("CAMARA") or "").strip():
                    from print_scanner_app.ui.dialogs.config_startup_dialogs import ConfigStartupDialogs

                    def on_camara(value: str):
                        presenter.persist_config_key("CAMARA", value)
                        logger.info("CAMARA actualizado en config")
                        advance_config_wizard()

                    ConfigStartupDialogs.show_camara_popup(
                        current=str(cfg.get("CAMARA") or ""),
                        on_confirm=on_camara,
                        on_open=self._open_popup_disabling_hotkeys,
                    )
                    return
                if not str(cfg.get("PREFIJO_ARCHIVO") or "").strip():
                    from print_scanner_app.ui.dialogs.config_startup_dialogs import ConfigStartupDialogs

                    def on_prefijo(value: str):
                        presenter.persist_config_key("PREFIJO_ARCHIVO", value)
                        logger.info("PREFIJO_ARCHIVO actualizado en config")
                        advance_config_wizard()

                    ConfigStartupDialogs.show_prefijo_popup(
                        current=str(cfg.get("PREFIJO_ARCHIVO") or ""),
                        on_confirm=on_prefijo,
                        on_open=self._open_popup_disabling_hotkeys,
                    )
                    return
                if presenter.needs_output_directory_setup():
                    from print_scanner_app.ui.directory_prompt import prompt_output_directory

                    prompt_output_directory(
                        presenter,
                        on_success=advance_config_wizard,
                        on_open_popup=self._open_popup_disabling_hotkeys,
                        refresh_status=refresh_status,
                    )
                    return
                open_codigo_startup_popup()

            Clock.schedule_once(lambda _dt: advance_config_wizard(), 0.15)
            return root

        def _on_request_close(self, *_args):
            if self.handlers and "exit" in self.handlers:
                self.handlers["exit"]()
            return True

        def on_stop(self):
            ev = getattr(self, "_pause_preview_timeout_ev", None)
            if ev is not None:
                ev.cancel()
                self._pause_preview_timeout_ev = None
            if getattr(self, "_busy_cursor", None) is not None:
                self._busy_cursor.clear()
            presenter.end_pause_transition()
            ev = getattr(self, "_debug_key_clock", None)
            if ev is not None:
                ev.cancel()
                self._debug_key_clock = None
            presenter.close_alignment_debug_windows()
            from print_scanner_app.infrastructure.debug.opencv_alignment_windows import shutdown_alignment_debug_worker

            shutdown_alignment_debug_worker()
            self._perform_exit_cleanup()
            self._unbind_hotkeys()

        def _perform_exit_cleanup(self) -> None:
            """
            Parar preview → esperar I/O idle → join → cerrar gphoto (una sola vez).

            Orden crítico: nunca ``camera.exit()`` con ``capture_preview`` en vuelo
            en el hilo de UI (dispara el diálogo forzar/esperar del escritorio).
            """
            if getattr(self, "_exit_cleanup_done", False):
                return
            self._exit_cleanup_done = True

            from print_scanner_app.ui.presenters.app_presenter import (
                EXIT_PREVIEW_JOIN_TIMEOUT_S,
            )

            self._preview_worker_running = False
            if self._preview_render_event is not None:
                self._preview_render_event.cancel()
                self._preview_render_event = None

            try:
                presenter.wait_for_camera_idle_before_exit()
            except Exception:  # noqa: BLE001
                logger.exception("exit cleanup: wait_for_camera_idle_before_exit falló")

            thread = self._preview_worker_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=EXIT_PREVIEW_JOIN_TIMEOUT_S)
            self._preview_worker_thread = None

            try:
                presenter.release_camera_sessions_for_exit(settle=False)
            except Exception:  # noqa: BLE001
                logger.exception("exit cleanup: release_camera_sessions_for_exit falló")

            try:
                if getattr(self, "preview_image", None) is not None:
                    self._show_logo_in_preview()
            except Exception:  # noqa: BLE001
                logger.debug("exit cleanup: logo preview ignorado", exc_info=True)

        def _build_top_info_text(self) -> str:
            directory = presenter.current_directory() or t("info.no_directory")
            frame = container.app_state.frame_count if container is not None else 0
            debug_flag = "ON" if presenter.is_debug_ui_active() else "OFF"
            extra = ""
            if presenter.is_debug_ui_active():
                if presenter.is_debug_alignment_waiting():
                    extra = t("info.align_waiting")
                elif not presenter.alignment_debug_visual_available():
                    r = presenter.alignment_debug_unavailable_reason() or t("info.roi_default_reason")
                    extra = t("info.roi_unavailable", reason=r)
            return t(
                "info.line",
                directory=directory,
                frame=frame,
                fmt=presenter.get_format(),
                threshold=presenter.get_threshold(),
                debug_flag=debug_flag,
                extra=extra,
            )

        def _rebuild_sidebar_header(self):
            header = getattr(self, "sidebar_header", None)
            if header is None:
                return
            header.clear_widgets()
            toggle = self.sidebar_toggle
            lang = self.btn_language
            if getattr(toggle, "parent", None) is not None:
                toggle.parent.remove_widget(toggle)
            if getattr(lang, "parent", None) is not None:
                lang.parent.remove_widget(lang)
            if self.sidebar_expanded:
                header.orientation = "horizontal"
                header.height = 40
                header.add_widget(toggle)
                header.add_widget(Label(size_hint_x=1))
                header.add_widget(lang)
            else:
                header.orientation = "vertical"
                header.height = 80
                header.add_widget(toggle)
                header.add_widget(lang)

        def _apply_ui_language(self):
            if getattr(self, "btn_start", None) is not None:
                self.btn_start.text = t("btn.digitize")
            if getattr(self, "btn_pause", None) is not None:
                self.btn_pause.text = t("btn.pause")
            if getattr(self, "btn_move", None) is not None:
                self.btn_move.text = t("btn.move_1px")
            if getattr(self, "btn_frame_x_frame", None) is not None:
                self.btn_frame_x_frame.text = t("btn.frame_x_frame")
            if getattr(self, "btn_language", None) is not None:
                self.btn_language.text = target_language_label()
            for key_i18n, key in getattr(self, "_sidebar_specs", []) or []:
                btn = (getattr(self, "_sidebar_action_buttons", None) or {}).get(key)
                if btn is not None:
                    btn.text = t(key_i18n)
            retry = getattr(self, "btn_retry_camera", None)
            if retry is not None:
                retry.text = t("btn.retry_camera")

        def _collapse_startup_banner(self):
            if self._startup_banner_collapsed:
                return
            self._startup_banner_collapsed = True
            self.startup_line.text = ""
            self.startup_line.opacity = 0
            self.startup_line.size_hint_y = None
            self.startup_line.height = 0

        def _sync_preview_background(self, *_args):
            self._preview_bg_rect.pos = self.preview_container.pos
            self._preview_bg_rect.size = self.preview_container.size
            self._refresh_preview_panel()

        def _sync_sidebar_background(self, *_args):
            self._sidebar_bg_rect.pos = self.sidebar.pos
            self._sidebar_bg_rect.size = self.sidebar.size

        def _image_display_bbox(self):
            """
            Rectángulo donde se dibuja la textura con `fit_mode='contain'` (sin letterbox).
            Coordenadas relativas al `preview_container` (mismo espacio que canvas.after).
            Las líneas en `aplicar_cuadricula` están en píxeles de la imagen.
            """
            img = self.preview_image
            if img.texture is None:
                return None
            try:
                iw, ih = img.norm_image_size
            except Exception:  # noqa: BLE001
                iw, ih = img.size
            if iw <= 1 or ih <= 1:
                return None
            ix = img.x + (img.width - iw) * 0.5
            iy = img.y + (img.height - ih) * 0.5
            return ix, iy, iw, ih

        def _overlay_points_for_format(self, fmt: str, ix: float, iy: float, iw: float, ih: float):
            # Valores de `actualizar_cuadricula_por_formato`.
            # Solo 16mm y 35mm; 8mm/super8 usan el mismo preset que 16mm.
            # El rectángulo de perforación se espeja en X según PERFORATION_SIDE (líneas fijas).
            from print_scanner_app.domain.policies.perforation_roi import (
                OVERLAY_BASE_H,
                OVERLAY_BASE_W,
                overlay_rect_for_format,
            )

            presets = {
                "16mm": {"lines": (150, 290, 810)},
                "35mm": {"lines": (135, 240, 750)},
            }
            key = fmt if fmt in presets else "16mm"
            cfg = presets[key]
            base_w = OVERLAY_BASE_W
            base_h = OVERLAY_BASE_H
            l1 = ix + iw * (cfg["lines"][0] / base_w)
            l2 = ix + iw * (cfg["lines"][1] / base_w)
            l3 = ix + iw * (cfg["lines"][2] / base_w)
            side = presenter.get_perforation_side()
            rx1_px, ry1_top, rx2_px, ry2_top = overlay_rect_for_format(fmt, side)  # type: ignore[arg-type]
            rect_w = iw * ((rx2_px - rx1_px) / base_w)
            ry_top_max = max(ry1_top, ry2_top)
            ry_top_min = min(ry1_top, ry2_top)
            rect_h = ih * ((ry_top_max - ry_top_min) / base_h)
            rx = ix + iw * (rx1_px / base_w)
            ry_bottom = iy + ih * ((base_h - ry_top_max) / base_h)
            return l1, l2, l3, (rx, ry_bottom, max(1.0, rect_w), max(1.0, rect_h))

        def _refresh_preview_panel(self):
            self.preview_container.canvas.after.clear()
            mode = presenter.ui_main_view_mode()
            if mode == "captured":
                raw = presenter.last_captured_raw_name()
                jpeg = presenter.last_captured_preview_jpeg()
                if jpeg:
                    self._apply_jpeg_bytes_to_preview(jpeg)
                elif raw:
                    logger.info("Última captura: %s", raw)

            if mode != "preview" or not presenter.overlay_enabled():
                return
            if getattr(self, "_preview_showing_logo", False):
                return

            bbox = self._image_display_bbox()
            if bbox is None:
                return
            ix, iy, iw, ih = bbox
            x1, x2, x3, rect = self._overlay_points_for_format(presenter.get_format(), ix, iy, iw, ih)
            with self.preview_container.canvas.after:
                Color(0.1, 0.7, 1.0, 0.95)
                Line(points=[x1, iy, x1, iy + ih], width=1)
                Line(points=[x2, iy, x2, iy + ih], width=1)
                Line(points=[x3, iy, x3, iy + ih], width=1)
                Color(1.0, 0.1, 0.1, 0.95)
                rx, ry, rw, rh = rect
                Line(rectangle=(rx, ry, rw, rh), width=1.3)

        def _decode_preview_frame(self, jpeg_bytes: bytes):
            if not jpeg_bytes or PilImage is None:
                return None
            try:
                img = PilImage.open(BytesIO(jpeg_bytes)).convert("RGB")
                width, height = img.size
                return img.tobytes(), width, height
            except Exception:  # noqa: BLE001
                return None

        def _apply_rgb_frame(self, frame_bytes: bytes, width: int, height: int) -> bool:
            if not frame_bytes or width <= 0 or height <= 0:
                return False
            if getattr(self, "_preview_showing_logo", False) or self.preview_image.source:
                self.preview_image.source = ""
                self._preview_showing_logo = False
            tex = self.preview_image.texture
            if tex is None or tex.size != (width, height):
                tex = Texture.create(size=(width, height), colorfmt="rgb")
                tex.flip_vertical()
                self.preview_image.texture = tex
            tex.blit_buffer(frame_bytes, colorfmt="rgb", bufferfmt="ubyte")
            return True

        def _apply_jpeg_bytes_to_preview(self, jpeg_bytes: bytes) -> bool:
            frame = self._decode_preview_frame(jpeg_bytes)
            if frame is None:
                return False
            fb, w, h = frame
            return self._apply_rgb_frame(fb, w, h)

        def _preview_worker_loop(self):
            fps = presenter.preview_fps_target()
            interval = 1.0 / fps
            while self._preview_worker_running:
                tick_start = time.perf_counter()
                if presenter.ui_main_view_mode() == "preview":
                    t_cap0 = time.perf_counter()
                    jpeg = presenter.read_preview_jpeg()
                    t_cap1 = time.perf_counter()
                    frame = self._decode_preview_frame(jpeg) if jpeg else None
                    t_dec2 = time.perf_counter()
                    if frame:
                        with self._preview_lock:
                            self._latest_preview_frame = frame
                            self._latest_preview_token += 1
                    self._preview_worker_iter += 1
                    if logger.isEnabledFor(logging.DEBUG) and self._preview_worker_iter % 80 == 0:
                        logger.debug(
                            "preview_latency_ms capture=%.2f decode=%.2f (muestra c/80 iter)",
                            (t_cap1 - t_cap0) * 1000.0,
                            (t_dec2 - t_cap1) * 1000.0,
                        )
                else:
                    self._preview_worker_iter += 1
                elapsed = time.perf_counter() - tick_start
                if logger.isEnabledFor(logging.DEBUG) and self._preview_worker_iter % 40 == 0:
                    logger.debug(
                        "preview_worker iter=%s capture_s=%.4f sleep_budget_s=%.4f fps_target=%.1f",
                        self._preview_worker_iter,
                        elapsed,
                        max(0.01, interval - elapsed),
                        fps,
                    )
                time.sleep(max(0.01, interval - elapsed))

        def _render_preview_tick(self, _dt):
            if presenter.ui_main_view_mode() != "preview":
                return
            frame = None
            token = -1
            with self._preview_lock:
                token = self._latest_preview_token
                if token != self._last_rendered_preview_token:
                    frame = self._latest_preview_frame
            if frame is None:
                return
            frame_bytes, width, height = frame
            if self._apply_rgb_frame(frame_bytes, width, height):
                self._last_rendered_preview_token = token
                if (
                    presenter.is_pause_transitioning()
                    and token > getattr(self, "_pause_preview_baseline_token", -1)
                ):
                    complete = getattr(self, "_complete_pause_preview_transition", None)
                    if complete is not None:
                        complete()
                if not self._startup_banner_collapsed:
                    Clock.schedule_once(lambda _dt: self._collapse_startup_banner(), 0)
                self._refresh_preview_panel()

        def _show_logo_in_preview(self) -> None:
            from print_scanner_app.infrastructure.system.env_tools import project_logo_path

            path = project_logo_path()
            if not path.is_file():
                return
            self.preview_container.canvas.after.clear()
            self.preview_image.source = str(path)
            self._preview_showing_logo = True
            try:
                self.preview_image.reload()
            except Exception:  # noqa: BLE001
                pass

        def _start_preview_pipeline(self):
            if self._preview_worker_running:
                return
            self._preview_worker_running = True
            self._preview_worker_thread = threading.Thread(target=self._preview_worker_loop, daemon=True)
            self._preview_worker_thread.start()
            self._preview_render_event = Clock.schedule_interval(self._render_preview_tick, 1.0 / 30.0)

        def _stop_preview_pipeline(self, join_timeout: float = 5.0) -> None:
            self._preview_worker_running = False
            if self._preview_render_event is not None:
                self._preview_render_event.cancel()
                self._preview_render_event = None
            thread = self._preview_worker_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=join_timeout)
            self._preview_worker_thread = None
            self._show_logo_in_preview()

        def _apply_dynamic_colors(self):
            if presenter.is_debug_ui_active():
                Window.clearcolor = (0.8, 0.2, 0.2, 1)
            elif presenter.is_digitalizing() and not presenter.is_paused():
                Window.clearcolor = (0.08, 0.08, 0.08, 1)
            elif presenter.is_paused():
                Window.clearcolor = (0.13, 0.13, 0.03, 1)
            else:
                Window.clearcolor = (0.1, 0.1, 0.1, 1)

        def _refresh_download_button_state(self):
            if self.btn_download is None:
                return
            pending = presenter.pending_raw_count()
            self.btn_download.background_color = (0.75, 0.2, 0.2, 1) if pending > 0 else (1, 1, 1, 1)

        def _apply_digitization_ui_lock(self):
            """D10/D12: con digitación activa solo Pausar (p) y teclas debug OpenCV.
            Durante transición de pausa→preview: todo deshabilitado (incl. Pausar).
            """
            transitioning = presenter.is_pause_transitioning()
            active = presenter.is_digitalizing() and not presenter.is_paused()
            sidebar = getattr(self, "_sidebar_action_buttons", None) or {}
            lang_btn = getattr(self, "btn_language", None)
            if lang_btn is not None:
                lang_btn.disabled = active or i18n.has_open_popup() or transitioning
            if transitioning:
                for key, btn in sidebar.items():
                    btn.disabled = True
                if getattr(self, "btn_settings", None) is not None:
                    self.btn_settings.disabled = True
                if getattr(self, "btn_start", None) is not None:
                    self.btn_start.disabled = True
                if getattr(self, "btn_move", None) is not None:
                    self.btn_move.disabled = True
                if getattr(self, "btn_frame_x_frame", None) is not None:
                    self.btn_frame_x_frame.disabled = True
                if getattr(self, "btn_pause", None) is not None:
                    self.btn_pause.disabled = True
                return
            fxf_busy = presenter.is_frame_by_frame_busy()
            for key, btn in sidebar.items():
                btn.disabled = active
            if getattr(self, "btn_settings", None) is not None:
                self.btn_settings.disabled = active or not presenter.can_open_camera_settings()
            if getattr(self, "btn_start", None) is not None:
                self.btn_start.disabled = active
            if getattr(self, "btn_move", None) is not None:
                self.btn_move.disabled = active or fxf_busy
            if getattr(self, "btn_frame_x_frame", None) is not None:
                self.btn_frame_x_frame.disabled = active or fxf_busy
            if getattr(self, "btn_pause", None) is not None:
                self.btn_pause.disabled = False
            if not active:
                for key, btn in sidebar.items():
                    btn.disabled = False
                if self.btn_settings is not None:
                    self.btn_settings.disabled = not presenter.can_open_camera_settings()
                if getattr(self, "btn_move", None) is not None:
                    self.btn_move.disabled = fxf_busy
                if getattr(self, "btn_frame_x_frame", None) is not None:
                    self.btn_frame_x_frame.disabled = fxf_busy

        def _bind_hotkeys(self):
            if self._key_handler_bound:
                return
            Window.bind(on_key_down=self._on_key_down)
            self._key_handler_bound = True

        def _unbind_hotkeys(self):
            if not self._key_handler_bound:
                return
            Window.unbind(on_key_down=self._on_key_down)
            self._key_handler_bound = False

        def _begin_startup_wizard(self) -> None:
            self._startup_wizard_active = True
            self.hotkeys_enabled = False
            self._unbind_hotkeys()

        def _end_startup_wizard(self) -> None:
            if not self._startup_wizard_active:
                return
            self._startup_wizard_active = False
            self.hotkeys_enabled = True
            self._bind_hotkeys()

        def _open_popup_disabling_hotkeys(self, popup):
            bind_popup_tracking(popup)
            self.hotkeys_enabled = False
            self._unbind_hotkeys()

            def _restore(*_):
                if self._startup_wizard_active:
                    return
                self.hotkeys_enabled = True
                self._bind_hotkeys()

            popup.bind(on_dismiss=_restore)
            popup.open()

        def _on_key_down(self, _window, _key, _scancode, codepoint, _modifiers):
            if not self.hotkeys_enabled:
                return False
            if presenter.is_pause_transitioning():
                return False
            key = (codepoint or "").lower()
            if presenter.is_digitalizing() and not presenter.is_paused():
                if key == "p":
                    cb = self.handlers.get("pause")
                    if cb is not None:
                        cb()
                    return True
                return False
            hotkeys = {
                "z": "start",
                "c": "move_1px",
                "w": "frame_x_frame",
                "p": "pause",
                ",": "change_dir",
                "-": "open_dir",
                "+": "counter",
                "b": "edit_frame",
                "e": "settings",
                "u": "threshold",
                "y": "umbralizacion",
                "q": "exit",
                "l": "overlay",
                "k": "perforation_side",
                "d": "download",
                "g": "debug",
            }
            action = hotkeys.get(key)
            if action is None:
                return False
            cb = self.handlers.get(action)
            if cb is not None:
                cb()
            return True

    ThermalModularApp().run()
