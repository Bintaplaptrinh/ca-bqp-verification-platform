from cabqp.modules.subject_group.service import classify_subject_group


def test_unit_alone_does_not_force_subject_group():
    g,conf,method=classify_subject_group(organization_type='BCA',position=None,text='Công tác tại Công an tỉnh Cà Mau',fields={})
    assert g is None
