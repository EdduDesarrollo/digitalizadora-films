from __future__ import annotations

import errno
from typing import Any, NoReturn

from print_scanner_app.domain.exceptions.domain_errors import (
    DiskFullError,
    DomainError,
    PermissionDeniedError,
    ReadOnlyFilesystemError,
)


def classify_exception(exc: BaseException, message: str | None = None) -> DomainError:
    """Mapea excepciones de infraestructura a errores de dominio."""
    msg = message or str(exc)
    if isinstance(exc, OSError):
        if exc.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
            return DiskFullError(msg)
        if exc.errno == errno.EACCES:
            return PermissionDeniedError(msg)
        if exc.errno == errno.EROFS:
            return ReadOnlyFilesystemError(format_rofs(msg, getattr(exc, "filename", None)))
    if isinstance(exc, DomainError):
        return exc
    return DomainError(msg)


def format_rofs(msg: str, filename: Any) -> str:
    if filename:
        return f"{msg} (filename={filename!r})"
    return msg


def raise_classified(exc: BaseException, message: str | None = None) -> NoReturn:
    raise classify_exception(exc, message) from exc
