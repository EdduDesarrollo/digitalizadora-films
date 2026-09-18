from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Callable, Mapping, Optional, Tuple

from print_scanner_app.application.dto.camera_session import CameraSession
from print_scanner_app.application.dto.results import CameraAssignResult
from print_scanner_app.domain.policies.retry_policy import RetryConfig
from print_scanner_app.infrastructure.camera.camera_config import (
    INFO_CAMERAMODEL_MISSING,
    WARNING_MODEL_MISMATCH,
    apply_camera_configurations,
)
from print_scanner_app.infrastructure.camera.camera_config_export import is_retryable_camera_io_error
from print_scanner_app.infrastructure.camera.camera_config_locale import (
    CAMERAMODEL_PATH,
    camera_models_match,
    ensure_capture_target_memory_card,
    read_camera_model_from_device,
)
from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
    filter_camera_config_to_whitelist,
    has_preset_camera_config,
)
from print_scanner_app.infrastructure.camera.camera_detection import prepare_and_list_cameras
from print_scanner_app.infrastructure.camera.gphoto_client import (
    GPhotoClient,
    capture_preview_bytes,
    delete_jpeg_status,
    disable_viewfinder_best_effort,
    find_latest_jpeg_on_camera,
    find_latest_raw_on_camera,
    find_raw_on_camera,
    get_camera_serial,
    init_camera_at_address,
    raw_exists_on_camera,
    trigger_capture_and_get_raw_name,
    trigger_eos_remote_immediate,
)
from print_scanner_app.infrastructure.system.usb_tools import reset_usb_address

OptionalLogger = Optional[logging.Logger]
Run = Callable[..., Any]

_DEFAULT_OPEN_RETRY = RetryConfig(max_attempts=3, delay_seconds=1.5)


def _safe_camera_exit(camera: Any) -> None:
    try:
        camera.exit()
    except Exception:  # noqa: BLE001
        pass


def _is_retryable_open_error(err: str | None) -> bool:
    if not err:
        return False
    if "Serial" in err and "no coincide" in err:
        return False
    if "No se pudo asignar cámara" in err and "Sin cámaras" not in err:
        return is_retryable_camera_io_error(Exception(err))
    if "Sin cámaras" in err:
        return True
    return is_retryable_camera_io_error(Exception(err))


