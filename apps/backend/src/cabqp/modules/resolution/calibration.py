from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path

from cabqp.shared.settings import get_settings

FEATURES = ("fuzzy", "margin", "bm25", "semantic")


@dataclass(frozen=True)
class CalibrationResult:
    probability: float
    version: str
    method: str
    available: bool


_CACHE_LOCK = threading.Lock()
_PAYLOAD_CACHE: dict[str, tuple[float | None, dict | None]] = {}


class ResolverCalibrator:
    def __init__(self, path: str | Path | None = None):
        s = get_settings()
        self.path = Path(path) if path else s.calibration_file
        self.payload = self._load()

    def _load(self) -> dict | None:
        key = str(self.path)
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None

        with _CACHE_LOCK:
            cached = _PAYLOAD_CACHE.get(key)
            if cached and cached[0] == mtime:
                return cached[1]

        payload: dict | None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            payload = None

        with _CACHE_LOCK:
            _PAYLOAD_CACHE[key] = (mtime, payload)
        return payload

    @property
    def available(self) -> bool:
        return bool(self.payload and self.payload.get("method") == "logistic")

    @property
    def version(self) -> str:
        if not self.payload:
            return "calibration-unavailable"
        return str(self.payload.get("version", "calibration-unknown"))

    def predict(self, *, fuzzy: float, margin: float, bm25: float = 0.0, semantic: float = 0.0) -> CalibrationResult:
        if not self.available:
            # This fallback is for display only. Resolver policy can require a real calibration artifact for auto-accept.
            heuristic = max(0.0, min(1.0, (fuzzy / 100.0) * (0.75 + min(max(margin, 0.0), 30.0) / 120.0)))
            return CalibrationResult(heuristic, self.version, "heuristic-display-only", False)
        assert self.payload is not None
        coefs = self.payload.get("coefficients", {})
        intercept = float(self.payload.get("intercept", 0.0))
        values = {
            "fuzzy": max(0.0, min(1.0, fuzzy / 100.0)),
            "margin": max(0.0, min(1.0, margin / 100.0)),
            "bm25": max(0.0, min(1.0, bm25)),
            "semantic": max(0.0, min(1.0, semantic)),
        }
        z = intercept + sum(float(coefs.get(name, 0.0)) * values[name] for name in FEATURES)
        if z >= 0:
            probability = 1.0 / (1.0 + math.exp(-z))
        else:
            ez = math.exp(z)
            probability = ez / (1.0 + ez)
        return CalibrationResult(max(0.0, min(1.0, probability)), self.version, "logistic", True)
