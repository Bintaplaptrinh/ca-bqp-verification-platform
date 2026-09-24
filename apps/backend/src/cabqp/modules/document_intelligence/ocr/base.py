from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

BBox = tuple[float, float, float, float]


@dataclass(slots=True)
class OcrLine:
    text: str
    conf: float
    bbox: BBox
    page: int = 1
    engine: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


class TextDetector(Protocol):
    name: str
    def detect(self, image) -> list[BBox]: ...


class TextRecognizer(Protocol):
    name: str
    def recognize(self, image, bboxes: list[BBox], *, page: int = 1) -> list[OcrLine]: ...


class OcrEngine(Protocol):
    name: str
    def run(self, image, *, page: int = 1) -> list[OcrLine]: ...
