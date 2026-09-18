from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    current: int
    total: int
    message: str

    @property
    def fraction(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(1.0, self.current / self.total)
