"""Predicción de nombres CR3 Canon (``_MG_NNNN.CR3`` → siguiente)."""

from __future__ import annotations

import re
from typing import Optional

_CR3_NUM = re.compile(r"^(.*?)(\d+)(\.cr3)$", re.IGNORECASE)

# Canon con tarjeta vacía / numeración reiniciada (prefijo visto en EOS M6 Mark II).
DEFAULT_FIRST_CR3_NAME = "_MG_0001.CR3"


def predict_next_cr3_name(last_name: Optional[str]) -> Optional[str]:
    """
    Dado el último basename visto (p. ej. ``_MG_0180.CR3``), devuelve el siguiente
    con el mismo ancho de dígitos (``_MG_0181.CR3``). ``None`` si no parsea.
    """
    s = (last_name or "").strip()
    if not s:
        return None
    m = _CR3_NUM.match(s)
    if not m:
        return None
    prefix, digits, _ext = m.group(1), m.group(2), m.group(3)
    nxt = int(digits) + 1
    if nxt > 10 ** len(digits) - 1:
        return None
    return f"{prefix}{nxt:0{len(digits)}d}.CR3"


def initial_predicted_cr3_name(*known_latest: Optional[str]) -> Optional[str]:
    """
    Próximo CR3 a disparar: ``max(conocidos)+1``, o ``DEFAULT_FIRST_CR3_NAME``
    si no hay ningún CR3 conocido (tarjeta vacía y sin pendientes).
    """
    baseline = max_cr3_name(*known_latest)
    if baseline is None:
        return DEFAULT_FIRST_CR3_NAME
    return predict_next_cr3_name(baseline)


def cr3_sequence_number(name: Optional[str]) -> Optional[int]:
    s = (name or "").strip()
    if not s:
        return None
    m = _CR3_NUM.match(s)
    if not m:
        return None
    return int(m.group(2))


def max_cr3_name(*names: Optional[str]) -> Optional[str]:
    """Elige el basename con mayor número de secuencia entre candidatos parseables."""
    best: Optional[str] = None
    best_n = -1
    for n in names:
        num = cr3_sequence_number(n)
        if num is None:
            continue
        if num > best_n:
            best_n = num
            best = (n or "").strip()
    return best
