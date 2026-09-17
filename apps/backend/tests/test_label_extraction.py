"""Label/value extraction regressions.

Vietnamese dossiers are mostly "Nhãn: giá trị" lines. A free-form regex lets `\\s+` run
past the newline and absorb the next label, so these lock the parse to one line and check
that a unit cell holding only a short code is routed to the trusted-code tier.
"""
from __future__ import annotations

from cabqp.modules.document_intelligence.extraction import (
    _is_label,
    _looks_like_unit_code,
    extract,
    label_values,
    spatial_key_values,
)

DOSSIER = (
    "HỒ SƠ KIỂM TRA - DỮ LIỆU GIẢ LẬP\n"
    "\n"
    "Họ và tên: Nguyễn Văn Minh\n"
    "CCCD: 001082946357\n"
    "Chức vụ: Chuyên viên\n"
    "Đơn vị công tác: Cục Kỹ thuật\n"
)


def test_label_value_does_not_absorb_the_next_line():
    """The old regex produced 'Nguyễn Văn Minh\\nCCCD'."""
    result = extract(DOSSIER, {})
    assert result.subject_name == "Nguyễn Văn Minh"
    assert "\n" not in (result.subject_name or "")
    assert result.subject_code == "001082946357"
    assert result.position == "Chuyên viên"
    assert result.current_unit == "Cục Kỹ thuật"


def test_labels_are_read_without_diacritics():
    """Key/value sheets are often typed unaccented; labels must still be recognised."""
    plain = (
        "Ho va ten: Tran Quoc Bao\n"
        "Chuc vu: Can bo\n"
        "Don vi cong tac: Cuc Ky thuat\n"
    )
    values = label_values(plain)
    assert values["subject_name"] == "Tran Quoc Bao"
    assert values["position"] == "Can bo"
    assert values["unit_name"] == "Cuc Ky thuat"


def test_explicit_subject_group_label_is_preserved_for_validation():
    values = label_values("Nhóm đối tượng: BQP\n")

    assert values["subject_group"] == "BQP"


def test_is_label_scores_only_the_label_part_of_an_inline_line():
    assert _is_label("CCCD: 075201223344")
    assert _is_label("Chc v: Chuyen vien")
    assert not _is_label("Chuyen vien")


def test_ocr_lines_without_colons_or_label_spaces_keep_readable_values():
    """Low-quality scans often merge label words and drop the colon."""
    text = (
        "Movaten 0o Minh Quan\n"
        "CCCO: 075201223344\n"
        "Chucv Chuyenvien\n"
        "Nhom doi tuono BQP\n"
        "Don vi cono tac Cuc Ky thust\n"
    )

    result = extract(text, {})

    assert result.subject_name == "0o Minh Quan"
    assert result.subject_code == "075201223344"
    assert result.position == "Chuyenvien"
    assert result.current_unit == "Cuc Ky thust"
    assert result.fields["labelled_fields"]["subject_group"] == "BQP"


def test_spatial_extraction_rejects_an_inline_label_as_a_candidate_value():
    ocr_lines = [
        {"text": "Ho va ten", "conf": 0.99, "bbox": [10, 10, 100, 30], "page": 1},
        {"text": "CCCD: 075201223344", "conf": 0.99, "bbox": [110, 10, 260, 30], "page": 1},
    ]

    values, _ = spatial_key_values(ocr_lines)

    assert "subject_name" not in values
    assert values["subject_code"] == "075201223344"


def test_tab_separated_key_value_sheet_is_parsed():
    """XLSX label/value sheets arrive as tab-separated pairs rather than 'label: value'."""
    sheet = "Trường thông tin\tGiá trị\nHọ và tên:\tĐỗ Minh Quân\nĐơn vị công tác:\tCục Kỹ thuật"
    result = extract(sheet, {})
    assert result.subject_name == "Đỗ Minh Quân"
    assert result.current_unit == "Cục Kỹ thuật"


def test_unit_cell_holding_a_code_is_routed_to_unit_code():
    """'C08' names no unit on its own; it must reach the resolver as a code."""
    result = extract("Đơn vị công tác: C08\n", {})
    assert result.unit_code == "C08"
    assert result.current_unit is None


def test_unit_name_is_not_mistaken_for_a_code():
    result = extract("Đơn vị công tác: Cục Kỹ thuật\n", {})
    assert result.unit_code is None
    assert result.current_unit == "Cục Kỹ thuật"


def test_explicit_structured_unit_code_wins():
    result = extract("Đơn vị công tác: C08\n", {"unit_code": "BQP-HVQP"})
    assert result.unit_code == "BQP-HVQP"


def test_code_shape_requires_a_digit_or_hyphen():
    """A bare uppercase word is an abbreviation, not a code, and must stay a name."""
    assert _looks_like_unit_code("C08")
    assert _looks_like_unit_code("PK-KQ")
    assert not _looks_like_unit_code("CAND")
    assert not _looks_like_unit_code("Cục Kỹ thuật")
    assert not _looks_like_unit_code("")


def test_narrative_text_still_uses_current_work_unit_markers():
    """The label parser must not regress the narrative CURRENT/FORMER distinction."""
    narrative = (
        "Đồng chí Nguyễn Văn A trước đây công tác tại Công an tỉnh A. "
        "Hiện công tác tại Cục Cảnh sát giao thông."
    )
    result = extract(narrative, {})
    assert result.current_unit == "Cục Cảnh sát giao thông"
    assert "Công an tỉnh A" in result.former_units
    assert result.subject_name == "Nguyễn Văn A"
