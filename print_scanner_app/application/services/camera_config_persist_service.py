from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from print_scanner_app.infrastructure.camera.camera_config_export import (
    export_camera_config_tree,
    is_retryable_camera_io_error,
    merge_camera_config,
)
from print_scanner_app.infrastructure.camera.camera_config_whitelist import (
    diff_camera_config,
    filter_camera_config_to_whitelist,
)
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository

OptionalLogger = Optional[logging.Logger]


@dataclass(frozen=True)
class PersistCameraConfigResult:
    ok: bool
    error: str | None = None
    merged_config: dict[str, Any] | None = None


class CameraConfigPersistService:
    def __init__(self, *, logger: OptionalLogger = None):
        self._log = logger or logging.getLogger(__name__)

    def persist_camera_config_after_entangle(
        self,
        camera: Any,
        gp: Any,
        config_repo: ConfigRepository,
        *,
        before_snapshot: Mapping[str, Any] | None = None,
        max_attempts: int = 2,
        initial_sleep_s: float = 3.0,
        retry_sleep_increment_s: float = 0.5,
    ) -> PersistCameraConfigResult:
        last_err: str | None = None
        for attempt in range(max_attempts):
            sleep_s = initial_sleep_s + (attempt * retry_sleep_increment_s)
            if sleep_s > 0:
                time.sleep(sleep_s)
            try:
                exported_full = export_camera_config_tree(camera, gp)
                exported = filter_camera_config_to_whitelist(exported_full)
                if not exported:
                    last_err = "export vacío"
                    self._log.warning(
                        "CONFIG_CAMARA: export vacío (intento %s/%s)",
                        attempt + 1,
                        max_attempts,
                    )
                    continue

                if before_snapshot is not None:
                    changes = diff_camera_config(before_snapshot, exported)
                else:
                    changes = exported

                if not changes:
                    self._log.info(
                        "CONFIG_CAMARA: sin cambios respecto al snapshot pre-Entangle"
                    )
                    cfg = config_repo.load()
                    existing = filter_camera_config_to_whitelist(
                        cfg.get("CONFIG_CAMARA") if isinstance(cfg.get("CONFIG_CAMARA"), dict) else {}
                    )
                    return PersistCameraConfigResult(ok=True, merged_config=existing)

                cfg = config_repo.load()
                existing = cfg.get("CONFIG_CAMARA")
                merged = merge_camera_config(
                    filter_camera_config_to_whitelist(
                        existing if isinstance(existing, dict) else None
                    ),
                    changes,
                )
                cfg["CONFIG_CAMARA"] = filter_camera_config_to_whitelist(merged)
                config_repo.save(cfg)
                self._log.info(
                    "CONFIG_CAMARA guardado tras Entangle (%s claves cambiadas, %s total)",
                    len(changes),
                    len(cfg["CONFIG_CAMARA"]),
                )
                return PersistCameraConfigResult(ok=True, merged_config=cfg["CONFIG_CAMARA"])
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                if is_retryable_camera_io_error(e):
                    self._log.warning(
                        "CONFIG_CAMARA: cámara ocupada (intento %s/%s): %s",
                        attempt + 1,
                        max_attempts,
                        e,
                    )
                else:
                    self._log.error(
                        "CONFIG_CAMARA: error no reintentable (intento %s/%s): %s",
                        attempt + 1,
                        max_attempts,
                        e,
                    )
                    return PersistCameraConfigResult(ok=False, error=last_err)
        return PersistCameraConfigResult(ok=False, error=last_err or "no se pudo guardar")
