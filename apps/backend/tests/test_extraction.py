from cabqp.modules.document_intelligence.extraction import extract


def test_current_beats_former():
    x=extract('Đồng chí Nguyễn Văn A trước đây công tác tại Công an tỉnh An Giang. Hiện công tác tại Công an tỉnh Cà Mau.')
    assert 'Công an tỉnh Cà Mau' in (x.current_unit or '')
    assert any('Công an tỉnh An Giang' in y for y in x.former_units)


def test_bare_person_name_accepts_lowercase_and_uppercase_without_diacritics():
    for raw in ("Nguyen Van An", "NGUYEN VAN AN", "nguyen van an"):
        result = extract(raw)
        assert result.subject_name == raw
        assert result.fields["field_evidence"]["subject_name"]["rule"] == "bare_name_query"


def test_unaccented_lowercase_narrative_keeps_raw_name_and_unit():
    raw = "dong chi nguyen van an hien cong tac tai cuc ky thuat"

    result = extract(raw)

    assert result.subject_name == "nguyen van an"
    assert result.current_unit == "cuc ky thuat"
    assert result.fields["field_evidence"]["subject_name"]["rule"] == "narrative_name"
    assert result.fields["field_evidence"]["current_unit"]["rule"] == "current_marker"


def test_lowercase_role_phrase_is_not_mistaken_for_a_bare_name():
    assert extract("si quan cong an").subject_name is None
