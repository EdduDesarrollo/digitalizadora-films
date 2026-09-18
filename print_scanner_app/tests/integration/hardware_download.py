"""
Descarga real de RAW pendientes + borrado de JPG en cámara (mismo flujo que la UI).

Uso manual (sin pytest):

    DIGITALIZADORA_HARDWARE_TEST=1 python -m print_scanner_app.tests.integration.hardware_download

Requiere: cámara USB, ``config.json`` con ``CAMARA``, ``CONFIG_CAMARA``, ``DIRECTORIO``,
y al menos un bloque en ``Utils/Pending_raws/raw_pendientes_*.txt``.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from print_scanner_app.application.dto.results import DownloadRawsResult
from print_scanner_app.application.services.camera_service import CameraService
from print_scanner_app.application.services.raw_download_service import RawDownloadService
from print_scanner_app.application.use_cases.download_raws import DownloadRawsUseCase
from print_scanner_app.infrastructure.camera.gphoto_client import find_all_jpeg_paths_on_camera
from print_scanner_app.infrastructure.camera.gphoto_raw_bridge import GPhotoCameraRawAdapter
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingBlock, RawPendingRepository


@dataclass(frozen=True)
class HardwareDownloadOutcome:
    """Resultado de una corrida E2E contra hardware real."""

    result: DownloadRawsResult
    pending_before: List[RawPendingBlock]
    dest_base: Path
    batch_dir: Optional[Path] = None
    jpg_absent_on_card: dict[str, bool] = field(default_factory=dict)


def _repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def run_hardware_download(
    project_root: Path,
    *,
    logger: Optional[logging.Logger] = None,
    verify_jpegs_deleted: bool = True,
) -> HardwareDownloadOutcome:
    """
    Abre cámara, ejecuta fase A+B de descarga y opcionalmente verifica JPG ausentes.
    """
    log = logger or logging.getLogger(__name__)
    cfg_repo = ConfigRepository(project_root / "config.json")
    cfg = cfg_repo.load()
    serial = str(cfg.get("CAMARA") or "").strip()
    config_cam = cfg.get("CONFIG_CAMARA") or {}
    if not isinstance(config_cam, dict):
        config_cam = {}
    from print_scanner_app.infrastructure.storage.config_repository import (
        output_directory_configured,
        resolve_output_directory,
    )

    if not output_directory_configured(cfg):
        raise ValueError("Configure DIRECTORIO en config.json (ruta absoluta existente)")
    base_str = resolve_output_directory(cfg)

    repo = RawPendingRepository(project_root / "Utils", cfg_repo)
    pending_before = repo.load_blocks()
    if not pending_before:
        raise ValueError("No hay bloques en raw_pendientes (archivo vacío o inexistente)")

    jpg_names = [b.jpg_name for b in pending_before if b.has_jpg and b.jpg_name]
    dest_base = Path(base_str)

    cam_svc = CameraService(logger=log)
    session, err = cam_svc.open_session_for_download(serial, config_cam)
    if session is None:
        raise RuntimeError(err or "No se pudo abrir la cámara")

    try:
        adapter = GPhotoCameraRawAdapter(session.camera, session.gp)
        uc = DownloadRawsUseCase(RawDownloadService(repo, logger=log))
        dl_result = uc.execute(
            pending_before,
            dest_base,
            adapter,
            search_root=dest_base,
        )

        jpg_absent: dict[str, bool] = {}
        if verify_jpegs_deleted and jpg_names:
            for name in jpg_names:
                hits = find_all_jpeg_paths_on_camera(session.camera, session.gp, name)
                jpg_absent[name] = len(hits) == 0

        batch_dir: Optional[Path] = None
        if dl_result.batch_folder:
            candidate = dest_base / dl_result.batch_folder
            if candidate.is_dir():
                batch_dir = candidate

        return HardwareDownloadOutcome(
            result=dl_result,
            pending_before=pending_before,
            dest_base=dest_base,
            batch_dir=batch_dir,
            jpg_absent_on_card=jpg_absent,
        )
    finally:
        try:
            session.camera.exit()
        except Exception:  # noqa: BLE001
            pass


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = _repo_root_from_here()
    try:
        out = run_hardware_download(root)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    r = out.result
    print("--- Resultado ---")
    print(f"Descargados: {r.downloaded}")
    print(f"No en cámara: {r.not_found}")
    print(f"Aviso popup: {r.missing_local_copy_ids}")
    print(f"Carpeta lote: {r.batch_folder}")
    if r.error:
        print(f"Error: {r.error}")
        return 1
    if out.batch_dir:
        for f in sorted(out.batch_dir.glob("*.cr3")):
            print(f"  {f.name} ({f.stat().st_size} bytes)")
    for name, absent in sorted(out.jpg_absent_on_card.items()):
        print(f"  JPG {name}: {'ausente' if absent else 'AÚN EN CÁMARA'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
