from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence, Tuple, Union

from print_scanner_app.application.dto.results import RawDownloadBatchResult
from print_scanner_app.domain.exceptions.domain_errors import DiskFullError, RawDownloadError
from print_scanner_app.domain.policies.error_policy import classify_exception
from print_scanner_app.domain.policies.raw_batch_policy import batch_subfolder_for_download
from print_scanner_app.infrastructure.storage.file_storage import ensure_dir, safe_destination_path
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingBlock, RawPendingRepository

ProgressCallback = Callable[[int, int, str], None]


class CameraRawPort(Protocol):
    """Puerto mínimo para descargar un CR3 desde la cámara ya inicializada."""

    def find_raw(self, raw_name: str) -> Tuple[Optional[str], Optional[str]]: ...

    def save_raw_to(self, folder: str, name: str, dest_path: Path) -> None: ...

    def delete_raw(self, folder: str, name: str) -> None: ...

    def delete_jpeg(self, jpg_basename: str) -> str: ...


def _coerce_blocks(pending: Sequence[Union[RawPendingBlock, Sequence[str]]]) -> List[RawPendingBlock]:
    if not pending:
        return []
    first = pending[0]
    if isinstance(first, RawPendingBlock):
        return list(pending)  # type: ignore[arg-type]
    out: List[RawPendingBlock] = []
    for row in pending:  # type: ignore[assignment]
        if len(row) < 2:
            continue
        out.append(RawPendingBlock(str(row[0]).strip(), str(row[1]).strip()))
    return out


def _find_dest_basename_on_disk(search_root: Path, dest_basename: str) -> Tuple[Optional[Path], List[Path]]:
    """
    Recorre ``search_root`` en profundidad; compara solo el basename (case-insensitive).
    Retorna (elegido, todas_las_coincidencias) con elegido = primera ruta lexicográfica.
    """
    want = os.path.basename(dest_basename).lower()
    hits: List[Path] = []
    if not search_root.is_dir():
        return None, hits
    for dirpath, _dirnames, filenames in os.walk(search_root, topdown=True, followlinks=False):
        for fn in filenames:
            if fn.lower() == want:
                hits.append(Path(dirpath) / fn)
    hits.sort(key=lambda p: str(p))
    if not hits:
        return None, hits
    return hits[0], hits


class RawDownloadService:
    """
    Fase A: todos los RAW del lote (con recuperación en disco si no están en cámara).
    Fase B: borrado de JPG en cámara solo para éxitos de fase A con metadato JPG persistido.

    **Persistencia (E3)**: el bloque RAW+JPG se quita del ``.txt`` en fase A; la fase B solo actúa
    en cámara. No hay reescritura del pendiente después de B. Cada ``remove_block_sync`` exitoso
    en A aplica **6 reintentos + log truncado** (``persist_raw_pending_file`` en el repo).
  """

    def __init__(
        self,
        pending_repo: RawPendingRepository,
        logger: Optional[logging.Logger] = None,
    ):
        self._repo = pending_repo
        self._log = logger or logging.getLogger(__name__)

    def download_batch(
        self,
        pending: Sequence[Union[RawPendingBlock, Sequence[str]]],
        base_dir: Path,
        camera: CameraRawPort,
        *,
        search_root: Path | None = None,
        progress: Optional[ProgressCallback] = None,
    ) -> RawDownloadBatchResult:
        """
        Una corrida: fase A sobre todo el lote; fase B solo si no hubo aborto fatal en A.

        Si ``error`` está definido en el resultado, hubo aborto fatal (p. ej. disco lleno): no se
        ejecutó fase B, pero ``missing_local_copy_ids`` y ``downloaded`` reflejan el progreso hasta
        el fallo (popup al cierre según spec).
        """
        root = search_root if search_root is not None else base_dir
        blocks = _coerce_blocks(pending)
        if not blocks:
            if pending:
                raise RawDownloadError(
                    "No hay líneas válidas en pendientes: cada bloque debe tener al menos "
                    "raw_name|dest_basename. Revise el archivo Utils/Pending_raws/raw_pendientes_*.txt"
                )
            return RawDownloadBatchResult()

        basenames = [b.dest_basename for b in blocks]
        batch = batch_subfolder_for_download(basenames)
        sub = batch.subfolder
        batch_dir = ensure_dir(Path(base_dir) / sub)

        descargados: List[str] = []
        no_encontrados: List[str] = []
        popup_missing: List[str] = []
        total_to_download = len(blocks)
        idx_prog = 0

        jpg_queue: List[str] = []

        for block in blocks:
            idx_prog += 1
            if progress:
                progress(idx_prog, total_to_download, f"Descargando {idx_prog}/{total_to_download} RAW")

            raw_name = block.raw_name
            dest_basename = block.dest_basename

            folder, fname = camera.find_raw(raw_name)
            if not fname:
                chosen, all_hits = _find_dest_basename_on_disk(root, dest_basename)
                if chosen is not None:
                    if len(all_hits) > 1:
                        self._log.warning(
                            "RAW %s: varias copias con basename %s en disco: %s",
                            raw_name,
                            os.path.basename(dest_basename),
                            ", ".join(str(p) for p in all_hits),
                        )
                    self._log.info(
                        "RAW no en cámara pero encontrado en disco (%s); se elimina pendiente",
                        chosen,
                    )
                    if not self._repo.remove_block_sync(raw_name):
                        self._log.error(
                            "Fallo al persistir pendientes tras recuperación en disco para %s; "
                            "posible desincronización cámara/pendientes",
                            raw_name,
                        )
                    continue

                popup_missing.append(raw_name)
                self._log.info("RAW no en cámara ni en disco (avisar al cierre): %s", raw_name)
                no_encontrados.append(raw_name)
                continue

            dest_path = safe_destination_path(batch_dir, os.path.basename(dest_basename))
            try:
                camera.save_raw_to(folder, fname, dest_path)
                camera.delete_raw(folder, fname)
            except Exception as e:  # noqa: BLE001
                dom = classify_exception(e)
                self._log.error("Error descargando %s: %s", raw_name, dom)
                if isinstance(dom, DiskFullError):
                    return RawDownloadBatchResult(
                        downloaded=descargados,
                        not_found=no_encontrados,
                        batch_folder=sub,
                        missing_local_copy_ids=list(popup_missing),
                        error=str(dom),
                    )
                raise RawDownloadError(str(dom)) from e

            jpg_name: Optional[str] = None
            if block.has_jpg:
                jpg_name = block.jpg_name

            if not self._repo.remove_block_sync(raw_name):
                self._log.error(
                    "Fallo al persistir pendientes tras éxito de descarga para %s; "
                    "posible desincronización cámara/pendientes",
                    raw_name,
                )
            else:
                if jpg_name:
                    jpg_queue.append(jpg_name)
            descargados.append(raw_name)

        # Fase B: buscar cada basename en toda la tarjeta (no se usa carpeta del .txt).
        for jpg_basename in jpg_queue:
            try:
                status = camera.delete_jpeg(jpg_basename)
                if status == "absent":
                    self._log.info(
                        "JPG ya ausente en cámara (tratado como éxito): %s",
                        jpg_basename,
                    )
            except Exception as e:  # noqa: BLE001
                self._log.warning("Fallo no fatal borrando JPG %s: %s", jpg_basename, e)

        return RawDownloadBatchResult(
            downloaded=descargados,
            not_found=no_encontrados,
            batch_folder=sub,
            missing_local_copy_ids=popup_missing,
        )
