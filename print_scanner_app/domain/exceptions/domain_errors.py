"""Taxonomía de errores de dominio."""


class DomainError(Exception):
    """Base para errores de negocio."""


class CameraError(DomainError):
    """Fallos de detección, init o operación con la cámara."""


class PrinterError(DomainError):
    """Fallos de impresora o comunicación ESC/POS."""


class DiskFullError(DomainError):
    """Sin espacio en dispositivo (ENOSPC u equivalente)."""


class RawDownloadError(DomainError):
    """Error genérico en pipeline de descarga RAW (excepto disco lleno / no encontrado)."""


class RawNotFoundOnCameraError(DomainError):
    """El RAW listado como pendiente no está en la cámara."""


class PermissionDeniedError(DomainError):
    """EACCES / permisos insuficientes."""


class ReadOnlyFilesystemError(DomainError):
    """EROFS u filesystem solo lectura."""
