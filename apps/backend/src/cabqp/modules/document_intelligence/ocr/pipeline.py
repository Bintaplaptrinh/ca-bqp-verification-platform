from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean

from PIL import Image

from cabqp.modules.document_intelligence.quality import (
    confidence_from_quality,
    evaluate_quality,
    image_quality_thresholds,
)
from cabqp.shared.normalization import ascii_key
from cabqp.shared.settings import get_settings

from .base import OcrLine
from .engines import get_engine
from .preprocess import assess_image_quality

_CRITICAL_WORDS = ('cccd', 'cmnd', 'ho ten', 'ho va ten', 'don vi', 'co quan')


@dataclass(slots=True)
class OcrRun:
    lines: list[OcrLine]
    quality: dict
    confidence: float
    evidence: dict


def _critical_signature(lines: list[OcrLine]) -> set[str]:
    out: set[str] = set()
    for line in lines:
        key = ascii_key(line.text)
        ids = re.findall(r'(?<!\d)(?:\d{9}|\d{12})(?!\d)', line.text)
        out.update(f'id:{x}' for x in ids)
        if any(word in key for word in _CRITICAL_WORDS):
            out.add(f'label:{key}')
    return out


def _quality(lines: list[OcrLine]):
    text = '\n'.join(x.text for x in lines)
    return evaluate_quality(text, ocr_scores=[x.conf for x in lines], source='OCR')


def run_ocr(image: Image.Image, *, page: int = 1, detector: str | None = None, recognizer: str | None = None) -> OcrRun:
    settings = get_settings()
    image_quality = assess_image_quality(image)
    blur_min, contrast_min = image_quality_thresholds()
    blur_ok = image_quality['blur_variance'] >= blur_min
    contrast_ok = image_quality['contrast_std'] >= contrast_min
    input_quality_low = not (blur_ok and contrast_ok)
    primary = get_engine(detector, recognizer)
    primary_lines = primary.run(image, page=page)
    primary_q = _quality(primary_lines)
    primary_score = mean([x.conf for x in primary_lines] or [0.0])
    # A recognizer that is merely unsure does not necessarily fail the quality gate:
    # short key/value scans produce few enough lines that a weak reading can still
    # pass every distribution metric. The mean recognition confidence is therefore a
    # fallback trigger in its own right, alongside a failed gate and a degraded source
    # image.
    low_confidence = primary_score < settings.ocr_fallback_confidence_min
    selected_lines = primary_lines
    selected_q = primary_q
    evidence = {
        'primary_engine': primary.name,
        'primary_confidence': primary_score,
        'fallback_ran': False,
        'critical_disagreement': False,
        'input_image_quality': image_quality,
    }

    if settings.ocr_fallback_enabled and (
        primary_q.gate_result.value == 'FAIL' or input_quality_low or low_confidence
    ):
        evidence['fallback_reason'] = (
            'PRIMARY_GATE_FAILED' if primary_q.gate_result.value == 'FAIL'
            else 'INPUT_IMAGE_QUALITY_LOW' if input_quality_low
            else 'PRIMARY_CONFIDENCE_BELOW_THRESHOLD'
        )
        fallback = get_engine(settings.ocr_fallback_detector, settings.ocr_fallback_recognizer)
        if fallback.name != primary.name:
            try:
                evidence['fallback_ran'] = True
                fallback_lines = fallback.run(image, page=page)
                fallback_q = _quality(fallback_lines)
                evidence['fallback_engine'] = fallback.name
                evidence['fallback_confidence'] = mean([x.conf for x in fallback_lines] or [0.0])
                primary_signature = _critical_signature(primary_lines)
                fallback_signature = _critical_signature(fallback_lines)
                if (primary_signature or fallback_signature) and primary_signature != fallback_signature:
                    evidence['critical_disagreement'] = True
                    evidence['primary_critical'] = sorted(primary_signature)
                    evidence['fallback_critical'] = sorted(fallback_signature)
                # Select one complete engine output; never splice/vote characters.
                selected_score = mean([x.conf for x in selected_lines] or [0.0])
                f_score = mean([x.conf for x in fallback_lines] or [0.0])
                if fallback_q.gate_result.value == 'PASS' and (
                    selected_q.gate_result.value == 'FAIL' or f_score > selected_score
                ):
                    selected_lines, selected_q = fallback_lines, fallback_q
            except Exception as exc:
                evidence['fallback_ran'] = True
                evidence['fallback_engine'] = fallback.name
                evidence['fallback_error_type'] = type(exc).__name__

    quality = selected_q.to_dict()
    quality['metrics']['image_blur_variance'] = {
        'name': 'image_blur_variance',
        'state': 'PASS' if blur_ok else 'FAIL',
        'value': image_quality['blur_variance'],
        'threshold': f'>={blur_min}',
        'reason': None if blur_ok else 'source_image_blurred',
    }
    quality['metrics']['image_contrast_std'] = {
        'name': 'image_contrast_std',
        'state': 'PASS' if contrast_ok else 'FAIL',
        'value': image_quality['contrast_std'],
        'threshold': f'>={contrast_min}',
        'reason': None if contrast_ok else 'source_image_low_contrast',
    }
    confidence = confidence_from_quality(selected_q)
    if input_quality_low:
        quality['gate_result'] = 'FAIL'
        quality['reason'] = 'INPUT_IMAGE_QUALITY_LOW'
        confidence = min(confidence, 0.5)
    if evidence['critical_disagreement']:
        quality['gate_result'] = 'FAIL'
        quality['critical_disagreement'] = True
        # The engines read different identity fields, so neither reading is trustworthy.
        # Leaving the per-engine confidence intact reported a failed gate alongside a high
        # score, and downstream confidence checks would then wave the case through.
        confidence = 0.0
    evidence['selected_engine'] = selected_lines[0].engine if selected_lines else primary.name
    return OcrRun(selected_lines, quality, confidence, evidence)
