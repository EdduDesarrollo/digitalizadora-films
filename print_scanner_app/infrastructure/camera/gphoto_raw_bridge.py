from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from print_scanner_app.infrastructure.camera.gphoto_client import (
    camera_file_scope,
    delete_jpeg_by_basename,
    find_raw_on_camera,
)


class GPhotoCameraRawAdapter:
    """Adapta cámara gphoto2 al protocolo `CameraRawPort` del servicio de descarga."""

    def __init__(self, camera: Any, gp: Any):
        self._camera = camera
        self._gp = gp
        self._folder_cache: list = [None]

    def find_raw(self, raw_name: str) -> Tuple[Optional[str], Optional[str]]:
        return find_raw_on_camera(
            self._camera,
            self._gp,
            raw_name,
            last_found_folder=self._folder_cache,
        )

    def save_raw_to(self, folder: str, name: str, dest_path: Path) -> None:
        with camera_file_scope(self._gp) as camera_file:
            self._camera.file_get(folder, name, self._gp.GP_FILE_TYPE_NORMAL, camera_file)
            camera_file.save(str(dest_path))
            # Política BUGVAR2-03: mtime/atime = momento de descarga (explorador de archivos coherente).
            try:
                now = time.time()
                os.utime(dest_path, (now, now))
            except OSError:
                pass

    def delete_raw(self, folder: str, name: str) -> None:
        self._camera.file_delete(folder, name)

    def delete_jpeg(self, jpg_basename: str) -> str:
        """Busca el basename en toda la tarjeta y borra. Retorna ``deleted`` | ``absent``."""
        return delete_jpeg_by_basename(self._camera, self._gp, jpg_basename)
