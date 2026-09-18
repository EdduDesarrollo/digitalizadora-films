"""Sub-fases del ciclo 35 mm (varias perforaciones por disparo)."""

from __future__ import annotations

from enum import Enum, auto


class Film35Subphase(Enum):
    """Ver `docs/DIFF_PRINT.md` — especificación 35 mm."""

    FIRST_SEARCH = auto()  # paso 1: buscar primera perforación → disparo
    MID_SEARCH = auto()  # pasos 4: buscar siguiente perforación (1 px)
    # Tras alinear en MID_SEARCH se aplica patrón (paso 5) en el mismo tick.
