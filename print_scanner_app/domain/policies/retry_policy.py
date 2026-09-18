from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    delay_seconds: float = 2.5


def run_with_retries(
    fn: Callable[[], T],
    *,
    should_retry: Callable[[BaseException], bool],
    config: RetryConfig | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Ejecuta fn con reintentos y backoff fijo entre intentos."""
    cfg = config or RetryConfig()
    errors: List[BaseException] = []
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            return fn()
        except BaseException as e:  # noqa: BLE001 — política explícita de reintento
            errors.append(e)
            if attempt >= cfg.max_attempts or not should_retry(e):
                raise
            sleep_fn(cfg.delay_seconds)
    raise RuntimeError("unreachable")  # pragma: no cover
