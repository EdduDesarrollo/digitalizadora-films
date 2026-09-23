from __future__ import annotations

import gc
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

from print_scanner_app import __version__
from print_scanner_app.domain.models.film_digitize_state import Film35Subphase
from print_scanner_app.domain.policies.alignment_constants import (
    ALIGNMENT_MAX_INTENTOS,
    ALIGNMENT_SEARCH_STEP_PX,
)
from print_scanner_app.domain.policies.shot_name_prediction import (
    max_cr3_name,
    predict_next_cr3_name,
    initial_predicted_cr3_name,
)
from print_scanner_app.infrastructure.storage.config_repository import (
    NUMERO_FRAME_KEY,
    output_directory_configured,
    parse_numero_frame_value,
    resolve_output_directory,
)

from print_scanner_app.ui.i18n import t

if TYPE_CHECKING:
    from print_scanner_app.app.container import Container
    from print_scanner_app.application.dto.results import CameraAssignResult, DownloadRawsResult, SimpleOk
    from print_scanner_app.application.services.startup_service import StartupOutcome

ProgressCb = Callable[[int, int, str], None]
AlignmentTimeoutCb = Callable[[], None]
PauseUiCb = Callable[[], None]

# Ráfaga de previews de debug: for _ in range(5): capture_preview; sleep(0.01).
# Override opcional en config.json: DEBUG_PREVIEW_BURST, DEBUG_PREVIEW_BURST_SLEEP.
PREVIEW_BURST_DEFAULT = 5
PREVIEW_BURST_SLEEP_DEFAULT = 0.01

# Pausa + popup de mantenimiento impresora (`docs/PAUSAR_500_FRAMES.md`).
PRINTER_CLEAN_FRAME_INTERVAL = 500

# Tras liberar la cámara (prepare), esperar antes de Entangle (`docs/AJUSTES_ENTANGLE.md` D21).
ENTANGLE_USB_RELEASE_DELAY_S = 0.5

# Frame x Frame: esperar a que termine un capture_preview en vuelo (estrategia A, sin cerrar sesión).
FRAME_BY_FRAME_PREVIEW_IDLE_TIMEOUT_S = 2.0
FRAME_BY_FRAME_RETRY_IDLE_TIMEOUT_S = 1.0

# Descarga RAW: esperar tick de captura / preview I/O idle antes de claim USB.
RAW_DOWNLOAD_CAPTURE_IDLE_TIMEOUT_S = 5.0

# Digitación rápida: Immediate + predicción CR3 (sin capture() bloqueante).
# Prueba: sin tope/wait de unconfirmed; se encola pending hasta pausa manual o ×500.
# Sigue activa la pausa por desync (CR3 en cámara más nuevo que el esperado).
IMMEDIATE_TO_MOVE_DELAY_S = 0.5
# Tras cerrar sesiones gphoto al salir: deja asentar el USB/PTP (sin power-cycle).
# En el path de exit de UI se omite (settle=False): el sleep en el hilo principal
# dispara el diálogo "forzar/esperar" del escritorio.
CAMERA_EXIT_SETTLE_S = 0.75
EXIT_CAPTURE_TICK_IDLE_TIMEOUT_S = 2.0
EXIT_PREVIEW_IO_IDLE_TIMEOUT_S = 2.0
EXIT_PREVIEW_JOIN_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class _UnconfirmedShot:
    raw_name: str
    reserved_at: float


def _printer_lp_available() -> bool:
    """True si hay al menos un dispositivo /dev/usb/lp* (impresora térmica esperada)."""
    from print_scanner_app.infrastructure.printer.printer_device import first_lp_device

    return first_lp_device() is not None


@dataclass(frozen=True)
class DebugFrameContext:
    frame_id: int
    jpeg_bytes: bytes
    px_blancos: int
    umbral: int
    aligned: bool


@dataclass(frozen=True)
class EntangleFlowResult:
    ok: bool
    error: str | None = None
    needs_user_choice: bool = False
    spawn_failed: bool = False
    preview_failed: bool = False



def _jpg_basename_from_raw(raw_name: str) -> Optional[str]:
    """Par Canon: ``_MG_3773.CR3`` → ``_MG_3773.JPG`` (sin carpeta en pendientes)."""
    name = (raw_name or "").strip()
    if not name:
        return None
    base, _ext = os.path.splitext(name)
    if not base:
        return None
    return f"{base}.JPG"


