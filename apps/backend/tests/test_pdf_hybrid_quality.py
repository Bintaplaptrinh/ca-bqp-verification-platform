"""Hybrid PDF pages must all clear the quality gate.

A hybrid document mixes an extractable text layer with scanned pages. The text pages were
appended to the output without being graded, so a page whose font decodes to U+FFFD passed
review as long as the scanned pages happened to be clean.
"""
from __future__ import annotations

import pytest

import cabqp.modules.document_intelligence.parsers as parsers
from cabqp.modules.document_intelligence.router import InputKind, PageProbe, RoutingDecision

READABLE = "Dong chi Nguyen Van A hien cong tac tai Cuc Ky thuat theo quyet dinh so 12."
BROKEN_FONT = "�" * 400


class _StubRun:
    """Stands in for a clean OCR pass so the assertion isolates the text-page grading."""

    lines: list = []
    quality = {"gate_result": "PASS", "metrics": {}}
    confidence = 0.95
    evidence = {"selected_engine": "stub"}


def _pdf(pages: list[str]) -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 100), body, fontsize=11)
    content = doc.tobytes()
    doc.close()
    return content


@pytest.fixture
def hybrid_parser(monkeypatch):
    """Force the hybrid branch with a fixed page routing and a stubbed OCR engine."""

    def install(routes: list[str]):
        probes = [
            PageProbe(index + 1, route, 400, 0.0, 1, 2.0, 0.0, 0, ["forced"])
            for index, route in enumerate(routes)
        ]
        monkeypatch.setattr(
            parsers,
            "route_input",
            lambda file_name, content: RoutingDecision(
                InputKind.PDF_HYBRID, "pdf", "forced_hybrid", probes
            ),
        )
        monkeypatch.setattr(parsers, "run_ocr", lambda image, **kwargs: _StubRun())
        monkeypatch.setenv("SCAN_TABLE_DETECTION_ENABLED", "false")

    return install


def test_broken_text_layer_page_fails_the_document_gate(hybrid_parser):
    hybrid_parser(["TEXT", "OCR"])
    result = parsers.parse_document("hybrid.pdf", _pdf([BROKEN_FONT, READABLE]))

    assert result.method == "PDF_HYBRID"
    assert result.quality["gate_result"] == "FAIL"


def test_clean_hybrid_document_still_passes(hybrid_parser):
    """The guard must not turn every hybrid document into a review item."""
    hybrid_parser(["TEXT", "TEXT"])
    result = parsers.parse_document("hybrid_clean.pdf", _pdf([READABLE, READABLE]))

    assert result.quality["gate_result"] == "PASS"


def test_blank_text_page_does_not_fail_the_gate(hybrid_parser):
    """An empty page carries no evidence either way and must not be graded."""
    hybrid_parser(["TEXT", "TEXT"])
    result = parsers.parse_document("hybrid_blank.pdf", _pdf(["", READABLE]))

    assert result.quality["gate_result"] == "PASS"
