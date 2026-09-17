"""A failed quality gate must never be paired with a confident score.

Only a subset of the quality metrics feed confidence_from_quality. A document can
therefore fail on a metric that is not averaged — index_of_coincidence or char_entropy —
and still report full confidence. Downstream routing compares that number against
OCR_MIN_CONFIDENCE / DOCUMENT_PARSE_MIN_CONFIDENCE, so the mismatch would wave through a
document the gate rejected.
"""
from __future__ import annotations

import pytest

from cabqp.modules.document_intelligence.quality import (
    MetricState,
    confidence_from_quality,
    evaluate_quality,
)

CLEAN_PROSE = (
    "Đồng chí Nguyễn Văn Minh sinh năm 1985, quê quán tỉnh Nghệ An, hiện đang công tác "
    "tại Cục Kỹ thuật thuộc Bộ Quốc phòng với chức vụ chuyên viên chính, đã có nhiều "
    "đóng góp trong công tác chuyên môn."
)
# A form-style dossier: short, heavy with identifiers, low index of coincidence.
FORM_DOSSIER = (
    "HỒ SƠ KIỂM TRA - PDF DIGITAL\n"
    "Họ và tên: Phạm Gia Huy\n"
    "CCCD: 075201223344\n"
    "Chức vụ: Chuyên viên\n"
    "Đơn vị công tác: Cục Kỹ thuật\n"
    "Ngày đánh giá: 14/09/2026\n"
)
OCR_GIBBERISH = "~~^^ |||l1I0O ###  $$ %%% &&& ((( ))) *** +++ ??? <<< >>> {{{ }}} @@@ ~~~ ^^^"


def _assess(text: str, **kwargs):
    quality = evaluate_quality(text, **kwargs)
    return quality, confidence_from_quality(quality)


@pytest.mark.parametrize("text", [FORM_DOSSIER, OCR_GIBBERISH, ""])
def test_failed_gate_never_reports_high_confidence(text):
    quality, confidence = _assess(text, source="PARSER")
    if quality.gate_result == MetricState.FAIL:
        assert confidence <= 0.5, (text[:40], confidence)


def test_clean_prose_keeps_a_high_score():
    """The clamp must not punish documents that actually pass."""
    quality, confidence = _assess(CLEAN_PROSE, source="PARSER")
    assert quality.gate_result == MetricState.PASS
    assert confidence > 0.5


def test_valid_short_form_is_not_rejected_by_prose_statistics():
    quality, confidence = _assess(FORM_DOSSIER, source="PARSER")

    assert quality.gate_result == MetricState.PASS
    assert quality.metrics["index_of_coincidence"].state == MetricState.NOT_APPLICABLE
    assert quality.metrics["index_of_coincidence"].reason in {"too_short", "not_prose"}
    assert confidence > 0.5


def test_gibberish_fails_and_scores_low():
    quality, confidence = _assess(OCR_GIBBERISH, source="PARSER")
    assert quality.gate_result == MetricState.FAIL
    assert confidence <= 0.5


def test_empty_text_fails_with_zero_confidence():
    quality, confidence = _assess("", source="PARSER")
    assert quality.gate_result == MetricState.FAIL
    assert confidence == 0.0


def test_confidence_stays_within_bounds():
    for text in (CLEAN_PROSE, FORM_DOSSIER, OCR_GIBBERISH, ""):
        _quality, confidence = _assess(text, source="PARSER")
        assert 0.0 <= confidence <= 1.0


def test_low_ocr_scores_fail_and_stay_below_the_threshold():
    """OCR line confidences are averaged in, so a bad scan must not slip past."""
    quality, confidence = _assess(
        "Ho va ten Nguyen Van A Don vi cong tac Cuc Ky thuat",
        ocr_scores=[0.10, 0.12, 0.09],
        source="OCR",
    )
    assert quality.gate_result == MetricState.FAIL
    assert confidence <= 0.5
