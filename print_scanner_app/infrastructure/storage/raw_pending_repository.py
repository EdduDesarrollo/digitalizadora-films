from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from print_scanner_app.application.session_naming import raw_pending_file_key_from_config
from print_scanner_app.infrastructure.storage.config_repository import ConfigRepository

_LOG_TRUNC_BYTES = 32768
_PERSIST_MAX_ATTEMPTS = 6
_PERSIST_BACKOFF_SEC = 0.03
PENDING_RAWS_SUBDIR = "Pending_raws"
_LEGACY_PENDING_SUBDIRS = ("raw_pendientes",)


@dataclass(frozen=True)
class RawPendingBlock:
    """Un pendiente: línea RAW obligatoria y metadato JPG opcional (misma corrida en disco)."""

    raw_name: str
    dest_basename: str
    jpg_folder: Optional[str] = None
    jpg_name: Optional[str] = None

    @property
    def has_jpg(self) -> bool:
        return bool((self.jpg_name or "").strip())


def _jpg_basename_from_metadata_line(line: str) -> Optional[str]:
    """
    Línea de metadato JPG tras un RAW.

    Formato actual: ``JPG|_MG_3773.JPG`` (solo basename).
    Legado (lectura): ``JPG|/carpeta/gphoto|_MG_3773.JPG`` — se conserva solo el nombre de archivo.
    """
    if not line.startswith("JPG|"):
        return None
    parts3 = line.split("|", 2)
    if len(parts3) == 3 and parts3[0] == "JPG":
        fname = parts3[2].strip()
        return fname or None
    parts2 = line.split("|", 1)
    if len(parts2) == 2 and parts2[0] == "JPG":
        fname = parts2[1].strip()
        return fname or None
    return None


def _is_orphan_jpg_metadata_line(line: str) -> bool:
    return _jpg_basename_from_metadata_line(line) is not None


