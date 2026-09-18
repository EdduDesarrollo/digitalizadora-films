from dataclasses import dataclass


@dataclass(frozen=True)
class RawItem:
    """Un RAW pendiente: nombre en cámara y nombre destino local (basename)."""

    raw_name: str
    dest_basename: str

    def as_pair(self) -> list:
        return [self.raw_name, self.dest_basename]
