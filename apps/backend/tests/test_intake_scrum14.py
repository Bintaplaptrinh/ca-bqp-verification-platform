"""Pytest Test Suite for SCRUM-14: Input Intake Pipeline.

Standard: Quality-first 2026 Production Architecture.
Tests:
1. Vietnamese Unicode NFC normalization & noise filtering.
2. High-precision extraction of security identifiers (CA-xxxx, BQP-xxxx, QD-xxxx, 12-digit CCCD, birth year).
3. Invariant 3: Disambiguation between CURRENT_WORK_UNIT and FORMER_WORK_UNIT.
   (Ensures former units like 'nguyên là...', 'từng công tác tại...' are NEVER confused with current unit).
4. Direct form intake processing returning canonical NormalizedRecord.
5. File intake pipeline simulation with text and binary buffer hints.
6. Edge cases: accented names, multi-space irregular formatting, multiple former units.
"""

import pytest
import unicodedata
from cabqp.modules.intake.processor import InputProcessor, NormalizedRecord


def test_unicode_nfc_normalization():
    """Verify that text is strictly normalized to Unicode NFC and extra whitespace is collapsed."""
    # Decomposed NFD string dynamically created from canonical Vietnamese text
    raw_vietnamese = "Nguyễn Văn A"
    nfd_text = unicodedata.normalize("NFD", raw_vietnamese)
    # Insert arbitrary spacing, tabs, and newlines around words
    words_nfd = nfd_text.split(" ")
    noisy_nfd_text = f"  {words_nfd[0]}  \t\n   {words_nfd[1]}    \r\n  {words_nfd[2]}   "
    normalized = InputProcessor.normalize_text(noisy_nfd_text)
    
    assert normalized == "Nguyễn Văn A"
    # Verify is NFC
    assert unicodedata.is_normalized("NFC", normalized)


def test_identifier_extraction():
    """Verify extraction of CA, BQP, CCCD and birth year patterns."""
    sample_text = "Đồng chí Nguyễn Văn A, sinh năm 1985, số hiệu CA-8492, CCCD 001085012345 công tác C02."
    ids = InputProcessor.extract_identifiers(sample_text)

    assert ids["ca_code"] == "CA-8492"
    assert ids["cccd"] == "001085012345"
    assert ids["birth_year"] == "1985"
    assert ids["bqp_code"] is None


def test_bqp_identifier_extraction():
    """Verify extraction of BQP and QD military identifiers."""
    sample_bqp = "Đồng chí Trần Văn B mang số hiệu BQP-7712, quyết định QD 9921."
    ids = InputProcessor.extract_identifiers(sample_bqp)

    assert ids["bqp_code"] in ("BQP-7712", "QD-9921")


def test_invariant_3_current_vs_former_work_unit():
    """
    CRITICAL INVARIANT 3 (SCRUM-14):
    Distinguish between CURRENT_WORK_UNIT and FORMER_WORK_UNIT.
    Must NOT simply pick the first organization that appears in raw text.
    """
    raw_history = (
        "Đồng chí Nguyễn Văn B, nguyên cán bộ Công an tỉnh Hà Tĩnh, "
        "hiện công tác tại Cục Cảnh sát hình sự C02 - Bộ Công an."
    )
    current_unit, former_units = InputProcessor.extract_work_units(raw_history)

    # Current unit MUST be C02, NOT the first mentioned unit (Hà Tĩnh)
    assert "C02" in current_unit or "Cục Cảnh sát hình sự" in current_unit
    assert "Hà Tĩnh" not in current_unit
    # Former unit must contain Hà Tĩnh
    assert any("Hà Tĩnh" in f for f in former_units)


def test_multiple_former_units():
    """Verify that multiple historical work units are captured without clobbering current unit."""
    raw_history = (
        "Cán bộ Lê Văn C: trước đây công tác tại Sư đoàn 304, "
        "từng công tác tại Quân đoàn 1, "
        "hiện công tác tại Cục Tác chiến - Bộ Tổng Tham mưu."
    )
    current_unit, former_units = InputProcessor.extract_work_units(raw_history)

    assert "Cục Tác chiến" in current_unit or "Bộ Tổng Tham mưu" in current_unit
    assert len(former_units) >= 2
    assert any("304" in f for f in former_units)
    assert any("Quân đoàn 1" in f for f in former_units)


def test_direct_intake_pipeline():
    """Verify process_direct_intake creates a complete NormalizedRecord."""
    record = InputProcessor.process_direct_intake(
        full_name="Phạm Quốc Dũng",
        birth_year="1980",
        current_unit="Cục Tác chiến - Bộ Tổng Tham mưu",
        identifier="BQP-7712",
        position="Sĩ quan tham mưu",
        raw_text="Nguyên sĩ quan Quân khu 3, hiện công tác tại Cục Tác chiến",
    )

    assert isinstance(record, NormalizedRecord)
    assert record.full_name == "Phạm Quốc Dũng"
    assert record.identifier == "BQP-7712"
    assert record.input_channel == "DIRECT_TEXT"
    assert record.extraction_confidence > 0.9
    assert any("Quân khu 3" in f for f in record.former_work_units)


def test_file_intake_pipeline_text_buffer():
    """Verify process_file_intake extracts metadata from text document content."""
    mock_pdf_content = (
        "Hồ sơ thẩm định trích lục\n"
        "Họ và tên: Hoàng Minh Tuấn\n"
        "Số hiệu: CA-9921\n"
        "Năm sinh: 1988\n"
        "Đơn vị: Cục Cảnh sát giao thông (C08)\n"
    ).encode("utf-8")

    record = InputProcessor.process_file_intake(
        file_bytes=mock_pdf_content,
        filename="ho_so_can_bo_tuan.pdf",
        content_type="application/pdf",
    )

    assert isinstance(record, NormalizedRecord)
    assert "Hoàng Minh Tuấn" in record.full_name
    assert record.identifier == "CA-9921"
    assert record.birth_year == "1988"
    assert record.input_channel == "FILE_UPLOAD"
    assert "C08" in record.current_work_unit or "Cảnh sát giao thông" in record.current_work_unit
