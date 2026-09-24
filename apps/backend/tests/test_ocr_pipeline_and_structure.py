"""OCR engine-selection and scan-structure regressions.

Both guards decide whether a scanned dossier reaches a human. They failed in opposite
directions: a disagreement between engines still reported a high confidence, and a failed
structure call was reported as "this page contains a table".
"""
from __future__ import annotations

import pytest
from PIL import Image

import cabqp.modules.document_intelligence.ocr.pipeline as pipeline
from cabqp.modules.document_intelligence.ocr.base import OcrLine
from cabqp.modules.document_intelligence.table import scan_structure_contains_table
from cabqp.shared.settings import get_settings

CLEAN_READING = [
    ("Ho va ten: Nguyen Van A", 0.95),
    ("CCCD: 001082946357", 0.95),
    ("Don vi cong tac: Cuc Ky thuat", 0.94),
]
UNREADABLE = [("~~^^ |||l1I0O ###", 0.25), ("CCCD: 001082946357", 0.30)]
CONFLICTING_ID = [
    ("Ho va ten: Nguyen Van A", 0.95),
    ("CCCD: 001082999999", 0.95),
    ("Don vi cong tac: Cuc Ky thuat", 0.94),
]


class _FakeEngine:
    def __init__(self, name: str, lines: list[tuple[str, float]]):
        self.name = name
        self._lines = lines

    def run(self, image, *, page: int = 1) -> list[OcrLine]:
        return [OcrLine(text, conf, (0, 0, 10, 10), page, self.name) for text, conf in self._lines]


@pytest.fixture
def engines(monkeypatch):
    def install(primary: list[tuple[str, float]], fallback: list[tuple[str, float]]):
        def get_engine(detector=None, recognizer=None):
            if (detector, recognizer) == (None, None):
                return _FakeEngine("primary", primary)
            return _FakeEngine("fallback", fallback)

        monkeypatch.setattr(pipeline, "get_engine", get_engine)

    return install


@pytest.fixture
def settings_env(monkeypatch):
    """Apply environment overrides that Settings actually sees.

    ``get_settings`` is ``lru_cache``d, so setting the variable alone leaves the
    already-built Settings in place and the override silently does nothing.
    """
    def apply(**values: str):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


@pytest.fixture
def image() -> Image.Image:
    return Image.new("RGB", (50, 50), "white")


def test_engine_disagreement_on_identity_zeroes_confidence(engines, image, monkeypatch):
    """A failed gate must not be paired with a high score.

    Downstream routing compares the parse confidence against a threshold, so reporting
    0.97 alongside gate=FAIL would let a contested identity reading through.
    """
    monkeypatch.setenv("OCR_FALLBACK_ENABLED", "true")
    engines(UNREADABLE, CONFLICTING_ID)

    run = pipeline.run_ocr(image)

    assert run.evidence["critical_disagreement"] is True
    assert run.quality["gate_result"] == "FAIL"
    assert run.confidence == 0.0


def test_agreeing_engines_keep_their_confidence(engines, image, monkeypatch):
    monkeypatch.setenv("OCR_FALLBACK_ENABLED", "true")
    engines(CLEAN_READING, CLEAN_READING)

    run = pipeline.run_ocr(image)

    assert run.evidence["critical_disagreement"] is False
    assert run.confidence > 0.0


def test_blurred_input_cannot_report_high_confidence(engines, image, monkeypatch):
    monkeypatch.setenv("OCR_FALLBACK_ENABLED", "false")
    engines(CLEAN_READING, CLEAN_READING)

    run = pipeline.run_ocr(image)

    assert run.quality["gate_result"] == "FAIL"
    assert run.quality["reason"] == "INPUT_IMAGE_QUALITY_LOW"
    assert run.quality["metrics"]["image_blur_variance"]["state"] == "FAIL"
    assert run.confidence <= 0.5


def test_low_primary_confidence_triggers_the_fallback(engines, image, monkeypatch, settings_env):
    """A confident-looking gate pass is not enough: a weak reading must still be re-run.

    A short key/value scan produces few enough lines to pass every distribution metric
    while the recognizer itself is unsure, so mean recognition confidence is a fallback
    trigger of its own — that is what the VietOCR fallback exists for.
    """
    # Isolate the confidence trigger: a blurred source image would fire the fallback on
    # its own and the assertion below would prove nothing.
    monkeypatch.setattr(
        pipeline,
        "assess_image_quality",
        lambda image: {"blur_variance": 5000.0, "contrast_std": 60.0, "skew_angle": 0.0},
    )
    settings_env(OCR_FALLBACK_ENABLED="true", OCR_FALLBACK_CONFIDENCE_MIN="0.99")
    engines(CLEAN_READING, CLEAN_READING)

    run = pipeline.run_ocr(image)

    assert run.evidence["fallback_ran"] is True
    assert run.evidence["fallback_reason"] == "PRIMARY_CONFIDENCE_BELOW_THRESHOLD"
    assert run.quality["gate_result"] == "PASS"


def test_confident_primary_reading_does_not_run_the_fallback(engines, image, monkeypatch, settings_env):
    monkeypatch.setattr(
        pipeline,
        "assess_image_quality",
        lambda image: {"blur_variance": 5000.0, "contrast_std": 60.0, "skew_angle": 0.0},
    )
    settings_env(OCR_FALLBACK_ENABLED="true", OCR_FALLBACK_CONFIDENCE_MIN="0.70")
    engines(CLEAN_READING, UNREADABLE)

    run = pipeline.run_ocr(image)

    assert run.evidence["fallback_ran"] is False
    assert run.evidence["selected_engine"] == "primary"


def test_structure_error_is_not_reported_as_a_table():
    """PP-Structure diagnostics must not be mistaken for table evidence."""
    assert scan_structure_contains_table([{"pp_structure_error": "TableRecognitionError"}]) is False
    assert scan_structure_contains_table([{"pp_structure_error": "ImportError"}]) is False


def test_recognised_text_mentioning_a_table_is_not_a_table():
    """A page that merely says "bảng phân công" is prose, not a ruled table."""
    assert scan_structure_contains_table([{"res": {"rec_texts": ["Bang phan cong cong tac"]}}]) is False
    assert scan_structure_contains_table([{"res": {"rec_texts": ["table of contents"]}}]) is False


def test_real_table_structure_is_still_detected():
    assert scan_structure_contains_table([{"res": {"table_res_list": [{"html": "<table></table>"}]}}])
    assert scan_structure_contains_table([{"res": {"table_cells": [1, 2]}}])


def test_empty_structure_is_not_a_table():
    assert scan_structure_contains_table([]) is False


def test_one_sided_identity_evidence_is_a_disagreement(engines, image, monkeypatch):
    """If only one engine can read identity evidence, automatic acceptance is unsafe."""
    monkeypatch.setenv("OCR_FALLBACK_ENABLED", "true")
    engines(UNREADABLE, [("noise without an identifier", 0.95)])

    run = pipeline.run_ocr(image)

    assert run.evidence["critical_disagreement"] is True
    assert run.quality["gate_result"] == "FAIL"
    assert run.confidence == 0.0
