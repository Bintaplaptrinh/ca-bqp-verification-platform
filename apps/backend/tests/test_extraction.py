from cabqp.modules.document_intelligence.extraction import extract


def test_current_beats_former():
    x=extract('Đồng chí Nguyễn Văn A trước đây công tác tại Công an tỉnh An Giang. Hiện công tác tại Công an tỉnh Cà Mau.')
    assert 'Công an tỉnh Cà Mau' in (x.current_unit or '')
    assert any('Công an tỉnh An Giang' in y for y in x.former_units)
