from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class DependencyReport:
    ok: bool
    system_missing: List[str] = field(default_factory=list)
    python_missing: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def check_commands(commands: List[str], *, which: Callable[[str], str | None] = shutil.which) -> List[str]:
    return [c for c in commands if not which(c)]


def merge_reports(*reports: DependencyReport) -> DependencyReport:
    out = DependencyReport(ok=True)
    for r in reports:
        out.system_missing.extend(r.system_missing)
        out.python_missing.extend(r.python_missing)
        out.notes.extend(r.notes)
        out.ok = out.ok and r.ok
    return out
