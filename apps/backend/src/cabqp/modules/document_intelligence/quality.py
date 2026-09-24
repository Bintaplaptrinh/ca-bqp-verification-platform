from __future__ import annotations

import math
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from statistics import mean

from cabqp.shared.settings import get_settings


@lru_cache
def _versioned_config() -> dict:
    s = get_settings()
    path = Path(s.quality_config_path)
    if not path.is_absolute():
        candidates = [Path.cwd() / path, Path(__file__).resolve().parents[4] / path]
        path = next((x for x in candidates if x.exists()), candidates[0])
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _threshold(env_name: str, section: str, key: str, fallback):
    # Environment is an explicit deployment override; otherwise the versioned YAML owns thresholds.
    if os.getenv(env_name) is not None:
        return fallback
    return _versioned_config().get(section, {}).get(key, fallback)


def image_quality_thresholds() -> tuple[float, float]:
    """Return versioned blur and contrast gates for source images."""
    s = get_settings()
    return (
        float(_threshold("QUALITY_IMAGE_BLUR_VARIANCE_MIN", "image", "blur_variance_min", s.quality_image_blur_variance_min)),
        float(_threshold("QUALITY_IMAGE_CONTRAST_STD_MIN", "image", "contrast_std_min", s.quality_image_contrast_std_min)),
    )

VI_DIACRITICS = set("àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ")
ALLOWED_RE = re.compile(r"[A-Za-zÀ-ỹĐđ0-9 .,/:\\\-()\n\t]")
TOKEN_RE = re.compile(r"[A-Za-zÀ-ỹĐđ]+", re.UNICODE)

# Small built-in administrative lexicon. Production deployments may override/extend it
# without changing gate semantics; this list deliberately does not pretend to be a full dictionary.
COMMON_VI = {
    "bo", "bộ", "cong", "công", "an", "quoc", "quốc", "phong", "phòng", "cuc", "cục",
    "don", "đơn", "vi", "vị", "ho", "họ", "ten", "tên", "ngay", "ngày", "sinh", "chuc", "chức",
    "vu", "vụ", "hien", "hiện", "tai", "tại", "truong", "trường", "hoc", "học", "vien", "viện",
    "benh", "bệnh", "quan", "quân", "doi", "đội", "tinh", "tỉnh", "thanh", "thành", "pho", "phố",
}


class MetricState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(slots=True)
class MetricResult:
    name: str
    state: MetricState
    value: float | None = None
    threshold: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d


@dataclass(slots=True)
class QualityVector:
    metrics: dict[str, MetricResult] = field(default_factory=dict)
    threshold_version: str = "unknown"

    @property
    def failed(self) -> list[str]:
        return [k for k, v in self.metrics.items() if v.state == MetricState.FAIL]

    @property
    def gate_result(self) -> MetricState:
        return MetricState.FAIL if self.failed else MetricState.PASS

    def to_dict(self) -> dict:
        return {
            "gate_result": self.gate_result.value,
            "threshold_version": self.threshold_version,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
        }


def _finite_metric(name: str, value: float, predicate: bool, threshold: str) -> MetricResult:
    if not math.isfinite(value):
        return MetricResult(name, MetricState.FAIL, value=None, threshold=threshold, reason="non_finite")
    return MetricResult(name, MetricState.PASS if predicate else MetricState.FAIL, value=value, threshold=threshold)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    idx = max(0, min(len(xs) - 1, math.ceil(q * len(xs)) - 1))
    return float(xs[idx])


def _ioc(text: str) -> float:
    chars = [c.casefold() for c in text if c.isalpha()]
    n = len(chars)
    if n < 2:
        return float("nan")
    freqs: dict[str, int] = {}
    for c in chars:
        freqs[c] = freqs.get(c, 0) + 1
    # Normalized by alphabet-ish baseline so Vietnamese prose is typically > 1.
    return 26.0 * sum(v * (v - 1) for v in freqs.values()) / (n * (n - 1))


