from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import fitz
from openpyxl import Workbook
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.bulk.service import process_bulk_row, profile_and_validate, refresh_job_counts
from cabqp.modules.document_intelligence.quality import MetricState, evaluate_quality
from cabqp.modules.document_intelligence.router import route_input
from cabqp.shared.db import Base
from cabqp.shared.models import (
    BulkIngestJob,
    BulkIngestRow,
    Case,
    Person,
    PersonCode,
    ReviewCase,
    RowError,
    Source,
    Unit,
)
from cabqp.shared.normalization import ascii_key, normalize_text


def db_session() -> Session:
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_router_distinguishes_tabular_list_and_key_value_sheet():
    tabular = _xlsx([
        ['Họ và tên', 'CCCD', 'Đơn vị công tác'],
        ['Nguyễn Văn A', '001082946357', 'Cục Cảnh sát giao thông'],
        ['Trần Văn B', '001082946358', 'Cục Cảnh sát giao thông'],
    ])
    form = _xlsx([
        ['Họ và tên:', 'Nguyễn Văn A'],
        ['CCCD:', '001082946357'],
        ['Đơn vị công tác:', 'Cục Cảnh sát giao thông'],
    ])
    assert route_input('list.xlsx', tabular).kind.value == 'TABULAR_LIST'
    assert route_input('form.xlsx', form).kind.value == 'KEY_VALUE_SHEET'


def _digital_pdf(*, rotate: int = 0, low_entropy: bool = False) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    text = ('A' * 180) if low_entropy else (
        'Quyết định công tác tại Bộ Công an. Nguyễn Văn A được điều động đến '
        'Cục Cảnh sát giao thông để thực hiện nhiệm vụ chuyên môn. ' * 4
    )
    page.insert_textbox(page.rect + (36, 36, -36, -36), text, fontsize=11)
    if rotate:
        page.set_rotation(rotate)
    payload = doc.tobytes()
    doc.close()
    return payload


def _scan_pdf() -> bytes:
    image = Image.new('RGB', (1000, 1400), 'white')
    ImageDraw.Draw(image).text((50, 50), 'SCAN PAGE', fill='black')
    png = BytesIO()
    image.save(png, format='PNG')
    doc = fitz.open()
    page = doc.new_page(width=1000, height=1400)
    page.insert_image(page.rect, stream=png.getvalue())
    payload = doc.tobytes()
    doc.close()
    return payload


def test_golden_router_pdf_digital_scan_hybrid_rotation_and_bad_text_layer():
    digital = _digital_pdf()
    scan = _scan_pdf()
    assert route_input('digital.pdf', digital).kind.value == 'PDF_TEXT'
    assert route_input('scan.pdf', scan).kind.value == 'PDF_SCAN'

    hybrid = fitz.open()
    with fitz.open(stream=digital, filetype='pdf') as src:
        hybrid.insert_pdf(src)
    with fitz.open(stream=scan, filetype='pdf') as src:
        hybrid.insert_pdf(src)
    hybrid_bytes = hybrid.tobytes()
    hybrid.close()
    routed = route_input('hybrid.pdf', hybrid_bytes)
    assert routed.kind.value == 'PDF_HYBRID'
    assert [p.route for p in routed.page_route_map] == ['TEXT', 'OCR']

    rotated = route_input('rotated.pdf', _digital_pdf(rotate=90))
    assert rotated.page_route_map[0].rotation == 90

    corrupt = route_input('corrupt-layer.pdf', _digital_pdf(low_entropy=True))
    assert corrupt.kind.value == 'PDF_SCAN'
    assert 'low_char_entropy' in corrupt.page_route_map[0].reasons

    paths = fitz.open()
    page = paths.new_page()
    for i in range(12):
        page.draw_rect(fitz.Rect(40, 40 + i * 20, 300, 50 + i * 20))
    path_bytes = paths.tobytes()
    paths.close()
    path_route = route_input('text-as-paths.pdf', path_bytes)
    assert path_route.kind.value == 'PDF_SCAN'
    assert 'possible_text_as_paths' in path_route.page_route_map[0].reasons


