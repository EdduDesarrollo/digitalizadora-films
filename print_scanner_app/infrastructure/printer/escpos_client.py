from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class EscposClient:
    """
    Encapsula escpos.printer.File. Si `python-escpos` no está instalado,
    las operaciones lanzan ImportError al usar instancias reales (tests usan mock).
    """

    def __init__(self, device_path: Optional[Path | str] = None, _printer: Any = None):
        self.device_path = Path(device_path) if device_path else None
        self._printer = _printer

    @classmethod
    def open(cls, device_path: Path | str):
        from escpos import printer as escpos_printer

        dev = Path(device_path)
        p = escpos_printer.File(str(dev))
        return cls(device_path=dev, _printer=p)

    def reset(self) -> None:
        if self._printer is None:
            raise RuntimeError("Impresora no inicializada")
        self._raw(b"\x1b@")

    def _raw(self, data: bytes) -> None:
        if self._printer is None:
            raise RuntimeError("Impresora no inicializada")
        # File driver expone _raw
        self._printer._raw(data)

    def advance_pixels(self, pixels: int) -> None:
        """
        Mueve film imprimiendo una tira blanca de `pixels` de alto.
        """
        if self._printer is None:
            raise RuntimeError("Impresora no inicializada")
        h = max(int(pixels), 1)
        try:
            from PIL import Image as Imge

            img = Imge.new("1", (35, h), 1)
            self._printer.image(img)
            self._raw(b"\n")
        except Exception:  # noqa: BLE001
            # Fallback: avance básico por salto de línea.
            self._raw(b"\n")

    def send_image(self, image: Any) -> None:
        if self._printer is None:
            raise RuntimeError("Impresora no inicializada")
        self._printer.image(image)