class CameraService:
    def __init__(
        self,
        *,
        logger: OptionalLogger = None,
        run: Run | None = None,
        photo_client: GPhotoClient | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._log = logger or logging.getLogger(__name__)
        self._client = photo_client if photo_client is not None else GPhotoClient()
        self._run = run
        self._sleep = sleep_fn

    def _assign_and_open_session_once(
        self,
        expected_serial: str,
        saved_camera_config: Mapping[str, Any],
        *,
        unmount_first: bool = True,
        retry: RetryConfig | None = None,
        apply_saved_config: bool = True,
    ) -> Tuple[Optional[CameraSession], Optional[str]]:
        run = self._run or subprocess.run
        try:
            cams = prepare_and_list_cameras(self._client, run=run, unmount_first=unmount_first)
        except Exception as e:  # noqa: BLE001
            return None, str(e)

        if not cams:
            return None, "Sin cámaras"

        gp = self._client.gp
        filtered_config = filter_camera_config_to_whitelist(saved_camera_config)
        last_err = None
        for _cam_name, addr in cams:
            cam = None
            try:
                cam = init_camera_at_address(gp, addr, retries=retry, reset_on_fail=True)
                serial = get_camera_serial(gp, cam)
                exp = (expected_serial or "").strip()
                det = (serial or "").strip()
                match = det == exp and exp != ""
                if match:
                    self._configure_camera_session(
                        cam,
                        gp,
                        filtered_config,
                        apply_saved_config=apply_saved_config,
                    )
                    return CameraSession(gp=gp, camera=cam, usb_address=addr), None
                last_err = f"Serial {serial!r} no coincide con {expected_serial!r}"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            if cam is not None:
                _safe_camera_exit(cam)

        return None, last_err or "No se pudo asignar cámara"

    def _assign_and_open_session(
        self,
        expected_serial: str,
        saved_camera_config: Mapping[str, Any],
        *,
        unmount_first: bool = True,
        retry: RetryConfig | None = None,
        apply_saved_config: bool = True,
        open_retry: RetryConfig | None = None,
    ) -> Tuple[Optional[CameraSession], Optional[str]]:
        cfg_open = open_retry or _DEFAULT_OPEN_RETRY
        init_retry = retry
        last_err: str | None = None

        for attempt in range(cfg_open.max_attempts):
            if attempt > 0:
                self._sleep(cfg_open.delay_seconds)
            do_unmount = unmount_first and attempt == 0
            session, err = self._assign_and_open_session_once(
                expected_serial,
                saved_camera_config,
                unmount_first=do_unmount,
                retry=init_retry,
                apply_saved_config=apply_saved_config,
            )
            if session is not None:
                return session, None
            last_err = err
            if not _is_retryable_open_error(err):
                break
            self._log.warning(
                "Apertura de sesión cámara (intento %s/%s): %s",
                attempt + 1,
                cfg_open.max_attempts,
                err,
            )

        return None, last_err or "No se pudo abrir la cámara"

    def _configure_camera_session(
        self,
        cam: Any,
        gp: Any,
        saved_camera_config: Mapping[str, Any],
        *,
        apply_saved_config: bool = True,
    ) -> None:
        detected_model = read_camera_model_from_device(cam, gp, logger=self._log)
        filtered = filter_camera_config_to_whitelist(saved_camera_config)
        expected_raw = filtered.get(CAMERAMODEL_PATH) if filtered else None
        expected_model = str(expected_raw).strip() if expected_raw else None

        config_ok = True
        model_mismatch = False
        applied_n = 0
        failed_n = 0

        should_apply = apply_saved_config and has_preset_camera_config(filtered)
        if should_apply:
            if not expected_model:
                self._log.info("%s", INFO_CAMERAMODEL_MISSING)
                result = apply_camera_configurations(
                    cam,
                    filtered,
                    gp,
                    logger=self._log,
                    expected_model=expected_model,
                    detected_model=detected_model,
                )
                config_ok = result.ok
                applied_n = len(result.applied)
                failed_n = len(result.failed)
            elif camera_models_match(expected_model, detected_model):
                result = apply_camera_configurations(
                    cam,
                    filtered,
                    gp,
                    logger=self._log,
                    expected_model=expected_model,
                    detected_model=detected_model,
                )
                config_ok = result.ok
                applied_n = len(result.applied)
                failed_n = len(result.failed)
            else:
                model_mismatch = True
                config_ok = False
                self._log.warning(
                    WARNING_MODEL_MISMATCH.format(
                        expected=expected_model,
                        detected=detected_model or "(desconocido)",
                    )
                )
        elif apply_saved_config and not filtered:
            config_ok = True
        elif apply_saved_config:
            self._log.debug(
                "CONFIG_CAMARA sin preset aplicable; se aplica solo invariante capturetarget"
            )

        # Invariante SD solo en assign/startup (apply_saved_config=True). Preview,
        # captura y descarga reabren sesión sin reescribir capturetarget.
        if apply_saved_config:
            invariant_ok = ensure_capture_target_memory_card(
                cam,
                gp,
                logger=self._log,
                detected_model=detected_model,
            )
        else:
            invariant_ok = True
            self._log.debug(
                "Sesión sin apply_saved_config: se omite invariante capturetarget"
            )

        self._log.info(
            "Sesión cámara: config_ok=%s invariant_ok=%s model_mismatch=%s "
            "applied=%s failed=%s apply_saved_config=%s",
            config_ok,
            invariant_ok,
            model_mismatch,
            applied_n,
            failed_n,
            apply_saved_config,
        )

    def assign_camera(
        self,
        expected_serial: str,
        saved_camera_config: Mapping[str, Any],
        *,
        unmount_first: bool = True,
        retry: RetryConfig | None = None,
    ) -> CameraAssignResult:
        session, err = self._assign_and_open_session(
            expected_serial,
            saved_camera_config,
            unmount_first=unmount_first,
            retry=retry,
            apply_saved_config=True,
        )
        if session is not None:
            try:
                ser = get_camera_serial(session.gp, session.camera)
                return CameraAssignResult(ok=True, usb_address=session.usb_address, serial=ser)
            finally:
                _safe_camera_exit(session.camera)
        return CameraAssignResult(ok=False, error=err)

    def open_session_for_download(
        self,
        expected_serial: str,
        saved_camera_config: Mapping[str, Any],
        *,
        unmount_first: bool = True,
        retry: RetryConfig | None = None,
    ) -> Tuple[Optional[CameraSession], Optional[str]]:
        """Sesión de descarga: sin apply de preset ni invariante capturetarget."""
        return self._assign_and_open_session(
            expected_serial,
            saved_camera_config,
            unmount_first=unmount_first,
            retry=retry,
            apply_saved_config=False,
        )

    def open_session_for_capture(
        self,
        expected_serial: str,
        saved_camera_config: Mapping[str, Any],
        *,
        unmount_first: bool = True,
        retry: RetryConfig | None = None,
        apply_saved_config: bool = False,
    ) -> Tuple[Optional[CameraSession], Optional[str]]:
        return self._assign_and_open_session(
            expected_serial,
            saved_camera_config,
            unmount_first=unmount_first,
            retry=retry,
            apply_saved_config=apply_saved_config,
        )

    def capture_raw_name(self, session: CameraSession) -> Optional[str]:
        return trigger_capture_and_get_raw_name(session.camera, session.gp)

    def trigger_immediate_release(self, session: CameraSession) -> bool:
        """Still rápido vía eosremoterelease=Immediate (sin esperar archivo PTP)."""
        return trigger_eos_remote_immediate(session.camera, session.gp)

    def raw_name_exists_on_card(
        self,
        session: CameraSession,
        raw_name: str,
        cache: list | None = None,
    ) -> bool:
        return raw_exists_on_camera(
            session.camera,
            session.gp,
            raw_name,
            last_found_folder=cache,
        )

    def capture_preview_jpeg(self, session: CameraSession) -> Optional[bytes]:
        return capture_preview_bytes(session.camera, session.gp)

    def find_latest_raw_name(self, session: CameraSession, cache: list | None = None) -> Optional[str]:
        _folder, name = find_latest_raw_on_camera(
            session.camera,
            session.gp,
            last_found_folder=cache,
        )
        return name

    def find_raw_name(
        self,
        session: CameraSession,
        raw_name: str,
        cache: list | None = None,
    ) -> Optional[str]:
        _folder, name = find_raw_on_camera(
            session.camera,
            session.gp,
            raw_name,
            last_found_folder=cache,
        )
        return name

    def find_latest_jpeg_pair(
        self,
        session: CameraSession,
        cache: list | None = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Carpeta y nombre JPEG más reciente en tarjeta (rutas exactas gphoto2)."""
        return find_latest_jpeg_on_camera(
            session.camera,
            session.gp,
            last_found_folder=cache,
        )

    def delete_jpeg_from_card(self, session: CameraSession, folder: str, name: str) -> str:
        """``deleted`` | ``absent``."""
        return delete_jpeg_status(session.camera, session.gp, folder, name)

    def close_session(self, session: CameraSession | None) -> None:
        """Apaga viewfinder (best-effort) y ``camera.exit()`` para no dejar PTP a medias."""
        if session is None:
            return
        try:
            disable_viewfinder_best_effort(session.camera, session.gp)
        except Exception:  # noqa: BLE001
            pass
        _safe_camera_exit(session.camera)

    def reset_usb_for_address(self, addr: str) -> bool:
        return reset_usb_address(addr)