def test_quality_gate_has_not_applicable_and_nan_fail_closed():
    short_code = evaluate_quality('C08', source='OCR')
    assert short_code.metrics['diacritic_ratio'].state == MetricState.NOT_APPLICABLE
    assert short_code.metrics['dict_hit_ratio'].state == MetricState.NOT_APPLICABLE
    assert short_code.gate_result == MetricState.PASS

    direct_no_accent = evaluate_quality('Nguyen Van A dang cong tac tai don vi C08. ' * 20, source='PARSER')
    assert direct_no_accent.metrics['diacritic_ratio'].state == MetricState.NOT_APPLICABLE

    nan_conf = evaluate_quality('Văn bản OCR hợp lệ', ocr_scores=[float('nan')], source='OCR')
    assert nan_conf.metrics['conf_p10'].state == MetricState.FAIL
    assert nan_conf.gate_result == MetricState.FAIL


def test_golden_batch_50_contract_and_idempotency():
    db = db_session()
    src = Source(authority='GOLDEN', url='https://example.invalid/csgt', source_kind='OFFICIAL')
    db.add(src)
    db.flush()
    db.add(Unit(
        id='u_csgt',
        canonical_name='Cục Cảnh sát giao thông',
        normalized_key=normalize_text('Cục Cảnh sát giao thông'),
        organization_type='BCA',
        qa_status='APPROVED',
        active=True,
        source_id=src.id,
        coverage_group='TEST',
    ))
    db.flush()

    # Every valid row supplies both person identity and CURRENT_WORK_UNIT, so the
    # batch contract now needs both registries populated. Rows 41-44 deliberately
    # keep a malformed unit assertion and must still be the four review cases.
    for i in [*range(1, 45), 49]:
        name = f'Nguyễn Văn {i}'
        person = Person(
            id=f'p{i}',
            full_name=name,
            normalized_key=normalize_text(name),
            ascii_key=ascii_key(name),
            canonical_unit_id='u_csgt',
            subject_group_hint='CAND',
            employment_status='ACTIVE',
            qa_status='APPROVED',
            source_kind='OFFICIAL',
            active=True,
        )
        db.add(person)
        db.flush()
        db.add(PersonCode(
            person_id=person.id,
            code=(f'{100000000000 + i:012d}' if i < 49 else '999999999999'),
            namespace='CCCD',
            qa_status='APPROVED',
        ))
    db.flush()

    rows: list[list[object]] = [['Họ và tên', 'CCCD', 'Chức vụ', 'Đơn vị công tác']]
    for i in range(1, 41):
        rows.append([f'Nguyễn Văn {i}', f'{100000000000 + i:012d}', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông'])
    for i in range(41, 45):
        rows.append([f'Nguyễn Văn {i}', f'{100000000000 + i:012d}', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông; Học viện Quốc phòng'])
    for i in range(45, 48):
        rows.append(['', f'{100000000000 + i:012d}', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông'])
    rows.append(['Nguyễn Văn 48', '12345', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông'])
    rows.append(['Nguyễn Văn 49', '999999999999', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông'])
    rows.append(['Nguyễn Văn 50', '999999999999', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông'])
    content = _xlsx(rows)

    job = BulkIngestJob(
        file_name='batch_50.xlsx',
        file_sha256=sha256(content).hexdigest(),
        status='UPLOADED',
        created_by='golden',
    )
    db.add(job)
    db.flush()
    mapping = {
        'Họ và tên': 'subject_name',
        'CCCD': 'subject_code',
        'Chức vụ': 'position',
        'Đơn vị công tác': 'unit_name',
    }
    profile_and_validate(db, job, content, user_mapping=mapping)
    db.flush()

    pending = list(db.scalars(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id, BulkIngestRow.status == 'PENDING')))
    assert len(pending) == 45
    for row in pending:
        process_bulk_row(db, row, job)
    refresh_job_counts(db, job)
    db.flush()

    assert db.scalar(select(func.count()).select_from(Case)) == 45
    assert db.scalar(select(func.count()).select_from(Case).where(Case.workflow_status == 'NEED_REVIEW')) == 4
    assert db.scalar(select(func.count()).select_from(Case).where(Case.workflow_status == 'COMPLETED')) == 41
    assert job.status == 'COMPLETED_WITH_ERRORS'
    assert job.succeeded == 45
    assert job.failed == 4
    assert job.skipped == 1

    errors = list(db.scalars(select(RowError).where(RowError.job_id == job.id)))
    assert {e.row_index for e in errors if e.code == 'MISSING_REQUIRED'} == {46, 47, 48}
    assert {e.column for e in errors if e.code == 'MISSING_REQUIRED'} == {'Họ và tên'}
    assert {e.row_index for e in errors if e.code == 'BAD_FORMAT'} == {49}
    assert {e.row_index for e in errors if e.code == 'DUPLICATE_IN_FILE'} == {51}

    # Re-processing the same job is idempotent because terminal rows short-circuit.
    all_rows = list(db.scalars(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id)))
    for row in all_rows:
        process_bulk_row(db, row, job)
    assert db.scalar(select(func.count()).select_from(Case)) == 45
    assert db.scalar(select(func.count()).select_from(ReviewCase)) == 4


def test_batch_invalid_date_and_numeric_like_bad_cccd_fail_phase1():
    db = db_session()
    content = _xlsx([
        ['Họ và tên', 'CCCD', 'Ngày đánh giá'],
        ['Nguyễn Văn A', '123-45', '2026-09-01'],
        ['Trần Văn B', '001082946357', '2026-99-01'],
    ])
    job = BulkIngestJob(file_name='bad.xlsx', file_sha256=sha256(content).hexdigest(), status='UPLOADED', created_by='u')
    db.add(job); db.flush()
    profile_and_validate(db, job, content, user_mapping={
        'Họ và tên': 'subject_name', 'CCCD': 'subject_code', 'Ngày đánh giá': 'as_of_date'
    })
    rows = list(db.scalars(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id).order_by(BulkIngestRow.row_index)))
    assert [r.status for r in rows] == ['FAILED', 'FAILED']
    errors = list(db.scalars(select(RowError).where(RowError.job_id == job.id).order_by(RowError.row_index)))
    assert errors[0].column == 'CCCD' and errors[0].code == 'BAD_FORMAT'
    assert errors[1].column == 'Ngày đánh giá' and errors[1].code == 'BAD_FORMAT'
    assert db.scalar(select(func.count()).select_from(Case)) == 0


def test_csv_metadata_column_cannot_duplicate_subject_name_mapping():
    db = db_session()
    content = (
        b"full_name,personal_code,current_unit,source_kind\n"
        b"Nguyen Van An,001082946357,Cuc Canh sat giao thong,SYNTHETIC_DEMO\n"
        b"Tran Thi Binh,001082946358,Bo Tu lenh Thu do Ha Noi,SYNTHETIC_DEMO\n"
    )
    job = BulkIngestJob(
        file_name="people.csv",
        file_sha256=sha256(content).hexdigest(),
        status="UPLOADED",
        created_by="u",
    )
    db.add(job)
    db.flush()

    profile_and_validate(db, job, content)

    assert job.mapping_json["full_name"] == "subject_name"
    assert job.mapping_json["source_kind"] is None
    assert list(job.mapping_json.values()).count("subject_name") == 1
    assert job.status == "PROFILED"


def test_batch_warning_always_routes_child_case_to_review():
    db = db_session()
    src = Source(authority='GOLDEN', url='https://example.invalid/csgt', source_kind='OFFICIAL')
    db.add(src); db.flush()
    db.add(Unit(
        id='u_warning', canonical_name='Cục Cảnh sát giao thông',
        normalized_key=normalize_text('Cục Cảnh sát giao thông'), organization_type='BCA',
        qa_status='APPROVED', active=True, source_id=src.id, coverage_group='TEST'
    )); db.flush()
    content = _xlsx([
        ['Họ và tên', 'CCCD', 'Chức vụ', 'Đơn vị công tác'],
        ['Nguyễn Văn A', '001082946357', 'Sĩ quan Công an', 'Cục Cảnh sát giao thông; Cục Cảnh sát giao thông'],
    ])
    job = BulkIngestJob(file_name='warning.xlsx', file_sha256=sha256(content).hexdigest(), status='UPLOADED', created_by='u')
    db.add(job); db.flush()
    profile_and_validate(db, job, content, user_mapping={
        'Họ và tên': 'subject_name', 'CCCD': 'subject_code', 'Chức vụ': 'position', 'Đơn vị công tác': 'unit_name'
    })
    row = db.scalar(select(BulkIngestRow).where(BulkIngestRow.job_id == job.id, BulkIngestRow.status == 'PENDING'))
    assert row is not None
    process_bulk_row(db, row, job); db.flush()
    case = db.get(Case, row.case_id)
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert case.workflow_status == 'NEED_REVIEW'
    assert review is not None and review.reason == 'AMBIGUOUS_UNIT'
