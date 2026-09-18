"""
Servicio de captura/digitación.

Orquesta la máquina de estados de digitación para que UI/use-cases
no muten estado directamente. La alineación OpenCV, live view y reentrada Kivy
viven en el presenter / UI.
"""

from typing import Callable, Optional

from print_scanner_app.domain.models.app_state import AppState
from print_scanner_app.infrastructure.storage.raw_pending_repository import RawPendingRepository

RawNameProvider = Callable[[int], Optional[str]]
FrameCountCb = Callable[[int], None]


class CaptureService:
    """Orquesta estado básico de digitación sin acoplar a Kivy."""

    def __init__(
        self,
        pending_repo: RawPendingRepository | None = None,
        raw_name_provider: RawNameProvider | None = None,
    ):
        self._pending_repo = pending_repo
        self._raw_name_provider = raw_name_provider
        self._last_raw_name: str | None = None
        self._on_frame_count_changed: FrameCountCb | None = None

    def set_on_frame_count_changed(self, cb: FrameCountCb | None) -> None:
        """Notifica el nuevo `frame_count` tras incrementos en `observe_raw` / `capture_tick`."""
        self._on_frame_count_changed = cb

    def _emit_frame_count(self, state: AppState) -> None:
        cb = self._on_frame_count_changed
        if cb is not None:
            cb(state.frame_count)

    def start_digitization(self, state: AppState) -> bool:
        state.digitalizing = True
        state.pause_digitization = False
        return True

    def pause_digitization(self, state: AppState) -> bool:
        if not state.digitalizing:
            return False
        state.pause_digitization = True
        return True

    def resume_digitization(self, state: AppState) -> bool:
        if not state.digitalizing:
            return False
        state.pause_digitization = False
        return True

    def stop_digitization(self, state: AppState) -> bool:
        state.digitalizing = False
        state.pause_digitization = False
        self._last_raw_name = None
        return True

    def capture_tick(self, state: AppState) -> bool:
        """
        Paso mínimo de captura para migración incremental.
        Mientras no haya integración real de cámara/impresora, sólo incrementa frame_count.
        """
        if not state.digitalizing or state.pause_digitization:
            return False
        state.frame_count += 1
        if self._pending_repo is not None:
            idx = max(state.frame_count, 1)
            raw_name = self._resolve_raw_name(idx)
            dest_name = self._pending_repo.pending_dest_basename(idx)
            self._pending_repo.append(raw_name, dest_name)
        self._emit_frame_count(state)
        return True

    def _resolve_raw_name(self, idx: int) -> str:
        if self._raw_name_provider is None:
            return f"CAP-{idx:06d}.CR3"
        try:
            provided = (self._raw_name_provider(idx) or "").strip()
            return provided or f"CAP-{idx:06d}.CR3"
        except Exception:  # noqa: BLE001
            return f"CAP-{idx:06d}.CR3"

    def _persist_observed_raw(
        self,
        state: AppState,
        raw_name: str,
        *,
        jpg_name: str | None = None,
    ) -> bool:
        """Deduplica por nombre, incrementa ``frame_count`` y encola pendiente."""
        name = (raw_name or "").strip()
        if not name:
            return False
        if self._last_raw_name and self._last_raw_name.lower() == name.lower():
            return False
        self._last_raw_name = name
        state.frame_count += 1
        if self._pending_repo is not None:
            idx = max(state.frame_count, 1)
            dest_name = self._pending_repo.pending_dest_basename(idx)
            self._pending_repo.append_with_jpg(name, dest_name, jpg_name)
        self._emit_frame_count(state)
        return True

    def observe_raw(
        self,
        state: AppState,
        raw_name: str,
        *,
        jpg_name: str | None = None,
        allow_when_paused: bool = False,
    ) -> bool:
        """
        Registra un RAW observado en cámara real (deduplicado por nombre).
        Opcionalmente persiste metadato ``JPG|basename`` si ``jpg_name`` está definido.

        ``allow_when_paused``: si True, persiste el pendiente aunque ``pause_digitization``
        ya esté en True (para usarse dentro de la sección crítica post-disparo, donde la
        pausa fue diferida y el frame no debe perderse).
        """
        if not state.digitalizing:
            return False
        if state.pause_digitization and not allow_when_paused:
            return False
        return self._persist_observed_raw(state, raw_name, jpg_name=jpg_name)

    def observe_raw_manual(
        self,
        state: AppState,
        raw_name: str,
        *,
        jpg_name: str | None = None,
    ) -> bool:
        """
        Registra un RAW fuera del loop de digitación (Frame x Frame).

        No exige ``digitalizing=True`` ni bloquea por ``pause_digitization``.
        """
        return self._persist_observed_raw(state, raw_name, jpg_name=jpg_name)