def _parse_lines_to_blocks(
    lines: Sequence[str],
    *,
    log: logging.Logger,
) -> List[RawPendingBlock]:
    """
    Parseo posicional según docs/ELIMINAR_JPG.md (tras descartar líneas vacías).
    """
    blocks: List[RawPendingBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _is_orphan_jpg_metadata_line(line):
            log.warning("raw_pendientes: línea JPG huérfana omitida: %r", line[:200])
            i += 1
            continue
        if "|" not in line:
            log.warning("raw_pendientes: línea RAW sin '|' omitida: %r", line[:200])
            i += 1
            continue
        raw_name, dest_basename = line.split("|", 1)
        raw_name, dest_basename = raw_name.strip(), dest_basename.strip()
        i += 1
        jpg_name: Optional[str] = None
        if i < n:
            nxt = lines[i]
            parsed_jpg = _jpg_basename_from_metadata_line(nxt)
            if parsed_jpg is not None:
                jpg_name = parsed_jpg
                i += 1
            elif nxt.startswith("JPG|"):
                log.warning("raw_pendientes: línea JPG mal formada, omitida: %r", nxt[:200])
                i += 1
        blocks.append(
            RawPendingBlock(
                raw_name=raw_name,
                dest_basename=dest_basename,
                jpg_folder=None,
                jpg_name=jpg_name,
            )
        )
    return blocks


def _normalize_file_lines(text: str) -> List[str]:
    out: List[str] = []
    for raw_ln in text.splitlines():
        ln = raw_ln.replace("\r\n", "\n").strip()
        if not ln:
            continue
        out.append(ln)
    return out


def _serialize_blocks(blocks: Sequence[RawPendingBlock]) -> str:
    parts: List[str] = []
    for b in blocks:
        parts.append(f"{b.raw_name}|{b.dest_basename}\n")
        if b.has_jpg:
            parts.append(f"JPG|{b.jpg_name}\n")
    return "".join(parts)


def _atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    tmp.replace(path)


def _log_truncated_body(log: logging.Logger, body: str) -> None:
    raw = body.encode("utf-8")
    n = len(raw)
    if n <= _LOG_TRUNC_BYTES:
        log.error("raw_pendientes: fallo persistencia tras reintentos; contenido:\n%s", body)
        return
    half = _LOG_TRUNC_BYTES // 2
    head = raw[:half].decode("utf-8", errors="replace")
    tail = raw[-half:].decode("utf-8", errors="replace")
    log.error(
        "raw_pendientes: fallo persistencia tras reintentos; contenido (truncado):\n%s\n[… truncado, %s bytes en total]\n%s",
        head,
        n,
        tail,
    )


def _unlink_with_retries(path: Path, *, log: logging.Logger) -> bool:
    """Borra el archivo de pendientes con la misma política de reintentos que la escritura."""
    last_exc: Optional[BaseException] = None
    for attempt in range(_PERSIST_MAX_ATTEMPTS):
        try:
            path.unlink(missing_ok=True)
            return True
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt + 1 < _PERSIST_MAX_ATTEMPTS:
                time.sleep(_PERSIST_BACKOFF_SEC)
    log.error("raw_pendientes: unlink falló %s tras %s intentos: %s", path, _PERSIST_MAX_ATTEMPTS, last_exc)
    return False


def persist_raw_pending_file(
    path: Path,
    content: str,
    *,
    log: Optional[logging.Logger] = None,
    context: str = "raw_pendientes",
) -> bool:
    """
    Escribe el archivo completo con hasta 6 intentos (1 + 5 reintentos) y backoff corto.
    Retorna True si OK, False si agotados reintentos (log ERROR con cuerpo truncado a 32 KiB).
    """
    logger = log or logging.getLogger(__name__)
    last_exc: Optional[BaseException] = None
    for attempt in range(_PERSIST_MAX_ATTEMPTS):
        try:
            _atomic_replace(path, content)
            return True
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt + 1 < _PERSIST_MAX_ATTEMPTS:
                time.sleep(_PERSIST_BACKOFF_SEC)
    msg = f"{context}: no se pudo escribir {path} tras {_PERSIST_MAX_ATTEMPTS} intentos"
    if last_exc is not None:
        logger.error("%s: %s", msg, last_exc)
    else:
        logger.error("%s", msg)
    _log_truncated_body(logger, content)
    return False


class RawPendingRepository:
    """
    Persistencia `raw_name|dest_basename` y opcional `JPG|basename` por sesión.

    Convención: ``Utils/Pending_raws/raw_pendientes_{NOMBRE_ARCHIVO}.txt``
    con NOMBRE_ARCHIVO derivado de config (PREFIJO_ARCHIVO + CODIGO_REFERENCIA).
    Migra automáticamente desde ubicaciones legacy (``Utils/raw_pendientes_*.txt`` o
    ``Utils/raw_pendientes/raw_pendientes_*.txt``).

    Captura y descarga compiten por el mismo archivo: serializar con `_lock`.
    """

    def __init__(
        self,
        utils_dir: Path,
        config_repo: ConfigRepository,
        *,
        fixed_session_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self._utils_dir = utils_dir
        self._pending_dir = utils_dir / PENDING_RAWS_SUBDIR
        self._config_repo = config_repo
        self._fixed_session_key = fixed_session_key
        self._log = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._utils_dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir.mkdir(parents=True, exist_ok=True)

    def _session_key(self) -> str:
        if self._fixed_session_key is not None:
            return self._fixed_session_key
        return raw_pending_file_key_from_config(self._config_repo.load())

    def pending_dest_basename(self, frame_index: int) -> str:
        """
        Nombre destino en PC: ``{NOMBRE_ARCHIVO}-{frame:06d}.cr3``
        (misma raíz que ``raw_pendientes_{NOMBRE_ARCHIVO}.txt``).
        """
        key = self._session_key()
        n = max(int(frame_index), 1)
        return f"{key}-{n:06d}.cr3"

    def _pending_file_name(self) -> str:
        return f"raw_pendientes_{self._session_key()}.txt"

    @property
    def file_path(self) -> Path:
        return self._pending_dir / self._pending_file_name()

    def _legacy_file_paths(self) -> list[Path]:
        name = self._pending_file_name()
        paths = [self._utils_dir / name]
        for sub in _LEGACY_PENDING_SUBDIRS:
            paths.append(self._utils_dir / sub / name)
        return paths

    def _migrate_legacy_if_needed(self) -> None:
        target = self.file_path
        if target.is_file():
            return
        for legacy in self._legacy_file_paths():
            if not legacy.is_file():
                continue
            try:
                self._pending_dir.mkdir(parents=True, exist_ok=True)
                legacy.replace(target)
                self._log.info("raw_pendientes: migrado legacy %s -> %s", legacy, target)
                return
            except Exception as e:  # noqa: BLE001
                self._log.warning("raw_pendientes: no se pudo migrar legacy %s: %s", legacy, e)

    def _resolved_file_path(self) -> Path:
        self._migrate_legacy_if_needed()
        return self.file_path

    def load_blocks(self) -> List[RawPendingBlock]:
        path = self._resolved_file_path()
        if not path.is_file():
            return []
        with self._lock:
            text = path.read_text(encoding="utf-8")
        lines = _normalize_file_lines(text)
        return _parse_lines_to_blocks(lines, log=self._log)

    def load_all(self) -> List[List[str]]:
        """Compatibilidad: una fila ``[raw_name, dest_basename]`` por bloque."""
        return [[b.raw_name, b.dest_basename] for b in self.load_blocks()]

    def save_blocks(self, blocks: Sequence[RawPendingBlock], *, use_post_phase_b_retries: bool = False) -> bool:
        """
        Reescribe el archivo con la lista de bloques dada.
        Si ``use_post_phase_b_retries`` es True, aplica 6 intentos + log truncado (cierre post fase B).
        """
        content = _serialize_blocks(blocks)
        path = self._resolved_file_path()
        with self._lock:
            if use_post_phase_b_retries:
                return persist_raw_pending_file(path, content, log=self._log, context="post_fase_B")
            try:
                _atomic_replace(path, content)
                return True
            except Exception as e:  # noqa: BLE001
                self._log.error("raw_pendientes: error al guardar %s: %s", path, e)
                return False

    def append(self, raw_name: str, dest_name: str) -> None:
        self.append_with_jpg(raw_name, dest_name, None)

    def append_with_jpg(
        self,
        raw_name: str,
        dest_name: str,
        jpg_name: Optional[str],
    ) -> None:
        jn = (jpg_name or "").strip() or None
        if jn and "|" in jn:
            self._log.warning(
                "raw_pendientes: JPG con '|' en el nombre no soportado; se omite metadato JPG"
            )
            jn = None
        block = RawPendingBlock(
            raw_name=raw_name.strip(),
            dest_basename=dest_name.strip(),
            jpg_folder=None,
            jpg_name=jn,
        )
        with self._lock:
            blocks = self._load_blocks_unlocked()
            blocks.append(block)
            _atomic_replace(self._resolved_file_path(), _serialize_blocks(blocks))

    def _load_blocks_unlocked(self) -> List[RawPendingBlock]:
        path = self._resolved_file_path()
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8")
        lines = _normalize_file_lines(text)
        return _parse_lines_to_blocks(lines, log=self._log)

    def remove_block_sync(self, raw_name: str) -> bool:
        """
        Elimina el bloque del disco. True si el resultado es coherente (bloque ausente o bien borrado).
        False solo ante fallo de E/S tras agotar reintentos.

        Usa ``persist_raw_pending_file`` (6 intentos + log truncado a 32 KiB) al reescribir el
        archivo; si el lote queda vacío, ``unlink`` con la misma política de reintentos.
        En descarga, cada éxito de fase A pasa por aquí (punto de consolidación E3 por ítem).
        """
        needle = raw_name.strip().upper()
        path = self._resolved_file_path()
        with self._lock:
            if not path.is_file():
                return True
            blocks = self._load_blocks_unlocked()
            kept = [b for b in blocks if b.raw_name.strip().upper() != needle]
            if len(kept) == len(blocks):
                return True
            if not kept:
                return _unlink_with_retries(path, log=self._log)
            content = _serialize_blocks(kept)
            return persist_raw_pending_file(
                path,
                content,
                log=self._log,
                context="remove_block_sync",
            )

    def remove(self, raw_name: str) -> bool:
        """Elimina el bloque (RAW + JPG asociado). True si el archivo dejó de existir."""
        needle = raw_name.strip().upper()
        path = self._resolved_file_path()
        with self._lock:
            if not path.is_file():
                return False
            blocks = self._load_blocks_unlocked()
            kept = [b for b in blocks if b.raw_name.strip().upper() != needle]
            if len(kept) == len(blocks):
                return False
            content = _serialize_blocks(kept)
            if not kept:
                try:
                    path.unlink(missing_ok=True)
                    return True
                except Exception as e:  # noqa: BLE001
                    self._log.error("raw_pendientes: no se pudo borrar %s: %s", path, e)
                    return False
            try:
                _atomic_replace(path, content)
                return False
            except Exception as e:  # noqa: BLE001
                self._log.error("raw_pendientes: remove falló al escribir %s: %s", path, e)
                return False

    def is_empty(self) -> bool:
        self._migrate_legacy_if_needed()
        if self.file_path.is_file():
            return False
        return not any(p.is_file() for p in self._legacy_file_paths())