class AppPresenter:
    """
    Presenter fino: mensajes de bienvenida y acceso a use cases vía Container.
    Sin lógica de negocio duplicada.
    """

    def __init__(
        self,
        *,
        container: Optional["Container"] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self._container = container
        self._log = logger or logging.getLogger(__name__)
        self._capture_session = None
        self._capture_folder_cache: list[str | None] = [None]
        self._jpeg_folder_cache: list[str | None] = [None]
        self._capture_last_error: str | None = None
        self._last_captured_raw_name: str = ""
        self._last_captured_preview_jpeg: bytes | None = None
        self._preview_session = None
        self._umbralizacion_active = False
        self._umbralizacion_session = None
        self._mostrar_debug_ui = False
        self._last_alignment_debug_ts = 0.0
        self._debug_alignment_waiting = False
        self._debug_capture_state: dict | None = None
        self._debug_step_requested = False
        self._debug_frame_seq = 0
        self._debug_frame_ctx: DebugFrameContext | None = None
        # True hasta mostrar el primer par de ventanas debug tras Digitalizar (o Reanudar con debug ON).
        self._debug_digitization_gate_pending = False
        # --- Alineación / film (`docs/DIFF_PRINT.md`) ---
        self._alignment_search_attempts = 0
        self._alignment_timeout_callback: AlignmentTimeoutCb | None = None
        self._film35_subphase: Film35Subphase | None = None
        self._film35_pair_index = 0
        self._film35_cycle_pattern_px: int | None = None
        self._last_printer_clean_pause_frame: int | None = None
        self._printer_clean_pending_schedule_for_frame: int | None = None
        self._printer_clean_popup_callback: Callable[[], None] | None = None
        self._printer_clean_refresh_status_callback: Callable[[], None] | None = None
        # Predicción CR3 / confirmación diferida (digitación automática + debug; no FxF).
        self._next_predicted_cr3: str | None = None
        self._unconfirmed_shots: list[_UnconfirmedShot] = []
        self._pause_transitioning = False
        self._pause_accepted_callback: PauseUiCb | None = None
        self._pause_capture_closed_callback: PauseUiCb | None = None
        self._numero_frame_lock = threading.Lock()
        self._camera_access_lock = threading.Lock()
        self._raw_download_in_progress = False
        # SET = el capture_loop puede entrar a un tick; CLEAR = descarga RAW dueña de la cámara.
        self._capture_tick_may_run = threading.Event()
        self._capture_tick_may_run.set()
        self._capture_tick_idle = threading.Condition(threading.Lock())
        self._capture_tick_running = False
        self._capture_critical_section_active = False
        self._frame_by_frame_busy = False
        self._preview_io_lock = threading.Lock()
        self._preview_io_idle = threading.Condition(self._preview_io_lock)
        self._preview_io_in_progress = False
        self._entangle_config_before: dict | None = None
        self._entangle_flow_active = False
        self._entangle_popen_factory: Callable[..., Any] | None = None
        self._entangle_sleep: Callable[[float], None] | None = None
        if container is not None:
            container.capture_service().set_on_frame_count_changed(self._on_capture_frame_count_changed)

    def hydrate_numero_frame_from_config(self) -> None:
        """
        Aplica `NUMERO_FRAME` del config a `app_state.frame_count` (paridad con UI).
        Valores inválidos → 0 y reescritura del JSON (`docs/NUMERO_FRAME_CONFIG.md`).
        """
        if self._container is None:
            return
        cfg = self._container.config_repo.load()
        raw = cfg.get(NUMERO_FRAME_KEY)
        n, needs_rewrite = parse_numero_frame_value(raw)
        self._container.app_state.frame_count = n
        if needs_rewrite:
            try:
                with self._numero_frame_lock:
                    self._container.config_repo.update_key(NUMERO_FRAME_KEY, n)
            except Exception as e:  # noqa: BLE001
                self._log.warning("NUMERO_FRAME: no se pudo normalizar config: %s", e)

    def _on_capture_frame_count_changed(self, frame_count: int) -> None:
        try:
            self._persist_numero_frame_value(frame_count)
        except Exception as e:  # noqa: BLE001
            self._log.warning("NUMERO_FRAME: persist tras captura falló: %s", e)

    def _persist_numero_frame(self) -> None:
        if self._container is None:
            return
        self._persist_numero_frame_value(self._container.app_state.frame_count)

    def _persist_numero_frame_value(self, n: int) -> None:
        if self._container is None:
            return
        n = max(0, int(n))
        with self._numero_frame_lock:
            self._container.config_repo.update_key(NUMERO_FRAME_KEY, n)

    def set_alignment_timeout_callback(self, callback: AlignmentTimeoutCb | None) -> None:
        """UI: tras timeout de alineación (p. ej. popup en hilo principal vía Clock.schedule_once)."""
        self._alignment_timeout_callback = callback

    def register_printer_clean_popup_callback(self, cb: Callable[[], None] | None) -> None:
        """Registrado desde kivy_app: abre el popup §3.13 (digitación ya pausada)."""
        self._printer_clean_popup_callback = cb

    def register_printer_clean_refresh_status_callback(self, cb: Callable[[], None] | None) -> None:
        """Registrado desde kivy_app: refresca barra de estado tras pausa por mantenimiento."""
        self._printer_clean_refresh_status_callback = cb

    def register_pause_accepted_callback(self, cb: PauseUiCb | None) -> None:
        """UI: pausa aceptada (inmediata o diferida); iniciar wait/lock."""
        self._pause_accepted_callback = cb

    def register_pause_capture_closed_callback(self, cb: PauseUiCb | None) -> None:
        """UI: sesión de captura cerrada tras pausa; armar timeout de preview."""
        self._pause_capture_closed_callback = cb

    def is_pause_transitioning(self) -> bool:
        return self._pause_transitioning

    def begin_pause_transition(self) -> None:
        self._pause_transitioning = True

    def end_pause_transition(self) -> None:
        self._pause_transitioning = False

    def _emit_pause_accepted(self) -> None:
        cb = self._pause_accepted_callback
        if cb is None:
            return
        try:
            cb()
        except Exception as e:  # noqa: BLE001
            self._log.error("pause_accepted_callback falló: %s", e)

    def _emit_pause_capture_closed(self) -> None:
        cb = self._pause_capture_closed_callback
        if cb is None:
            return
        try:
            cb()
        except Exception as e:  # noqa: BLE001
            self._log.error("pause_capture_closed_callback falló: %s", e)

    def get_last_printer_clean_pause_frame(self) -> int | None:
        return self._last_printer_clean_pause_frame

    def _reset_printer_clean_latch(self) -> None:
        self._last_printer_clean_pause_frame = None
        self._printer_clean_pending_schedule_for_frame = None

    def _reset_digitization_film_navigation(self) -> None:
        """Reinicia contadores de búsqueda y máquina 35 mm (digitación iniciada, reanudada, timeout, stop)."""
        self._alignment_search_attempts = 0
        self._film35_subphase = None
        self._film35_pair_index = 0
        self._film35_cycle_pattern_px = None
        self._next_predicted_cr3 = None
        self._unconfirmed_shots = []

    def _serial_and_config_camara(self) -> tuple[str, dict]:
        if self._container is None:
            return "", {}
        from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
            filter_camera_config_to_whitelist,
        )

        cfg = self._container.config_repo.load()
        serial = (cfg.get("CAMARA") or "").strip()
        config_cam = cfg.get("CONFIG_CAMARA") or {}
        if not isinstance(config_cam, dict):
            config_cam = {}
        return serial, filter_camera_config_to_whitelist(config_cam)

    def _camera_access_blocked(self) -> bool:
        if self._raw_download_in_progress:
            return True
        if self._frame_by_frame_busy:
            return True
        if self._umbralizacion_active:
            return True
        if self._capture_critical_section_active:
            return True
        if self._container is not None and self._container.app_state.pause_pending:
            return True
        return False

    def is_frame_by_frame_busy(self) -> bool:
        return bool(self._frame_by_frame_busy)

    def _begin_preview_io(self) -> bool:
        """
        Reserva el I/O de preview. False si la cámara está bloqueada (p. ej. Frame x Frame busy).
        Debe emparejarse siempre con ``_end_preview_io``.
        """
        with self._preview_io_idle:
            if self._camera_access_blocked():
                return False
            self._preview_io_in_progress = True
            return True

    def _end_preview_io(self) -> None:
        with self._preview_io_idle:
            self._preview_io_in_progress = False
            self._preview_io_idle.notify_all()

    def _wait_preview_io_idle(self, timeout_s: float) -> bool:
        """Espera a que no haya ``capture_preview`` / lectura preview en vuelo."""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._preview_io_idle:
            while self._preview_io_in_progress:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._preview_io_idle.wait(timeout=remaining)
            return True

    def wait_until_capture_tick_allowed(self) -> None:
        """
        Borde del ``capture_loop``: bloquea mientras hay descarga RAW
        (``_capture_tick_may_run`` en CLEAR). No aborta un tick ya en curso.
        """
        self._capture_tick_may_run.wait()

    def _begin_capture_tick(self) -> bool:
        """
        Reserva un tick de captura. False si la descarga ya bloqueó nuevos ticks.
        Debe emparejarse con ``_end_capture_tick``.
        """
        with self._capture_tick_idle:
            if not self._capture_tick_may_run.is_set():
                return False
            self._capture_tick_running = True
            return True

    def _end_capture_tick(self) -> None:
        with self._capture_tick_idle:
            self._capture_tick_running = False
            self._capture_tick_idle.notify_all()

    def _wait_capture_tick_idle(self, timeout_s: float) -> bool:
        """Espera a que termine un ``run_capture_tick`` en vuelo (sin abortarlo)."""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._capture_tick_idle:
            while self._capture_tick_running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._capture_tick_idle.wait(timeout=remaining)
            return True

    @staticmethod
    def _is_gphoto_io_in_progress_error(exc: BaseException) -> bool:
        msg = str(exc).lower()
        return "-110" in msg or "i/o in progress" in msg


    def _export_whitelist_from_active_session(self) -> dict:
        """Snapshot CONFIG whitelist desde sesión activa o JSON en disco."""
        from print_scanner_app.infrastructure.camera.camera_config_export import (
            export_camera_config_tree,
        )
        from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
            filter_camera_config_to_whitelist,
        )

        _serial, config_cam = self._serial_and_config_camara()
        session = self._capture_session or self._preview_session
        if session is not None:
            try:
                return filter_camera_config_to_whitelist(
                    export_camera_config_tree(session.camera, session.gp)
                )
            except Exception as e:  # noqa: BLE001
                self._log.warning("Snapshot CONFIG pre-Entangle desde sesión falló: %s", e)
        return dict(config_cam)

    def welcome_message(self) -> str:
        return f"Print Scanner v{__version__}"

    def config_camera_serial(self) -> str:
        if self._container is None:
            return ""
        return str(self._container.config_repo.load().get("CAMARA", "") or "").strip()

    def pending_raw_count(self) -> int:
        if self._container is None:
            return 0
        return len(self._container.raw_pending_repo.load_all())

    def current_directory(self) -> str:
        if self._container is None:
            return ""
        return resolve_output_directory(self._container.config_repo.load())

    def needs_output_directory_setup(self) -> bool:
        if self._container is None:
            return True
        return not output_directory_configured(self._container.config_repo.load())

    def persist_config_key(self, key: str, value: Any) -> bool:
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        cfg[key] = value
        cfg.pop("CARPETA_DESTINO", None)
        self._container.config_repo.save(cfg)
        return True

    def set_directory(self, directory: str) -> bool:
        if self._container is None:
            return False
        d = str(directory or "").strip()
        if not d:
            return False
        abs_path = os.path.abspath(os.path.expanduser(d))
        if not os.path.isdir(abs_path):
            return False
        return self.persist_config_key("DIRECTORIO", abs_path)

    def open_current_directory(self) -> bool:
        d = self.current_directory()
        if not d:
            return False
        try:
            subprocess.run(["xdg-open", d], check=False, capture_output=True)
            return True
        except Exception:  # noqa: BLE001
            return False

    def set_format(self, film_format: str) -> bool:
        if self._container is None:
            return False
        fmt = str(film_format or "").strip().lower()
        if fmt not in {"8mm", "super8", "16mm", "35mm"}:
            return False
        cfg = self._container.config_repo.load()
        cfg["FORMATO_DIGITALIZAR"] = fmt
        self._container.config_repo.save(cfg)
        return True

    def get_format(self) -> str:
        if self._container is None:
            return "16mm"
        cfg = self._container.config_repo.load()
        fmt = str(cfg.get("FORMATO_DIGITALIZAR", "16mm")).strip().lower() or "16mm"
        if fmt not in {"8mm", "super8", "16mm", "35mm"}:
            return "16mm"
        return fmt

    def set_overlay_enabled(self, enabled: bool) -> bool:
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        cfg["MOSTRAR_CUADRICULA"] = bool(enabled)
        self._container.config_repo.save(cfg)
        return True

    def get_threshold(self) -> int:
        if self._container is None:
            return 2000
        cfg = self._container.config_repo.load()
        raw = cfg.get("UMBRAL_PX_BLANCOS", 2000)
        try:
            return max(0, int(raw))
        except Exception:  # noqa: BLE001
            return 2000

    def set_threshold(self, value: int) -> bool:
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        cfg["UMBRAL_PX_BLANCOS"] = max(0, int(value))
        self._container.config_repo.save(cfg)
        return True

    def get_umbral_grey(self) -> int:
        """Umbral de umbralización (`UMBRAL_GREY_PERFORACION` o default)."""
        from print_scanner_app.domain.policies.perforation_roi import (
            UMBRAL_GREY_DEFAULT,
            umbral_grey_from_config,
        )

        if self._container is None:
            return UMBRAL_GREY_DEFAULT
        return umbral_grey_from_config(self._container.config_repo.load())

    def set_umbral_grey(self, value: int) -> bool:
        """Persiste ``UMBRAL_GREY_PERFORACION`` (0–255), creando la clave si no existe."""
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        cfg["UMBRAL_GREY_PERFORACION"] = max(0, min(255, int(value)))
        self._container.config_repo.save(cfg)
        return True

    def is_umbralizacion_active(self) -> bool:
        return bool(self._umbralizacion_active)

    def begin_umbralizacion_preview(self) -> str | None:
        """
        Toma la cámara en exclusiva para el popup de umbralización.

        Cierra la sesión de preview de img1. Retorna mensaje de error o None si OK.
        """
        if self._container is None:
            return t("err.no_container")
        if self.is_digitalizing() and not self.is_paused():
            return t("err.umbral_pause")
        if self._umbralizacion_active:
            return None
        self._umbralizacion_active = True
        if not self._wait_preview_io_idle(2.0):
            self._umbralizacion_active = False
            return t("err.camera_busy_preview")
        self._close_preview_session()
        if self._umbralizacion_session is not None:
            return None
        serial, config_cam = self._serial_and_config_camara()
        session, err = self._container.camera_service().open_session_for_capture(
            serial,
            config_cam,
            apply_saved_config=False,
        )
        if session is None:
            self._umbralizacion_active = False
            return err or t("err.umbral_open_camera")
        self._umbralizacion_session = session
        return None

    def read_umbralizacion_preview_jpeg(self) -> bytes | None:
        """JPEG de preview mientras el popup de umbralización tiene la sesión."""
        if self._container is None or not self._umbralizacion_active:
            return None
        if self._umbralizacion_session is None:
            return None
        try:
            return self._container.camera_service().capture_preview_jpeg(
                self._umbralizacion_session
            )
        except Exception as e:  # noqa: BLE001
            self._log.debug("umbralización preview: %s", e)
            return None

    def end_umbralizacion_preview(self) -> None:
        """Libera la sesión exclusiva y deja listo para reabrir el preview de img1."""
        if self._umbralizacion_session is not None and self._container is not None:
            try:
                self._container.camera_service().close_session(self._umbralizacion_session)
            except Exception as e:  # noqa: BLE001
                self._log.debug("close umbralización session: %s", e)
            self._umbralizacion_session = None
        self._umbralizacion_active = False
        self._try_open_preview_session()

    def get_perforation_side(self) -> str:
        if self._container is None:
            return "left"
        from print_scanner_app.domain.policies.perforation_roi import side_from_config

        return side_from_config(self._container.config_repo.load())

    def toggle_perforation_side(self) -> str | None:
        """
        Alterna left/right y persiste en config.
        Solo permitido si no hay digitalización activa (idle o pausado).
        """
        if self._container is None:
            return None
        if self.is_digitalizing() and not self.is_paused():
            return None
        from print_scanner_app.domain.policies.perforation_roi import PERFORATION_SIDE_KEY

        new_side = "right" if self.get_perforation_side() == "left" else "left"
        cfg = self._container.config_repo.load()
        cfg[PERFORATION_SIDE_KEY] = new_side
        self._container.config_repo.save(cfg)
        self._log.info("PERFORATION_SIDE=%s", new_side)
        return new_side

    def is_debug_capture_enabled(self) -> bool:
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        return bool(cfg.get("DEBUG_CAPTURA", False))

    def is_debug_ui_active(self) -> bool:
        """Modo debug visual (`mostrar_debug`); independiente del disco."""
        return self._mostrar_debug_ui

    def toggle_debug_ui(self) -> bool:
        self._mostrar_debug_ui = not self._mostrar_debug_ui
        if not self._mostrar_debug_ui:
            self._clear_alignment_debug_all()
        return self._mostrar_debug_ui

    def clear_debug_ui(self) -> None:
        self._mostrar_debug_ui = False
        self._clear_alignment_debug_all()

    def alignment_debug_visual_available(self) -> bool:
        from print_scanner_app.infrastructure.debug.opencv_capability import alignment_debug_visual_available

        return alignment_debug_visual_available()

    def alignment_debug_unavailable_reason(self) -> str | None:
        from print_scanner_app.infrastructure.debug.opencv_capability import alignment_debug_unavailable_reason

        return alignment_debug_unavailable_reason()

    def is_debug_alignment_waiting(self) -> bool:
        """True si el flujo de alineación está en espera de tecla (`DEBUG_WAITING`)."""
        return self._debug_alignment_waiting

    def _clear_alignment_debug_session(self, *, clear_ctx: bool = True) -> None:
        self._debug_alignment_waiting = False
        self._debug_capture_state = None
        if clear_ctx:
            self._debug_frame_ctx = None

    def _clear_alignment_debug_all(self) -> None:
        self._clear_alignment_debug_session()
        self._debug_step_requested = False
        self._debug_digitization_gate_pending = False

    def close_alignment_debug_windows(self) -> None:
        try:
            from print_scanner_app.infrastructure.debug import close_alignment_debug_windows as _close

            _close()
        except Exception:  # noqa: BLE001
            pass

    def poll_alignment_debug_keys(self) -> bool:
        """Teclas OpenCV: Q pausa; E reanuda un paso; R apaga debug. Retorna True si hubo acción."""
        from print_scanner_app.infrastructure.debug.opencv_alignment_windows import (
            close_alignment_debug_windows,
            poll_alignment_debug_key,
        )

        key = poll_alignment_debug_key()
        if key is None:
            return False
        if key == ord("q"):
            self.run_pause_digitization()
            close_alignment_debug_windows()
            return True
        if key == ord("e"):
            self._debug_step_requested = True
            # Conserva el frame mostrado para que E consuma ese mismo contexto.
            self._clear_alignment_debug_session(clear_ctx=False)
            self._log.info("DBG-ALIGN step_requested")
            return True
        if key == ord("r"):
            # Apaga ventanas y continúa un paso sin reabrir debug en esa vuelta.
            self._mostrar_debug_ui = False
            self._debug_step_requested = True
            self.save_debug_capture_preference(False)
            close_alignment_debug_windows()
            return True
        return False

    def save_debug_capture_preference(self, enabled: bool) -> None:
        """Persiste preferencia sin tumbar la app si falla el disco."""
        if self._container is None:
            return
        try:
            cfg = self._container.config_repo.load()
            cfg["DEBUG_CAPTURA"] = bool(enabled)
            self._container.config_repo.save(cfg)
        except Exception as e:  # noqa: BLE001
            self._log.warning("No se pudo persistir DEBUG_CAPTURA: %s", e)

    def toggle_debug_capture(self) -> bool:
        if self._container is None:
            return False
        cfg = self._container.config_repo.load()
        enabled = not bool(cfg.get("DEBUG_CAPTURA", False))
        cfg["DEBUG_CAPTURA"] = enabled
        try:
            self._container.config_repo.save(cfg)
        except Exception as e:  # noqa: BLE001
            self._log.warning("No se pudo persistir DEBUG_CAPTURA: %s", e)
        return enabled

    def can_open_camera_settings(self) -> bool:
        if self._container is None:
            return False
        if self._pause_transitioning:
            return False
        st = self._container.app_state
        if not st.digitalizing:
            return True
        return bool(st.pause_digitization)

    def reject_camera_settings_reason(self) -> str | None:
        if self.can_open_camera_settings():
            return None
        self._log.info("Ajustes bloqueado: digitación activa (use Pausar antes)")
        return t("settings.blocked")

    def is_entangle_flow_active(self) -> bool:
        return self._entangle_flow_active

    def prepare_for_entangle(self) -> None:
        """Cierra sesiones y desmonta; no cambia flags de digitación."""
        if self._container is None:
            return
        self._entangle_config_before = self._export_whitelist_from_active_session()
        self._close_preview_session()
        self._close_capture_session()
        self.close_alignment_debug_windows()
        from print_scanner_app.infrastructure.system.mount_tools import unmount_camera_mounts

        unmount_camera_mounts()

    def run_entangle_wait(self) -> str | None:
        """
        Ejecuta Entangle y espera cierre. Retorna None si OK, o mensaje de error.
        Debe llamarse desde hilo background, después de `prepare_for_entangle()` (D21).
        """
        delay = ENTANGLE_USB_RELEASE_DELAY_S
        if delay > 0:
            sleeper = self._entangle_sleep or time.sleep
            self._log.info("Entangle: espera %.1fs tras liberar cámara", delay)
            sleeper(delay)
        popen = self._entangle_popen_factory or subprocess.Popen
        try:
            proc = popen(["entangle"])  # noqa: S603,S607
            proc.wait()
            return None
        except FileNotFoundError:
            self._log.error("Entangle no encontrado en PATH")
            return t("settings.entangle_not_found")
        except Exception as e:  # noqa: BLE001
            self._log.error("Error al ejecutar Entangle: %s", e)
            return t("settings.entangle_error", error=e)

    def reset_to_espera_after_entangle(self) -> None:
        """D3: digitalizing=False, pause=False; conserva frame y RAW pendientes."""
        if self._container is None:
            return
        st = self._container.app_state
        if st.digitalizing or st.pause_digitization:
            self.run_stop_digitization()
        else:
            self._close_capture_session()
            self._clear_alignment_debug_all()

    def _try_open_preview_session(self, *, apply_saved_config: bool = False) -> None:
        if self._container is None or self._preview_session is not None:
            return
        if self._camera_access_blocked():
            return
        serial, config_cam = self._serial_and_config_camara()
        cfg_for_open = config_cam if apply_saved_config else {}
        session, err = self._container.camera_service().open_session_for_capture(
            serial,
            cfg_for_open,
            apply_saved_config=apply_saved_config,
        )
        if session is None:
            if err:
                self._log.info("preview session no disponible: %s", err)
            return
        self._preview_session = session

    def reopen_preview_after_entangle(self, *, apply_saved_config: bool = False) -> bool:
        self._close_preview_session()
        self._try_open_preview_session(apply_saved_config=apply_saved_config)
        if self._preview_session is None:
            self._log.error("No se pudo reabrir preview tras Entangle")
            return False
        return True

    def finish_after_entangle(self) -> EntangleFlowResult:
        """
        Tras cerrar Entangle: persist CONFIG_CAMARA (2 intentos), reset espera, reopen preview.
        Llamar desde hilo background.
        """
        from print_scanner_app.application.services.camera_config_persist_service import (
            CameraConfigPersistService,
        )

        if self._container is None:
            return EntangleFlowResult(ok=False, error=t("err.no_container"))

        persist_svc = CameraConfigPersistService(logger=self._log)
        serial, config_cam = self._serial_and_config_camara()
        cam_svc = self._container.camera_service()
        session, err = cam_svc.open_session_for_capture(
            serial, config_cam, unmount_first=True, apply_saved_config=False
        )
        if session is None:
            self._log.error("Persist CONFIG_CAMARA: no se abrió sesión: %s", err)
            self.reset_to_espera_after_entangle()
            return EntangleFlowResult(
                ok=False,
                error=err or t("err.open_camera_config"),
                needs_user_choice=True,
            )

        try:
            persist = persist_svc.persist_camera_config_after_entangle(
                session.camera,
                session.gp,
                self._container.config_repo,
                before_snapshot=self._entangle_config_before,
                max_attempts=2,
            )
        finally:
            cam_svc.close_session(session)

        if not persist.ok:
            self.reset_to_espera_after_entangle()
            return EntangleFlowResult(
                ok=False,
                error=persist.error,
                needs_user_choice=True,
            )

        self.reset_to_espera_after_entangle()
        self._entangle_config_before = None
        if not self.reopen_preview_after_entangle(apply_saved_config=False):
            return EntangleFlowResult(
                ok=False,
                error=t("err.reopen_preview"),
                preview_failed=True,
            )
        return EntangleFlowResult(ok=True)

    def continue_after_entangle_save_failure_yes(self) -> EntangleFlowResult:
        """D15: preview sin apply del JSON viejo."""
        self.reset_to_espera_after_entangle()
        if self.reopen_preview_after_entangle(apply_saved_config=False):
            return EntangleFlowResult(ok=True)
        return EntangleFlowResult(
            ok=False,
            error=t("err.reopen_preview"),
            preview_failed=True,
        )

    def overlay_enabled(self) -> bool:
        if self._container is None:
            return True
        cfg = self._container.config_repo.load()
        return bool(cfg.get("MOSTRAR_CUADRICULA", True))

    def toggle_overlay(self) -> bool:
        enabled = not self.overlay_enabled()
        self.set_overlay_enabled(enabled)
        return enabled

    def is_digitalizing(self) -> bool:
        if self._container is None:
            return False
        return bool(self._container.app_state.digitalizing)

    def is_paused(self) -> bool:
        if self._container is None:
            return False
        return bool(self._container.app_state.pause_digitization)

    def ui_main_view_mode(self) -> str:
        """
        Reglas de UI:
        - preview: idle o pausada
        - captured: digitalizando activa
        """
        if self.is_digitalizing() and not self.is_paused():
            return "captured"
        return "preview"

    def last_captured_raw_name(self) -> str:
        return self._last_captured_raw_name

    def last_captured_preview_jpeg(self) -> bytes | None:
        return self._last_captured_preview_jpeg

    def read_preview_jpeg(self) -> bytes | None:
        """
        Lee preview live de cámara para UI.
        Se usa cuando la vista principal está en modo `preview`.
        """
        if self._container is None or self._camera_access_blocked():
            return None
        if not self._begin_preview_io():
            return None
        try:
            # Re-chequeo: Frame x Frame pudo marcar busy entre el begin y acá.
            if self._camera_access_blocked():
                return None
            self._try_open_preview_session()
            if self._preview_session is None:
                return None
            try:
                jpeg = self._container.camera_service().capture_preview_jpeg(self._preview_session)
                if jpeg:
                    return jpeg
            except Exception:  # noqa: BLE001
                self._reopen_preview_session()
            return None
        finally:
            self._end_preview_io()

    def increment_frame(self, delta: int = 1) -> int:
        if self._container is None:
            return 0
        self._container.app_state.frame_count = max(0, self._container.app_state.frame_count + int(delta))
        try:
            self._persist_numero_frame()
        except Exception as e:  # noqa: BLE001
            self._log.warning("NUMERO_FRAME: persist falló: %s", e)
        return self._container.app_state.frame_count

    def move_film_pixels(self, pixels: int) -> "SimpleOk":
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False)
        n = max(1, int(pixels))
        ok = self._container.printer_service().move_film(n)
        return SimpleOk(ok=ok)

    def run_capture_frame_by_frame(self) -> "SimpleOk":
        """
        Disparo manual (Frame x Frame): sin alineación ni avance de film.

        Disponible en idle o digitación pausada. Reentrada mientras ``busy`` se ignora
        (``ok=True``). Encola RAW con ``observe_raw_manual`` y puede abrir el popup de
        limpieza de impresora sin llamar ``run_pause_digitization``.

        Estrategia A: no cierra la sesión de preview; marca busy, espera I/O de preview
        idle y dispara; un reintento interno ante ``[-110] I/O in progress``.
        """
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False, error=t("err.no_container"))

        # Gate corto: marca busy antes del trabajo de cámara para que reentradas
        # (y el preview worker vía `_camera_access_blocked`) se ignoren sin encolar disparos.
        with self._camera_access_lock:
            if self._frame_by_frame_busy:
                return SimpleOk(ok=True)
            if self._raw_download_in_progress:
                return SimpleOk(ok=False, error=t("err.raw_download_in_progress"))
            if self._pause_transitioning:
                return SimpleOk(ok=False, error=t("err.wait_pause"))
            if self.is_digitalizing() and not self.is_paused():
                return SimpleOk(
                    ok=False,
                    error=t("err.fxf_pause_first"),
                )
            cfg = self._container.config_repo.load()
            if not output_directory_configured(cfg):
                return SimpleOk(ok=False, error=t("err.select_output_dir"))
            self._frame_by_frame_busy = True

        try:
            if not self._wait_preview_io_idle(FRAME_BY_FRAME_PREVIEW_IDLE_TIMEOUT_S):
                self._log.warning(
                    "Frame x Frame: timeout esperando preview I/O idle (%.1fs)",
                    FRAME_BY_FRAME_PREVIEW_IDLE_TIMEOUT_S,
                )
                return SimpleOk(
                    ok=False,
                    error=t("err.camera_busy_preview"),
                )

            with self._camera_access_lock:
                if self._raw_download_in_progress:
                    return SimpleOk(ok=False, error=t("err.raw_download_in_progress"))
                session = self._capture_session or self._preview_session
                if session is None:
                    serial, config_cam = self._serial_and_config_camara()
                    session, err = self._container.camera_service().open_session_for_capture(
                        serial,
                        config_cam,
                        apply_saved_config=False,
                    )
                    if session is None:
                        return SimpleOk(
                            ok=False,
                            error=err or t("err.open_camera_capture"),
                        )
                    self._preview_session = session

                folder_cache = (
                    self._capture_folder_cache if self._capture_session is not None else [None]
                )
                observed, shoot_err = self._capture_raw_name_frame_by_frame(session, folder_cache)
                if not observed:
                    self._capture_last_error = shoot_err or t("err.capture_no_raw")
                    return SimpleOk(ok=False, error=self._capture_last_error)

                changed = self._container.capture_service().observe_raw_manual(
                    self._container.app_state,
                    observed,
                    jpg_name=_jpg_basename_from_raw(observed),
                )
                if not changed:
                    self._capture_last_error = t("err.raw_duplicate")
                    return SimpleOk(ok=False, error=self._capture_last_error)

                self._last_captured_raw_name = observed
                self._capture_last_error = None
                self._maybe_schedule_printer_clean_popup_only()
                return SimpleOk(ok=True)
        except Exception as e:  # noqa: BLE001
            self._log.error("Frame x Frame falló: %s", e)
            self._capture_last_error = str(e)
            return SimpleOk(ok=False, error=str(e))
        finally:
            self._frame_by_frame_busy = False

    def _capture_raw_name_frame_by_frame(
        self,
        session: Any,
        folder_cache: list,
    ) -> Tuple[str | None, str | None]:
        """
        Dispara still en la sesión dada. Ante ``[-110] I/O in progress`` espera idle
        otra vez y reintenta una sola vez.
        """
        assert self._container is not None
        last_err: str | None = None
        for attempt in range(2):
            try:
                observed = self._container.camera_service().capture_raw_name(session)
                if not observed:
                    observed = self._container.camera_service().find_latest_raw_name(
                        session,
                        folder_cache,
                    )
                    if observed:
                        self._log.warning(
                            "Frame x Frame: find_latest_raw_name como respaldo: %s",
                            observed,
                        )
                if observed:
                    return observed, None
                last_err = "captura sin RAW reportado"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                if attempt == 0 and self._is_gphoto_io_in_progress_error(e):
                    self._log.warning(
                        "Frame x Frame: I/O in progress en disparo; reintento tras esperar preview idle"
                    )
                    if not self._wait_preview_io_idle(FRAME_BY_FRAME_RETRY_IDLE_TIMEOUT_S):
                        return None, last_err
                    continue
                return None, last_err
            # Sin excepción pero sin RAW: no reintentar salvo que quisiéramos; un solo fallo vacío.
            break
        return None, last_err

    def get_frame(self) -> int:
        if self._container is None:
            return 0
        return int(self._container.app_state.frame_count)

    def set_frame(self, frame_value: int) -> int:
        if self._container is None:
            return 0
        self._container.app_state.frame_count = max(0, int(frame_value))
        try:
            self._persist_numero_frame()
        except Exception as e:  # noqa: BLE001
            self._log.warning("NUMERO_FRAME: persist falló: %s", e)
        return self._container.app_state.frame_count

    def capture_tick_interval_seconds(self) -> float:
        """
        Intervalo del loop de captura para UI.
        Usa `CAPTURE_TICK_SECONDS` en config.json; fallback seguro 0.4s.
        """
        if self._container is None:
            return 0.4
        cfg = self._container.config_repo.load()
        raw = cfg.get("CAPTURE_TICK_SECONDS", 0.05)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.4
        # Guard rails para evitar loop demasiado agresivo o muy lento.
        return max(0.05, min(5.0, value))

    def preview_fps_target(self) -> float:
        """
        FPS objetivo para live preview (UI).
        Configurable con `PREVIEW_FPS_TARGET`; fallback 15 FPS.
        """
        if self._container is None:
            return 15.0
        cfg = self._container.config_repo.load()
        raw = cfg.get("PREVIEW_FPS_TARGET", 15.0)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 15.0
        return max(4.0, min(30.0, value))

    def status_hint(self) -> str:
        cam = self.config_camera_serial() or t("status.no_serial")
        n = self.pending_raw_count()
        frames = self._container.app_state.frame_count if self._container is not None else 0
        if self._container is None:
            dig = t("status.dig.no_container")
        elif not self._container.app_state.digitalizing:
            dig = t("status.dig.stopped")
        elif self._container.app_state.pause_digitization:
            dig = t("status.dig.paused")
        else:
            dig = t("status.dig.active")
        line = t("status.line", cam=cam, n=n, dig=dig, frames=frames)
        if self._capture_last_error:
            line += t("status.capture_err_suffix", error=self._capture_last_error)
        return line

    def exit_via_use_case(self, *, release_camera: bool = True):
        from print_scanner_app.application.dto.results import ExitResult

        if self._container is None:
            self._log.warning("exit_app sin Container")
            return ExitResult(ok=False)
        if release_camera:
            # Sin settle en UI: el proceso está saliendo.
            self.release_camera_sessions_for_exit(settle=False)
        return self._container.exit_app_use_case().execute()

    def wait_for_camera_idle_before_exit(
        self,
        *,
        capture_idle_timeout_s: float = EXIT_CAPTURE_TICK_IDLE_TIMEOUT_S,
        preview_idle_timeout_s: float = EXIT_PREVIEW_IO_IDLE_TIMEOUT_S,
    ) -> None:
        """
        Bloquea nuevos ticks de captura y espera I/O idle (preview + tick).

        Llamar con el preview worker ya señalizado para parar
        (``_preview_worker_running=False``). No cierra sesiones: eso va
        después del ``join`` del worker.
        """
        self._capture_tick_may_run.clear()
        if not self._wait_capture_tick_idle(capture_idle_timeout_s):
            self._log.warning(
                "exit: capture tick no idle en %.1fs",
                capture_idle_timeout_s,
            )
        if not self._wait_preview_io_idle(preview_idle_timeout_s):
            self._log.warning(
                "exit: preview I/O no idle en %.1fs",
                preview_idle_timeout_s,
            )

    def release_camera_sessions_for_exit(self, *, settle: bool = True) -> None:
        """
        Cierre limpio de preview/captura al salir de la app.

        viewfinder off + exit viven en ``CameraService.close_session``; aquí
        se cierran ambas sesiones, ``gc`` y un settle corto opcional para no dejar ``-110``.
        Idempotente: si ya no hay sesión, no duerme de nuevo.
        """
        had_session = self._capture_session is not None or self._preview_session is not None
        self._close_capture_session()
        self._close_preview_session()
        self._gc_after_gphoto_session_boundary()
        if had_session and settle:
            time.sleep(CAMERA_EXIT_SETTLE_S)

    def run_startup(self, *, reset_usb_first: bool = True) -> "StartupOutcome | None":
        if self._container is None:
            return None
        serial, config_cam = self._serial_and_config_camara()
        return self._container.startup_service().run(
            expected_serial=serial,
            config_camera_json=config_cam,
            reset_usb_first=reset_usb_first,
        )

    def run_retry_camera(self) -> "CameraAssignResult":
        from print_scanner_app.application.dto.results import CameraAssignResult

        if self._container is None:
            return CameraAssignResult(ok=False, error=t("err.no_container"))
        serial, config_cam = self._serial_and_config_camara()
        return self._container.retry_camera_use_case().execute(serial, config_cam)

    def run_start_digitization(self) -> "SimpleOk":
        """
        Abre sesión de captura y deja listo el loop de ticks.

        Con UI debug activa (`toggle_debug_ui`), el presenter exige mostrar el primer par de
        ventanas OpenCV antes de cualquier `move_film` en el flujo debug (`_debug_digitization_gate_pending`).
        Esa compuerta no la aplica el hilo de captura aislado: la satisface `run_capture_tick` en modo debug.
        """
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False)
        if not _printer_lp_available():
            return SimpleOk(
                ok=False,
                error=t("err.no_printer"),
            )
        out = self._container.start_digitization_use_case().execute()
        if not out.ok:
            return out
        self._reset_digitization_film_navigation()
        self._clear_alignment_debug_all()
        self._close_preview_session()
        self._try_open_capture_session()
        if self._capture_session is None:
            self._container.stop_digitization_use_case().execute()
            self._clear_alignment_debug_all()
            self._try_open_preview_session()
            return SimpleOk(
                ok=False,
                error=t("err.open_camera_capture"),
            )
        baseline_err = self._init_cr3_prediction_baseline()
        if baseline_err:
            self._container.stop_digitization_use_case().execute()
            self._close_capture_session()
            self._clear_alignment_debug_all()
            self._try_open_preview_session()
            return SimpleOk(ok=False, error=baseline_err)
        self._last_captured_raw_name = ""
        self._last_captured_preview_jpeg = None
        if self.is_debug_ui_active():
            self._debug_digitization_gate_pending = True
        self._reset_printer_clean_latch()
        return SimpleOk(ok=True)

    def _gc_after_gphoto_session_boundary(self) -> None:
        """
        Una pasada de ``gc.collect()`` en fronteras de sesión gphoto
        (docs/260724_LIBERAR_FDs.md). No cierra ni reabre cámara.
        """
        gc.collect()

    def _finalize_deferred_pause(self) -> None:
        """
        Aplica la pausa diferida: convierte ``pause_pending`` en ``pause_digitization``
        real y cierra la sesión de captura.

        Llamar solo desde el hilo del tick, al finalizar la sección crítica, cuando
        ``app_state.pause_pending`` es True.
        """
        if self._container is None:
            return
        st = self._container.app_state
        st.pause_pending = False
        st.pause_digitization = True
        self._clear_alignment_debug_all()
        self._close_capture_session()
        self.close_alignment_debug_windows()
        self._gc_after_gphoto_session_boundary()
        self._log.info("Pausa diferida finalizada: digitación pausada tras sección crítica")
        self._emit_pause_capture_closed()

    def run_pause_digitization(self) -> "SimpleOk":
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False)

        # Si estamos en la sección crítica (disparo ya ocurrió, esperando move_film),
        # diferir la pausa para no perder el frame en Pending_raws ni desalinear el film.
        if self._capture_critical_section_active:
            if self._container.app_state.digitalizing:
                self._container.app_state.pause_pending = True
                self._log.info(
                    "Pausa solicitada durante sección crítica; se diferirá hasta el fin del tick"
                )
                self._emit_pause_accepted()
                return SimpleOk(ok=True)
            return SimpleOk(ok=False, error=t("err.digitization_inactive"))

        out = self._container.pause_digitization_use_case().execute()
        if out.ok:
            self._clear_alignment_debug_all()
            self._close_capture_session()
            self.close_alignment_debug_windows()
            self._gc_after_gphoto_session_boundary()
            self._emit_pause_accepted()
            self._emit_pause_capture_closed()
        return out

    def run_resume_digitization(self) -> "SimpleOk":
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False)
        if not _printer_lp_available():
            return SimpleOk(
                ok=False,
                error=t("err.no_printer"),
            )
        out = self._container.resume_digitization_use_case().execute()
        if not out.ok:
            return out
        self._reset_digitization_film_navigation()
        self._clear_alignment_debug_all()
        self._close_preview_session()
        self._try_open_capture_session()
        if self._capture_session is None:
            self._container.pause_digitization_use_case().execute()
            self._try_open_preview_session()
            return SimpleOk(
                ok=False,
                error=t("err.open_camera_capture"),
            )
        baseline_err = self._init_cr3_prediction_baseline()
        if baseline_err:
            self._container.pause_digitization_use_case().execute()
            self._close_capture_session()
            self._try_open_preview_session()
            return SimpleOk(ok=False, error=baseline_err)
        if self.is_debug_ui_active():
            self._debug_digitization_gate_pending = True
        return SimpleOk(ok=True)

    def run_stop_digitization(self) -> "SimpleOk":
        from print_scanner_app.application.dto.results import SimpleOk

        if self._container is None:
            return SimpleOk(ok=False)
        out = self._container.stop_digitization_use_case().execute()
        self._reset_digitization_film_navigation()
        self._reset_printer_clean_latch()
        self._clear_alignment_debug_all()
        self._close_capture_session()
        self._close_preview_session()
        self.close_alignment_debug_windows()
        self._last_captured_raw_name = ""
        self._last_captured_preview_jpeg = None
        try:
            self._persist_numero_frame()
        except Exception as e:  # noqa: BLE001
            self._log.warning("NUMERO_FRAME: persist al detener falló: %s", e)
        return out

    def _capture_tick_trace_enabled(self) -> bool:
        if self._container is None:
            return False
        return bool(self._container.config_repo.load().get("DEBUG_CAPTURE_TICK_TRACE", False))

    def run_capture_tick(self) -> bool:
        if self._container is None:
            return False
        if not self._begin_capture_tick():
            return False
        try:
            st = self._container.app_state
            if self._capture_tick_trace_enabled():
                self._log.info(
                    "CAP-TICK-TRACE digitalizing=%s paused=%s capture_session=%s debug_ui=%s "
                    "dbg_waiting=%s dbg_gate=%s unconfirmed=%s",
                    st.digitalizing,
                    st.pause_digitization,
                    self._capture_session is not None,
                    self.is_debug_ui_active(),
                    self._debug_alignment_waiting,
                    self._debug_digitization_gate_pending,
                    len(self._unconfirmed_shots),
                )
            if self._debug_alignment_waiting:
                if self._debug_step_requested:
                    # E tiene prioridad: salir de waiting para procesar el paso.
                    self._debug_alignment_waiting = False
                else:
                    if (
                        st.digitalizing
                        and not st.pause_digitization
                        and self._capture_session is not None
                    ):
                        return False
                    self._clear_alignment_debug_session()
            changed = False
            if self._capture_session is not None:
                try:
                    if self.is_debug_ui_active():
                        if self.get_format() == "35mm" and self._film35_subphase is None:
                            self._film35_subphase = Film35Subphase.FIRST_SEARCH
                        return self._run_capture_tick_debug_mode()
                    if self.get_format() == "35mm":
                        changed = self._run_capture_tick_35mm()
                    else:
                        changed = self._run_capture_tick_single_shot_format()
                except Exception as e:  # noqa: BLE001
                    self._capture_last_error = str(e)
                    self._log.warning("capture tick real falló: %s", e)
                    self._reopen_capture_session()
                    return False
            else:
                # Sin sesión de captura no se registran pendientes placeholder (CAP-*): exige cámara real.
                changed = False
            self._maybe_show_alignment_debug()
            return changed
        finally:
            self._end_capture_tick()

    def _capture_preview_for_alignment(self) -> bytes | None:
        """Ráfaga de previews; última imagen no vacía."""
        if self._container is None or self._capture_session is None:
            return None
        return self._capture_one_debug_preview_burst()

    def _pattern_pixels_for_active_capture_cycle(self) -> int:
        """
        Elemento del patrón para el ciclo de captura actual, **antes** de incrementar `frame_count`
        por el próximo disparo: `pattern[frame_count % len]` (capturas ya completadas = índice).
        """
        if self._container is None:
            return 10
        cfg = self._container.config_repo.load()
        fmt = str(cfg.get("FORMATO_DIGITALIZAR", "16mm")).strip().lower()
        pattern_key = "PRINTER_PATTERN_35MM" if fmt == "35mm" else "PRINTER_PATTERN_16MM"
        default_pattern = [22] if fmt == "35mm" else [10]
        pattern = cfg.get(pattern_key, default_pattern)
        if not isinstance(pattern, list) or not pattern:
            pattern = default_pattern
        nums: list[int] = []
        for p in pattern:
            try:
                nums.append(max(int(p), 1))
            except Exception:  # noqa: BLE001
                continue
        if not nums:
            nums = default_pattern
        fc = int(self._container.app_state.frame_count)
        idx = max(0, fc) % len(nums)
        return nums[idx]

    def _reset_alignment_attempts(self) -> None:
        self._alignment_search_attempts = 0

    def _increment_alignment_search_or_timeout(self) -> bool:
        """True si se disparó timeout (digitación pausada)."""
        self._alignment_search_attempts += 1
        if self._alignment_search_attempts >= ALIGNMENT_MAX_INTENTOS:
            self._trigger_alignment_timeout()
            return True
        return False

    def _trigger_alignment_timeout(self) -> None:
        self._log.warning("Alineación: timeout tras %s intentos", ALIGNMENT_MAX_INTENTOS)
        self._reset_digitization_film_navigation()
        self.run_pause_digitization()
        cb = self._alignment_timeout_callback
        if cb is not None:
            try:
                cb()
            except Exception as e:  # noqa: BLE001
                self._log.error("alignment_timeout_callback falló: %s", e)

    def _move_film_printer_px(self, px: int) -> bool:
        if self._container is None:
            return False
        if self._debug_digitization_gate_pending:
            self._capture_last_error = t("capture.wait_debug_frame")
            return False
        px = max(1, int(px))
        ok = self._container.printer_service().move_film(px)
        if not ok:
            self._capture_last_error = t("capture.move_film_fail")
            self.run_pause_digitization()
        return ok

    def _init_cr3_prediction_baseline(self) -> str | None:
        """
        Lee último CR3 en tarjeta (+ último pendiente en disco) y fija ``_next_predicted_cr3``.
        Sin CR3 conocidos (tarjeta vacía y sin pendientes) → ``_MG_0001.CR3``.
        Retorna mensaje de error o None si OK.
        """
        if self._container is None or self._capture_session is None:
            return t("err.baseline_no_session")
        cam_latest = self._container.camera_service().find_latest_raw_name(
            self._capture_session,
            self._capture_folder_cache,
        )
        pending_latest: str | None = None
        try:
            blocks = self._container.raw_pending_repo.load_blocks()
            if blocks:
                pending_latest = (blocks[-1].raw_name or "").strip() or None
        except Exception as e:  # noqa: BLE001
            self._log.warning("baseline CR3: no se pudo leer pendientes: %s", e)
        baseline = max_cr3_name(cam_latest, pending_latest)
        nxt = initial_predicted_cr3_name(cam_latest, pending_latest)
        if not nxt:
            if baseline:
                return t("err.predict_cr3_from", baseline=baseline)
            return t("err.predict_cr3")
        self._next_predicted_cr3 = nxt
        self._unconfirmed_shots = []
        self._log.info(
            "CR3 baseline=%s next_predicted=%s",
            baseline or "(vacío→_MG_0001)",
            nxt,
        )
        return None

    def _try_confirm_unconfirmed_shots(self) -> None:
        """Sondeo USB-safe: confirma la cabeza FIFO si el CR3 predicho ya está en tarjeta."""
        if (
            self._container is None
            or self._capture_session is None
            or not self._unconfirmed_shots
        ):
            return
        head = self._unconfirmed_shots[0]
        exists = self._container.camera_service().raw_name_exists_on_card(
            self._capture_session,
            head.raw_name,
            self._capture_folder_cache,
        )
        if not exists:
            # Desync duro: un CR3 más nuevo que el predicho sin que exista el esperado.
            latest = self._container.camera_service().find_latest_raw_name(
                self._capture_session,
                self._capture_folder_cache,
            )
            from print_scanner_app.domain.policies.shot_name_prediction import cr3_sequence_number

            exp_n = cr3_sequence_number(head.raw_name)
            got_n = cr3_sequence_number(latest)
            if exp_n is not None and got_n is not None and got_n > exp_n:
                self._capture_last_error = t(
                    "capture.desync_cr3", expected=head.raw_name, latest=latest
                )
                self._log.error("%s", self._capture_last_error)
                self.run_pause_digitization()
            return
        self._unconfirmed_shots.pop(0)
        self._log.info(
            "CR3 confirmado en tarjeta: %s (unconfirmed=%s)",
            head.raw_name,
            len(self._unconfirmed_shots),
        )

    def _shoot_immediate_predicted_and_advance(self, *, move_px: int | None = None) -> bool:
        """
        Viewfinder off → ``camera.capture()`` → observe_raw(nombre real) → move → live view UI.

        Usa ``capture()`` (no Immediate) para que el still persista en SD tras live view.
        La predicción solo fija el nombre esperado previo; el pending usa el RAW reportado.

        ``move_px``: si se pasa, usa ese avance (35 mm); si None, patrón single-shot.
        """
        if self._container is None or self._capture_session is None:
            return False
        self._try_confirm_unconfirmed_shots()
        if self._container.app_state.pause_digitization:
            return False
        predicted = (self._next_predicted_cr3 or "").strip()
        if not predicted:
            self._capture_last_error = t("capture.no_cr3_prediction")
            self.run_pause_digitization()
            return False

        trace = self._capture_tick_trace_enabled()
        t0 = time.perf_counter() if trace else 0.0
        try:
            observed = self._container.camera_service().capture_raw_name(
                self._capture_session
            )
        except Exception as e:  # noqa: BLE001
            self._capture_last_error = str(e)
            self._log.warning("capture() en digitación falló: %s", e)
            self.run_pause_digitization()
            if trace:
                self._log_post_align_timing(t0=t0, t_after_capture=time.perf_counter())
            return False
        t_cap = time.perf_counter() if trace else 0.0
        raw_name = (observed or "").strip()
        if not raw_name:
            self._capture_last_error = t("capture.immediate_fail")
            self.run_pause_digitization()
            if trace:
                self._log_post_align_timing(t0=t0, t_after_capture=t_cap)
            return False
        if raw_name.casefold() != predicted.casefold():
            self._log.info(
                "Digitación: RAW reportado=%s (predicho=%s)",
                raw_name,
                predicted,
            )

        self._capture_last_error = None
        self._last_captured_raw_name = raw_name
        self._capture_critical_section_active = True
        changed = False
        t_obs = t_move = t_prev = None
        try:
            changed = self._container.capture_service().observe_raw(
                self._container.app_state,
                raw_name,
                jpg_name=_jpg_basename_from_raw(raw_name),
                allow_when_paused=True,
            )
            if trace:
                t_obs = time.perf_counter()
            if not changed:
                self._capture_last_error = t("err.raw_duplicate_immediate")
                self.run_pause_digitization()
                return False

            self._unconfirmed_shots.append(
                _UnconfirmedShot(raw_name=raw_name, reserved_at=time.monotonic())
            )
            nxt = predict_next_cr3_name(raw_name)
            self._next_predicted_cr3 = nxt
            if self._capture_tick_trace_enabled():
                self._log.info(
                    "CAP-TICK-TRACE capture raw=%s unconfirmed=%s next=%s",
                    raw_name,
                    len(self._unconfirmed_shots),
                    nxt,
                )

            time.sleep(IMMEDIATE_TO_MOVE_DELAY_S)

            if move_px is not None:
                moved = self._move_film_printer_px(move_px)
            else:
                moved = self._advance_film_after_capture()
            if trace:
                t_move = time.perf_counter()
            if not moved:
                return False

            self._try_confirm_unconfirmed_shots()
            self._refresh_liveview_preview_after_capture()
            if trace:
                t_prev = time.perf_counter()
            if not self._container.app_state.pause_pending:
                self._maybe_schedule_printer_clean_maintenance()
        finally:
            self._capture_critical_section_active = False
            if trace:
                self._log_post_align_timing(
                    t0=t0,
                    t_after_capture=t_cap,
                    t_after_observe=t_obs,
                    t_after_move=t_move,
                    t_after_preview=t_prev,
                )
            if self._container is not None and self._container.app_state.pause_pending:
                self._finalize_deferred_pause()
        return changed

    def _refresh_liveview_preview_after_capture(self) -> None:
        """Live view post-disparo para UI (modo captured); no bloquea el move si se llama después."""
        if self._container is None or self._capture_session is None:
            return
        try:
            self._last_captured_preview_jpeg = self._container.camera_service().capture_preview_jpeg(
                self._capture_session
            )
        except Exception:  # noqa: BLE001
            self._last_captured_preview_jpeg = None

    def _pause_after_capture_without_raw_name(self) -> None:
        self._capture_last_error = t("err.capture_no_raw_fallback")
        self.run_pause_digitization()

    def _log_post_align_timing(
        self,
        *,
        t0: float,
        t_after_capture: float,
        t_after_observe: float | None = None,
        t_after_move: float | None = None,
        t_after_preview: float | None = None,
    ) -> None:
        if not self._capture_tick_trace_enabled():
            return
        parts = [f"dt_capture={t_after_capture - t0:.3f}"]
        if t_after_observe is not None:
            parts.append(f"dt_observe={t_after_observe - t_after_capture:.3f}")
        if t_after_move is not None and t_after_observe is not None:
            parts.append(f"dt_move={t_after_move - t_after_observe:.3f}")
        if t_after_preview is not None and t_after_move is not None:
            parts.append(f"dt_preview={t_after_preview - t_after_move:.3f}")
        end = t_after_preview or t_after_move or t_after_observe or t_after_capture
        parts.append(f"total={end - t0:.3f}")
        self._log.info("CAP-TICK-TRACE post-align %s", " ".join(parts))

    def _execute_capture_after_alignment(self) -> bool:
        return self._shoot_immediate_predicted_and_advance(move_px=None)

    def _run_capture_tick_single_shot_format(self) -> bool:
        """16 mm, 8 mm, super8: un disparo por ciclo (`DIFF_PRINT.md`)."""
        if self._container is None or self._capture_session is None:
            return False
        if self._container.app_state.pause_digitization:
            return False
        self._try_confirm_unconfirmed_shots()
        jpeg = self._capture_preview_for_alignment()
        if not jpeg:
            self._capture_last_error = t("capture.no_preview_align")
            if self._increment_alignment_search_or_timeout():
                return False
            self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
            return False
        self._last_captured_preview_jpeg = jpeg
        result = self._analyze_alignment_from_jpeg(jpeg)
        if result is None:
            self._capture_last_error = t("capture.align_analyze_fail")
            if self._increment_alignment_search_or_timeout():
                return False
            self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
            return False
        if result.aligned:
            self._reset_alignment_attempts()
            return self._execute_capture_after_alignment()
        self._capture_last_error = t(
            "capture.not_aligned",
            white_pixel_count=result.white_pixel_count,
            threshold=self.get_threshold(),
        )
        if self._increment_alignment_search_or_timeout():
            return False
        self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
        return False

    def _execute_35mm_first_shot_after_alignment(self) -> bool:
        if self._container is None or self._capture_session is None:
            return False
        if self._film35_cycle_pattern_px is None:
            self._film35_cycle_pattern_px = self._pattern_pixels_for_active_capture_cycle()
        px = self._film35_cycle_pattern_px
        changed = self._shoot_immediate_predicted_and_advance(move_px=px)
        if changed and not (
            self._container is not None and self._container.app_state.pause_digitization
        ):
            self._film35_subphase = Film35Subphase.MID_SEARCH
            self._film35_pair_index = 0
            self._reset_alignment_attempts()
        return changed

    def _tick35_first_search(self) -> bool:
        jpeg = self._capture_preview_for_alignment()
        if not jpeg:
            self._capture_last_error = t("capture.no_preview_align")
            if self._increment_alignment_search_or_timeout():
                return False
            self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
            return False
        self._last_captured_preview_jpeg = jpeg
        result = self._analyze_alignment_from_jpeg(jpeg)
        if result is None:
            self._capture_last_error = t("capture.align_analyze_fail")
            if self._increment_alignment_search_or_timeout():
                return False
            self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
            return False
        if result.aligned:
            self._reset_alignment_attempts()
            self._film35_cycle_pattern_px = self._pattern_pixels_for_active_capture_cycle()
            return self._execute_35mm_first_shot_after_alignment()
        self._capture_last_error = t(
            "capture.not_aligned",
            white_pixel_count=result.white_pixel_count,
            threshold=self.get_threshold(),
        )
        if self._increment_alignment_search_or_timeout():
            return False
        self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
        return False

    def _tick35_mid_search(self) -> bool:
        jpeg = self._capture_preview_for_alignment()
        if not jpeg:
            return False
        self._last_captured_preview_jpeg = jpeg
        result = self._analyze_alignment_from_jpeg(jpeg)
        if result is None:
            if self._increment_alignment_search_or_timeout():
                return False
            self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
            return False
        if result.aligned:
            self._reset_alignment_attempts()
            px = self._film35_cycle_pattern_px
            if px is None:
                px = self._pattern_pixels_for_active_capture_cycle()
            # Sección crítica: move_film de MID_SEARCH + actualización de estado.
            # Una pausa solicitada aquí se diferirá hasta el fin del bloque.
            self._capture_critical_section_active = True
            try:
                if not self._move_film_printer_px(px):
                    return False
                self._try_confirm_unconfirmed_shots()
                self._film35_pair_index += 1
                if self._film35_pair_index >= 3:
                    self._film35_subphase = Film35Subphase.FIRST_SEARCH
                    self._film35_cycle_pattern_px = None
                self._reset_alignment_attempts()
            finally:
                self._capture_critical_section_active = False
                if self._container is not None and self._container.app_state.pause_pending:
                    self._finalize_deferred_pause()
            return False
        self._capture_last_error = t(
            "capture.not_aligned",
            white_pixel_count=result.white_pixel_count,
            threshold=self.get_threshold(),
        )
        if self._increment_alignment_search_or_timeout():
            return False
        self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
        return False

    def _run_capture_tick_35mm(self) -> bool:
        if self._container is None or self._capture_session is None:
            return False
        if self._container.app_state.pause_digitization:
            return False
        if self._film35_subphase is None:
            self._film35_subphase = Film35Subphase.FIRST_SEARCH
        if self._film35_subphase == Film35Subphase.FIRST_SEARCH:
            return self._tick35_first_search()
        if self._film35_subphase == Film35Subphase.MID_SEARCH:
            return self._tick35_mid_search()
        return False

    def _run_capture_tick_debug_mode(self) -> bool:
        """Contrato debug: iteración controlada por tecla E sobre el frame mostrado."""
        if self._container is None or self._capture_session is None:
            return False
        if self._container.app_state.pause_digitization:
            return False
        if self._debug_step_requested:
            return self._process_debug_step()
        # Sin tecla E: si no hay contexto, mostrar uno inicial y esperar.
        if not self._debug_alignment_waiting:
            self._build_and_show_debug_context()
        return False

    def _process_debug_step(self) -> bool:
        if self._container is None or self._capture_session is None:
            return False
        ctx = self._debug_frame_ctx
        self._debug_step_requested = False
        self._debug_alignment_waiting = False
        if ctx is None or self._debug_digitization_gate_pending:
            self._build_and_show_debug_context()
            return False
        # La decisión se toma sobre el mismo frame mostrado.
        if ctx.aligned:
            fmt = self.get_format()
            if fmt == "35mm" and self._film35_subphase == Film35Subphase.MID_SEARCH:
                self._log.info("DBG-ALIGN35 mid pair pattern frame_id=%s", ctx.frame_id)
                px = self._film35_cycle_pattern_px or self._pattern_pixels_for_active_capture_cycle()
                # Sección crítica debug MID_SEARCH
                self._capture_critical_section_active = True
                try:
                    if not self._retry_move_film(px):
                        return False
                    self._film35_pair_index += 1
                    if self._film35_pair_index >= 3:
                        self._film35_subphase = Film35Subphase.FIRST_SEARCH
                        self._film35_cycle_pattern_px = None
                finally:
                    self._capture_critical_section_active = False
                    if self._container is not None and self._container.app_state.pause_pending:
                        self._finalize_deferred_pause()
                        return False
                self._build_and_show_debug_context()
                return False
            self._log.info("DBG-ALIGN aligned shoot_allowed frame_id=%s", ctx.frame_id)
            if fmt == "35mm" and self._film35_subphase == Film35Subphase.FIRST_SEARCH:
                self._film35_cycle_pattern_px = self._pattern_pixels_for_active_capture_cycle()
            if fmt == "35mm":
                px = self._film35_cycle_pattern_px or self._pattern_pixels_for_active_capture_cycle()
                changed = self._shoot_immediate_predicted_and_advance(move_px=px)
                if changed and self._container is not None and not self._container.app_state.pause_digitization:
                    self._film35_subphase = Film35Subphase.MID_SEARCH
                    self._film35_pair_index = 0
            else:
                changed = self._shoot_immediate_predicted_and_advance(move_px=None)
            if changed:
                self._build_and_show_debug_context()
            return changed
        self._log.info("DBG-ALIGN not_aligned shoot_blocked frame_id=%s", ctx.frame_id)
        if not self._retry_move_film(ALIGNMENT_SEARCH_STEP_PX):
            return False
        self._try_confirm_unconfirmed_shots()
        self._build_and_show_debug_context()
        return False

    def _should_trigger_capture_from_alignment(self) -> bool:
        """
        Antes de disparar RAW, valida alineación por ROI.

        Reservado para tests / callers legacy; el loop real usa `_run_capture_tick_*`.
        """
        if self._container is None or self._capture_session is None:
            return True
        try:
            jpeg = self._capture_preview_for_alignment()
        except Exception:  # noqa: BLE001
            return True
        if not jpeg:
            return True
        self._last_captured_preview_jpeg = jpeg
        result = self._analyze_alignment_from_jpeg(jpeg)
        if result is None:
            return True
        if result.aligned:
            self._debug_step_requested = False
            return True
        self._capture_last_error = t(
            "capture.not_aligned",
            white_pixel_count=result.white_pixel_count,
            threshold=self.get_threshold(),
        )
        if self.is_debug_ui_active():
            if not self._debug_step_requested:
                self._run_alignment_debug_visualization(jpeg)
                if self._debug_alignment_waiting:
                    self._log.info("DBG-ALIGN waiting_on")
                    return False
            else:
                self._debug_step_requested = False
                self._log.info("DBG-ALIGN continue_after_step")
                self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
                self._refresh_debug_preview_after_step()
                return False
        self._advance_film_for_realign(step_px=ALIGNMENT_SEARCH_STEP_PX)
        return False

    def _build_and_show_debug_context(self) -> bool:
        if self._container is None or self._capture_session is None:
            return False
        jpeg = self._retry_capture_preview()
        if not jpeg:
            return False
        self._last_captured_preview_jpeg = jpeg
        result = self._analyze_alignment_from_jpeg(jpeg)
        if result is None:
            return False
        self._debug_frame_seq += 1
        ctx = DebugFrameContext(
            frame_id=self._debug_frame_seq,
            jpeg_bytes=jpeg,
            px_blancos=int(result.white_pixel_count),
            umbral=self.get_threshold(),
            aligned=bool(result.aligned),
        )
        self._debug_frame_ctx = ctx
        self._log.info(
            "DBG-ALIGN frame_id=%s px=%s umbral=%s aligned=%s",
            ctx.frame_id,
            ctx.px_blancos,
            ctx.umbral,
            ctx.aligned,
        )
        showed = self._run_alignment_debug_visualization(jpeg)
        if showed:
            self._debug_alignment_waiting = True
            self._debug_digitization_gate_pending = False
            self._log.info("DBG-ALIGN waiting_on frame_id=%s", ctx.frame_id)
        return showed

    def _capture_one_debug_preview_burst(self) -> bytes | None:
        """
        Una ráfaga de previews (última imagen ganadora).

        Call sites debug: `_build_and_show_debug_context` -> `_retry_capture_preview`;
        `_refresh_debug_preview_after_step` -> `_retry_capture_preview(max_attempts=1)`;
        `_maybe_show_alignment_debug` (fallback si no hay JPEG en cache).
        Modo automático: `_capture_preview_for_alignment` / `_run_capture_tick_*`.
        """
        if self._container is None or self._capture_session is None:
            return None
        cfg = self._container.config_repo.load()
        try:
            burst = int(cfg.get("DEBUG_PREVIEW_BURST", PREVIEW_BURST_DEFAULT))
        except Exception:  # noqa: BLE001
            burst = PREVIEW_BURST_DEFAULT
        burst = max(1, min(10, burst))
        try:
            burst_sleep = float(cfg.get("DEBUG_PREVIEW_BURST_SLEEP", PREVIEW_BURST_SLEEP_DEFAULT))
        except Exception:  # noqa: BLE001
            burst_sleep = PREVIEW_BURST_SLEEP_DEFAULT
        burst_sleep = max(0.0, min(0.05, burst_sleep))
        latest: bytes | None = None
        for i in range(burst):
            jpeg = self._container.camera_service().capture_preview_jpeg(self._capture_session)
            if jpeg:
                latest = jpeg
            if i < burst - 1 and burst_sleep > 0:
                time.sleep(burst_sleep)
        return latest

    def _retry_capture_preview(self, max_attempts: int = 10) -> bytes | None:
        if self._container is None or self._capture_session is None:
            return None
        last_err: Exception | None = None
        for _ in range(max_attempts):
            try:
                latest = self._capture_one_debug_preview_burst()
                if latest:
                    return latest
            except Exception as e:  # noqa: BLE001
                last_err = e
        self._capture_last_error = t("capture.hw_preview", max_attempts=max_attempts)
        if last_err is not None:
            self._log.error("capture_preview falló tras reintentos: %s", last_err)
        return None

    def _retry_capture_raw_name(self, max_attempts: int = 10) -> str | None:
        last_err: Exception | None = None
        for _ in range(max_attempts):
            try:
                observed = self._trigger_and_read_raw_name()
                if observed:
                    return observed
            except Exception as e:  # noqa: BLE001
                last_err = e
        self._capture_last_error = t("capture.hw_shoot", max_attempts=max_attempts)
        if last_err is not None:
            self._log.error("capture_raw_name falló tras reintentos: %s", last_err)
        return None

    def _retry_move_film(self, px: int, max_attempts: int = 10) -> bool:
        if self._container is None:
            return False
        if self._debug_digitization_gate_pending:
            self._capture_last_error = t("capture.wait_debug_frame")
            self._log.debug("DBG-ALIGN move_film bloqueado (gate primer frame)")
            return False
        px = max(1, int(px))
        for _ in range(max_attempts):
            ok = self._container.printer_service().move_film(px)
            if ok:
                self._log.info("DBG-ALIGN step_applied move_px=%s", px)
                return True
        self._capture_last_error = t("capture.hw_move", max_attempts=max_attempts)
        self._log.error("move_film falló tras %s reintentos", max_attempts)
        return False

    def _analyze_alignment_from_jpeg(self, jpeg_bytes: bytes):
        from io import BytesIO

        from PIL import Image

        from print_scanner_app.domain.policies.perforation_alignment import analyze_perforation_alignment
        from print_scanner_app.domain.policies.perforation_roi import (
            roi_from_config,
            side_from_config,
            umbral_grey_from_config,
            w_rail_from_config,
            w_rail_max_from_config,
        )

        try:
            img = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        except Exception:  # noqa: BLE001
            return None
        cfg = self._container.config_repo.load() if self._container else {}
        fmt = self.get_format()
        y_roi = roi_from_config(cfg, fmt)
        ug = umbral_grey_from_config(cfg)
        ut = self.get_threshold()
        side = side_from_config(cfg)
        w_rail = w_rail_from_config(cfg, fmt)
        w_rail_max = w_rail_max_from_config(cfg, fmt, w_rail=w_rail)
        return analyze_perforation_alignment(
            img,
            y_roi,
            umbral_grey=ug,
            umbral_px_blancos=ut,
            side=side,
            w_rail=w_rail,
            w_rail_max=w_rail_max,
        )

    def _advance_film_for_realign(self, *, step_px: int | None = None) -> None:
        if self._container is None:
            return
        px = max(1, int(step_px)) if step_px is not None else self._printer_pixels_for_frame()
        ok = self._container.printer_service().move_film(px)
        if not ok:
            self._capture_last_error = t("capture.realign_move_fail")
            return
        self._log.info("DBG-ALIGN step_applied move_px=%s", px)
        # Ventana USB libre tras move: sondear CR3 pendientes de confirmar.
        self._try_confirm_unconfirmed_shots()

    def _refresh_debug_preview_after_step(self) -> None:
        if self._container is None or self._capture_session is None:
            return
        jpeg = self._retry_capture_preview(max_attempts=1)
        if not jpeg:
            return
        self._last_captured_preview_jpeg = jpeg
        self._log.info("DBG-ALIGN loop_preview_recaptured")
        self._run_alignment_debug_visualization(jpeg)

    def _maybe_show_alignment_debug(self) -> None:
        if not self.is_debug_ui_active():
            return
        if self._container is None:
            return
        st = self._container.app_state
        if not st.digitalizing or st.pause_digitization:
            return
        if self._capture_session is None:
            return
        now = time.monotonic()
        if now - self._last_alignment_debug_ts < 0.22:
            return
        jpeg = self._last_captured_preview_jpeg
        if not jpeg:
            try:
                jpeg = self._capture_one_debug_preview_burst()
            except Exception:  # noqa: BLE001
                return
        if not jpeg:
            return
        self._last_alignment_debug_ts = now
        self._run_alignment_debug_visualization(jpeg)

    def _run_alignment_debug_visualization(self, jpeg_bytes: bytes) -> bool:
        from io import BytesIO

        from PIL import Image

        from print_scanner_app.domain.policies.perforation_alignment import analyze_perforation_alignment
        from print_scanner_app.domain.policies.perforation_roi import (
            roi_from_config,
            side_from_config,
            umbral_grey_from_config,
            w_rail_from_config,
            w_rail_max_from_config,
        )
        from print_scanner_app.infrastructure.debug.opencv_alignment_windows import show_alignment_debug_windows

        try:
            img = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        except Exception:  # noqa: BLE001
            return False
        cfg = self._container.config_repo.load() if self._container else {}
        fmt = self.get_format()
        y_roi = roi_from_config(cfg, fmt)
        ug = umbral_grey_from_config(cfg)
        ut = self.get_threshold()
        side = side_from_config(cfg)
        w_rail = w_rail_from_config(cfg, fmt)
        w_rail_max = w_rail_max_from_config(cfg, fmt, w_rail=w_rail)
        res = analyze_perforation_alignment(
            img,
            y_roi,
            umbral_grey=ug,
            umbral_px_blancos=ut,
            side=side,
            w_rail=w_rail,
            w_rail_max=w_rail_max,
        )
        showed = show_alignment_debug_windows(
            img, y_roi, res, umbral_grey=ug, logger=self._log
        )
        if showed and self.alignment_debug_visual_available():
            self._debug_alignment_waiting = True
            self._debug_capture_state = {"phase": "alignment_debug", "t": time.monotonic()}
        return showed

    def _try_open_capture_session(self) -> None:
        if self._container is None or self._capture_session is not None:
            return
        if self._camera_access_blocked():
            return
        serial, config_cam = self._serial_and_config_camara()
        session, err = self._container.camera_service().open_session_for_capture(
            serial,
            config_cam,
            apply_saved_config=False,
        )
        if session is None:
            if err:
                self._log.info("capture session no disponible: %s", err)
            return
        self._capture_session = session
        self._capture_folder_cache = [None]
        self._capture_last_error = None

    def _close_capture_session(self) -> None:
        if self._capture_session is None:
            return
        self._container.camera_service().close_session(self._capture_session)
        self._capture_session = None
        self._capture_folder_cache = [None]

    def _close_preview_session(self) -> None:
        if self._preview_session is None:
            return
        self._container.camera_service().close_session(self._preview_session)
        self._preview_session = None

    def _reopen_preview_session(self) -> None:
        self._close_preview_session()
        self._try_open_preview_session()

    def reopen_camera_preview_after_download(self) -> None:
        """Tras una descarga RAW la sesión USB se cerró; reabre el live preview si aplica."""
        self._reopen_preview_session()

    def _read_latest_raw_name(self) -> str | None:
        if self._capture_session is None:
            return None
        name = self._container.camera_service().find_latest_raw_name(
            self._capture_session,
            self._capture_folder_cache,
        )
        return name

    def _trigger_and_read_raw_name(self) -> str | None:
        """
        Dispara still y obtiene nombre RAW.

        El fallback acotado (si ``capture()`` no reporta nombre) vive en
        ``trigger_capture_and_get_raw_name`` / ``resolve_raw_name_after_capture``.
        No se hace un segundo walk aquí.
        """
        if self._capture_session is None or self._container is None:
            return None
        name = self._container.camera_service().capture_raw_name(self._capture_session)
        return (name or "").strip() or None

    def _reopen_capture_session(self) -> None:
        self._close_capture_session()
        self._try_open_capture_session()

    def _printer_clean_maintenance_due(self, fc: int) -> bool:
        if self.is_debug_ui_active():
            return False
        if fc <= 0 or fc % PRINTER_CLEAN_FRAME_INTERVAL != 0:
            return False
        if self._last_printer_clean_pause_frame == fc:
            return False
        if self._printer_clean_pending_schedule_for_frame == fc:
            return False
        return True

    def _emit_printer_clean_popup(self, fc: int) -> None:
        """Latch + refresh + popup de limpieza (sin mutar flags de digitación)."""
        self._last_printer_clean_pause_frame = fc
        rs = self._printer_clean_refresh_status_callback
        if rs is not None:
            try:
                rs()
            except Exception as e:  # noqa: BLE001
                self._log.debug("refresh_status tras mantenimiento impresora: %s", e)
        cb = self._printer_clean_popup_callback
        if cb is not None:
            try:
                cb()
            except Exception as e:  # noqa: BLE001
                self._log.error("popup limpieza impresora: %s", e)
        else:
            self._log.warning("Popup de limpieza de impresora no registrado")

    def _maybe_schedule_printer_clean_popup_only(self) -> None:
        """
        Frame x Frame: al cruzar el umbral abre el popup de limpieza **sin**
        ``run_pause_digitization`` (válido en idle o ya pausado).
        """
        if self._container is None:
            return
        fc = int(self._container.app_state.frame_count)
        if not self._printer_clean_maintenance_due(fc):
            return
        self._log.warning(
            "Se ha alcanzado el límite de %s capturas (Frame x Frame); "
            "mostrando aviso de limpieza de impresora.",
            PRINTER_CLEAN_FRAME_INTERVAL,
        )
        self._printer_clean_pending_schedule_for_frame = fc

        def _on_main(_dt: object) -> None:
            self._printer_clean_pending_schedule_for_frame = None
            self._emit_printer_clean_popup(fc)

        try:
            from kivy.clock import Clock

            Clock.schedule_once(_on_main, 0)
        except Exception:  # noqa: BLE001
            self._printer_clean_pending_schedule_for_frame = None
            self._log.warning(
                "Kivy Clock no disponible; mostrando aviso de limpieza de impresora síncrono"
            )
            self._emit_printer_clean_popup(fc)

    def _maybe_schedule_printer_clean_maintenance(self) -> None:
        if self._container is None:
            return
        fc = int(self._container.app_state.frame_count)
        if not self._printer_clean_maintenance_due(fc):
            return
        self._log.warning(
            "Se ha alcanzado el límite de %s capturas, programando limpieza de impresora.",
            PRINTER_CLEAN_FRAME_INTERVAL,
        )
        self._printer_clean_pending_schedule_for_frame = fc

        def _on_main(_dt: object) -> None:
            self._printer_clean_pending_schedule_for_frame = None
            out = self.run_pause_digitization()
            if not out.ok:
                self._log.warning(
                    "Pausa por mantenimiento impresora (frame %s) no aplicada: %s",
                    fc,
                    out.error,
                )
                return
            self._emit_printer_clean_popup(fc)

        try:
            from kivy.clock import Clock

            Clock.schedule_once(_on_main, 0)
        except Exception:  # noqa: BLE001
            self._printer_clean_pending_schedule_for_frame = None
            self._log.warning("Kivy Clock no disponible; aplicando pausa síncrona por mantenimiento impresora")
            out = self.run_pause_digitization()
            if out.ok:
                self._emit_printer_clean_popup(fc)

    def _advance_film_after_capture(self) -> bool:
        """
        Avance de patrón tras RAW en formato single-shot automático.

        Invariante (§3.1c): no invocar con `_debug_digitization_gate_pending` en producción;
        el chequeo evita avanzar film si el gate quedó activo por error.

        Returns:
            True si el film se avanzó correctamente (camino feliz para §3.12.4).
        """
        if self._container is None:
            return False
        if self._debug_digitization_gate_pending:
            self._capture_last_error = t("capture.wait_debug_frame")
            self._log.debug("post-capture move_film omitido (gate debug activo)")
            return False
        px = self._printer_pixels_for_frame()
        ok = self._container.printer_service().move_film(px)
        if not ok:
            self._capture_last_error = t("capture.move_film_fail")
            self.run_pause_digitization()
            return False
        return True

    def _printer_pixels_for_frame(self) -> int:
        if self._container is None:
            return 10
        cfg = self._container.config_repo.load()
        fmt = str(cfg.get("FORMATO_DIGITALIZAR", "16mm")).strip().lower()
        pattern_key = "PRINTER_PATTERN_35MM" if fmt == "35mm" else "PRINTER_PATTERN_16MM"
        default_pattern = [22] if fmt == "35mm" else [10]
        pattern = cfg.get(pattern_key, default_pattern)
        if not isinstance(pattern, list) or not pattern:
            pattern = default_pattern
        nums: list[int] = []
        for p in pattern:
            try:
                nums.append(max(int(p), 1))
            except Exception:  # noqa: BLE001
                continue
        if not nums:
            nums = default_pattern
        idx = max(self._container.app_state.frame_count - 1, 0)
        return nums[idx % len(nums)]

    def run_download_pending(self, progress: ProgressCb | None = None) -> "DownloadRawsResult":
        from print_scanner_app.application.dto.results import DownloadRawsResult
        from print_scanner_app.infrastructure.camera.gphoto_raw_bridge import GPhotoCameraRawAdapter

        if self._container is None:
            return DownloadRawsResult(error=t("err.no_container"))

        cfg = self._container.config_repo.load()
        base_str = resolve_output_directory(cfg)
        if not base_str or not output_directory_configured(cfg):
            return DownloadRawsResult(error=t("err.select_output_dir"))

        pending = self._container.raw_pending_repo.load_blocks()
        if not pending:
            return DownloadRawsResult(error=t("err.no_raw_pending"))

        with self._camera_access_lock:
            self._raw_download_in_progress = True
            # Bloquea nuevos ticks; el que ya está en vuelo termina (sin abort).
            self._capture_tick_may_run.clear()
            try:
                if not self._wait_capture_tick_idle(RAW_DOWNLOAD_CAPTURE_IDLE_TIMEOUT_S):
                    return DownloadRawsResult(
                        error=t("err.capture_busy_download")
                    )
                if not self._wait_preview_io_idle(RAW_DOWNLOAD_CAPTURE_IDLE_TIMEOUT_S):
                    return DownloadRawsResult(
                        error=t("err.preview_busy_download")
                    )

                # libgphoto2 solo permite una sesión USB activa: preview/captura bloquean claim (-53).
                self._close_preview_session()
                self.close_alignment_debug_windows()
                st = self._container.app_state
                if st.digitalizing and not st.pause_digitization:
                    self.run_pause_digitization()
                if self._capture_session is not None:
                    self._close_capture_session()

                self._gc_after_gphoto_session_boundary()

                serial, config_cam = self._serial_and_config_camara()

                cam_svc = self._container.camera_service()
                session, err = cam_svc.open_session_for_download(serial, config_cam)
                if session is None:
                    return DownloadRawsResult(error=err or t("err.open_camera"))

                try:
                    adapter = GPhotoCameraRawAdapter(session.camera, session.gp)
                    uc = self._container.download_raws_use_case()
                    base = Path(base_str)
                    return uc.execute(
                        pending,
                        base,
                        adapter,
                        progress=progress,
                        search_root=base,
                    )
                finally:
                    try:
                        session.camera.exit()
                    except Exception:  # noqa: BLE001
                        self._log.debug("camera.exit() ignorado tras descarga", exc_info=True)
                    self._gc_after_gphoto_session_boundary()
            finally:
                self._raw_download_in_progress = False
                self._capture_tick_may_run.set()
