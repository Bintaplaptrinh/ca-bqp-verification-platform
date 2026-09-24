"""Routing decisions for the shipped sample dossiers.

The router picks the parse strategy for every upload, and a wrong pick is silent: a roster
routed as a single document becomes one Case instead of many, and a scanned page routed as
text yields an empty extraction. These pin the decision for each fixture in
datasets/samples, which the fixture README documents as the expected behaviour.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from cabqp.modules.document_intelligence.extraction import extract
from cabqp.modules.document_intelligence.file_validation import detect_type
from cabqp.modules.document_intelligence.ocr.preprocess import assess_image_quality
from cabqp.modules.document_intelligence.parsers import parse_document
from cabqp.modules.document_intelligence.quality import image_quality_thresholds
from cabqp.modules.document_intelligence.router import route_input

SAMPLES = Path(__file__).resolve().parents[3] / "datasets" / "samples"
requires_samples = pytest.mark.skipif(
    not SAMPLES.is_dir(), reason="sample dossiers are not present in this checkout"
)


def _read(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


@requires_samples
@pytest.mark.parametrize(
    "name,expected_detect,expected_kind",
    [
        ("01_text_valid.txt", "text", "TEXT"),
        ("02_text_no_diacritics.txt", "text", "TEXT"),
        ("03_docx_valid.docx", "docx", "DOCX"),
        ("04_pdf_digital_valid.pdf", "pdf", "PDF_TEXT"),
        ("05_pdf_hybrid.pdf", "pdf", "PDF_HYBRID"),
        ("05_batch_mixed.xlsx", "xlsx", "TABULAR_LIST"),
        ("06_key_value_sheet.xlsx", "xlsx", "KEY_VALUE_SHEET"),
        ("07_scan_valid.png", "png", "IMAGE"),
        ("08_scan_low_quality.png", "png", "IMAGE"),
        ("09_batch_small.csv", "text", "TABULAR_LIST"),
    ],
)
def test_sample_files_route_as_documented(name, expected_detect, expected_kind):
    content = _read(name)
    assert detect_type(content) == expected_detect
    assert route_input(name, content).kind.value == expected_kind


@requires_samples
def test_hybrid_pdf_routes_each_page_separately():
    """A hybrid dossier must not be forced wholesale into one strategy."""
    decision = route_input("05_pdf_hybrid.pdf", _read("05_pdf_hybrid.pdf"))

    routes = {probe.page: probe.route for probe in decision.page_route_map}
    assert len(routes) >= 2
    assert set(routes.values()) == {"TEXT", "OCR"}


@requires_samples
def test_roster_is_recognised_as_a_list_not_a_single_document():
    """A roster must reach bulk ingestion; parsing it as one Case would lose every row."""
    decision = route_input("05_batch_mixed.xlsx", _read("05_batch_mixed.xlsx"))
    profile = decision.tabular_profile

    assert decision.kind.value == "TABULAR_LIST"
    assert profile["data_rows"] >= 2
    assert profile["rectangularity"] >= 0.7
    assert profile["key_signal"] is True


@requires_samples
def test_key_value_sheet_is_not_mistaken_for_a_roster():
    """A two-column label/value sheet describes one person, not a list of them."""
    decision = route_input("06_key_value_sheet.xlsx", _read("06_key_value_sheet.xlsx"))

    assert decision.kind.value == "KEY_VALUE_SHEET"
    assert decision.tabular_profile["n_cols"] <= 2


@requires_samples
def test_digital_pdf_is_not_sent_to_ocr():
    """OCR on an extractable text layer only adds recognition error."""
    decision = route_input("04_pdf_digital_valid.pdf", _read("04_pdf_digital_valid.pdf"))

    assert decision.kind.value == "PDF_TEXT"
    assert all(probe.route == "TEXT" for probe in decision.page_route_map)


@requires_samples
def test_scanned_images_require_ocr():
    for name in ("07_scan_valid.png", "08_scan_low_quality.png"):
        decision = route_input(name, _read(name))
        assert decision.kind.value == "IMAGE"
        assert "ocr" in decision.reason.casefold()


@requires_samples
def test_low_quality_scan_is_distinguished_from_clear_scan():
    blur_min, contrast_min = image_quality_thresholds()
    clear = assess_image_quality(Image.open(SAMPLES / "07_scan_valid.png"))
    degraded = assess_image_quality(Image.open(SAMPLES / "08_scan_low_quality.png"))

    assert clear["blur_variance"] >= blur_min
    assert clear["contrast_std"] >= contrast_min
    assert degraded["blur_variance"] < blur_min


@requires_samples
@pytest.mark.parametrize(
    "name,expected_method,expected_fields",
    [
        (
            "01_text_valid.txt",
            "PLAIN_TEXT",
            {
                "subject_name": "Nguyễn Văn Minh",
                "subject_code": "001082946357",
                "position": "Chuyên viên",
                "current_unit": "Cục Kỹ thuật",
                "unit_code": None,
                "subject_group": "BQP",
            },
        ),
        (
            "02_text_no_diacritics.txt",
            "PLAIN_TEXT",
            {
                "subject_name": "Tran Quoc Bao",
                "subject_code": "079203004567",
                "position": "Can bo",
                "current_unit": None,
                "unit_code": "C08",
                "subject_group": "BCA",
            },
        ),
        (
            "03_docx_valid.docx",
            "DOCX_TEXT",
            {
                "subject_name": "Lê Hoàng Nam",
                "subject_code": "036199001234",
                "position": "Chuyên viên",
                "current_unit": "Học viện Kỹ thuật Quân sự",
                "unit_code": None,
                "subject_group": "BQP",
            },
        ),
        (
            "04_pdf_digital_valid.pdf",
            "PDF_TEXT",
            {
                "subject_name": "Phạm Gia Huy",
                "subject_code": "075201223344",
                "position": "Chuyên viên",
                "current_unit": "Cục Kỹ thuật",
                "unit_code": None,
                "subject_group": "BQP",
            },
        ),
        (
            "06_key_value_sheet.xlsx",
            "KEY_VALUE",
            {
                "subject_name": "Đỗ Minh Quân",
                "subject_code": "075201223344",
                "position": "Chuyên viên",
                "current_unit": "Cục Kỹ thuật",
                "unit_code": None,
                "subject_group": "BQP",
            },
        ),
    ],
)
def test_sample_documents_parse_and_extract_expected_fields(
    name, expected_method, expected_fields
):
    """Pin real values, not merely the route chosen for each representative file."""
    parsed = parse_document(name, _read(name))
    extracted = extract(parsed.text)

    assert parsed.method == expected_method
    assert parsed.quality["gate_result"] == "PASS"
    assert extracted.subject_name == expected_fields["subject_name"]
    assert extracted.subject_code == expected_fields["subject_code"]
    assert extracted.position == expected_fields["position"]
    assert extracted.current_unit == expected_fields["current_unit"]
    assert extracted.unit_code == expected_fields["unit_code"]
    assert (
        extracted.fields["labelled_fields"].get("subject_group")
        == expected_fields["subject_group"]
    )