def _entropy(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return float("nan")
    freqs: dict[str, int] = {}
    for c in chars:
        freqs[c] = freqs.get(c, 0) + 1
    n = len(chars)
    return -sum((v / n) * math.log2(v / n) for v in freqs.values())


def _alpha_tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def evaluate_quality(
    text: str,
    *,
    ocr_scores: Iterable[float] | None = None,
    source: str = "PARSER",
    dictionary: set[str] | None = None,
) -> QualityVector:
    s = get_settings()
    conf_p10_min = float(_threshold("QUALITY_CONF_P10_MIN", "ocr", "conf_p10_min", s.quality_conf_p10_min))
    conf_min_threshold = float(_threshold("QUALITY_CONF_MIN", "ocr", "conf_min", s.quality_conf_min))
    low_conf_line = float(_threshold("QUALITY_LOW_CONF_LINE", "ocr", "low_conf_line", s.quality_low_conf_line))
    low_conf_ratio_max = float(_threshold("QUALITY_LOW_CONF_RATIO_MAX", "ocr", "low_conf_ratio_max", s.quality_low_conf_ratio_max))
    charset_violation_max = float(_threshold("QUALITY_CHARSET_VIOLATION_MAX", "text", "charset_violation_max", s.quality_charset_violation_max))
    min_alpha_chars = int(_threshold("QUALITY_MIN_ALPHA_CHARS", "text", "min_alpha_chars", s.quality_min_alpha_chars))
    min_tokens = int(_threshold("QUALITY_MIN_TOKENS", "text", "min_tokens", s.quality_min_tokens))
    min_alpha_token_ratio = float(_threshold("QUALITY_MIN_ALPHA_TOKEN_RATIO", "text", "min_alpha_token_ratio", s.quality_min_alpha_token_ratio))
    diacritic_ratio_min = float(_threshold("QUALITY_DIACRITIC_RATIO_MIN", "text", "diacritic_ratio_min", s.quality_diacritic_ratio_min))
    ioc_min_chars = int(_threshold("QUALITY_IOC_MIN_CHARS", "text", "ioc_min_chars", s.quality_ioc_min_chars))
    ioc_min = float(_threshold("QUALITY_IOC_MIN", "text", "ioc_min", s.quality_ioc_min))
    entropy_min = float(_threshold("QUALITY_ENTROPY_MIN", "text", "entropy_min", s.quality_entropy_min))
    scores = [float(x) for x in (ocr_scores or [])]
    metrics: dict[str, MetricResult] = {}
    alpha = [c for c in text if c.isalpha()]
    tokens = _alpha_tokens(text)
    alpha_token_ratio = len(tokens) / max(1, len(re.findall(r"\S+", text)))

    if scores:
        conf_p10 = _percentile(scores, 0.10)
        conf_min = min(scores)
        low_ratio = sum(x < low_conf_line for x in scores) / len(scores)
        metrics["conf_p10"] = _finite_metric("conf_p10", conf_p10, conf_p10 >= conf_p10_min, f">={conf_p10_min}")
        metrics["conf_min"] = _finite_metric("conf_min", conf_min, conf_min >= conf_min_threshold, f">={conf_min_threshold}")
        metrics["low_conf_ratio"] = _finite_metric("low_conf_ratio", low_ratio, low_ratio <= low_conf_ratio_max, f"<={low_conf_ratio_max}")
    else:
        for name in ("conf_p10", "conf_min", "low_conf_ratio"):
            metrics[name] = MetricResult(name, MetricState.NOT_APPLICABLE, reason="no_ocr_lines")

    if text:
        violation = sum(1 for c in text if not c.isspace() and not ALLOWED_RE.fullmatch(c)) / max(1, len(text))
        metrics["charset_violation_ratio"] = _finite_metric(
            "charset_violation_ratio", violation, violation <= charset_violation_max, f"<={charset_violation_max}"
        )
    else:
        metrics["charset_violation_ratio"] = MetricResult("charset_violation_ratio", MetricState.FAIL, reason="empty_text")

    long_prose = (
        len(alpha) >= min_alpha_chars
        and len(tokens) >= min_tokens
        and alpha_token_ratio >= min_alpha_token_ratio
    )
    if long_prose and source.upper() == "OCR":
        ratio = sum(c in VI_DIACRITICS for c in alpha) / max(1, len(alpha))
        metrics["diacritic_ratio"] = _finite_metric(
            "diacritic_ratio", ratio, ratio >= diacritic_ratio_min, f">={diacritic_ratio_min}"
        )
    else:
        reason = "direct_text_or_parser" if source.upper() != "OCR" else "insufficient_vietnamese_prose"
        metrics["diacritic_ratio"] = MetricResult("diacritic_ratio", MetricState.NOT_APPLICABLE, reason=reason)

    if long_prose:
        lex = dictionary or COMMON_VI
        hits = sum(t.casefold() in lex for t in tokens)
        ratio = hits / max(1, len(tokens))
        # Built-in lexicon is intentionally small: this signal is informational unless a custom dictionary is configured.
        if s.quality_dictionary_gate_enabled:
            metrics["dict_hit_ratio"] = _finite_metric("dict_hit_ratio", ratio, ratio >= s.quality_dict_hit_min, f">={s.quality_dict_hit_min}")
        else:
            metrics["dict_hit_ratio"] = MetricResult("dict_hit_ratio", MetricState.NOT_APPLICABLE, value=ratio, reason="dictionary_gate_disabled")
    else:
        metrics["dict_hit_ratio"] = MetricResult("dict_hit_ratio", MetricState.NOT_APPLICABLE, reason="insufficient_vietnamese_prose")

    # IoC/entropy are prose diagnostics. Short key/value dossiers can contain over
    # 100 letters but are still dominated by labels, identifiers and proper names;
    # applying a language-distribution threshold to those valid forms created false
    # failures for DOCX/PDF text-layer inputs. Only apply these signals after the
    # same prose-shape gate used by the dictionary/diacritic diagnostics.
    if long_prose and len(alpha) >= ioc_min_chars:
        v = _ioc(text)
        metrics["index_of_coincidence"] = _finite_metric("index_of_coincidence", v, v >= ioc_min, f">={ioc_min}")
        ent = _entropy(text)
        metrics["char_entropy"] = _finite_metric("char_entropy", ent, ent >= entropy_min, f">={entropy_min}")
    else:
        reason = "not_prose" if len(alpha) >= ioc_min_chars else "too_short"
        metrics["index_of_coincidence"] = MetricResult("index_of_coincidence", MetricState.NOT_APPLICABLE, reason=reason)
        metrics["char_entropy"] = MetricResult("char_entropy", MetricState.NOT_APPLICABLE, reason=reason)

    return QualityVector(metrics=metrics, threshold_version=str(_versioned_config().get("version", s.threshold_version)))


def confidence_from_quality(q: QualityVector) -> float:
    """Return a bounded diagnostic confidence, never used as a substitute for the gate."""
    vals: list[float] = []
    for m in q.metrics.values():
        if m.state == MetricState.NOT_APPLICABLE or m.value is None or not math.isfinite(m.value):
            continue
        if m.name in {"conf_p10", "conf_min", "dict_hit_ratio", "diacritic_ratio"}:
            vals.append(max(0.0, min(1.0, m.value)))
        elif m.name in {"low_conf_ratio", "charset_violation_ratio"}:
            vals.append(max(0.0, min(1.0, 1.0 - m.value)))
    if not vals:
        return 0.0 if q.gate_result == MetricState.FAIL else 0.75
    score = max(0.0, min(1.0, mean(vals)))
    if q.gate_result == MetricState.FAIL:
        # Only a subset of the metrics feed the score, so a document can fail on a metric
        # that is not averaged (index_of_coincidence, char_entropy) and still report full
        # confidence. Downstream routing compares this number against a threshold, so a
        # failed gate must never come back as a confident reading.
        return min(score, 0.5)
    return score
