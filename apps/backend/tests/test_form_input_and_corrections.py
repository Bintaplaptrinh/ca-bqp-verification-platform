"""Structured form entry, and re-running a Case with operator-corrected fields.

Two rules are pinned here:

- In FORM mode the submission must carry something to resolve (a unit) and
  somebody to attach the result to (a name or a personnel code). Free-text
  lookup is deliberately unaffected — there, extraction is the whole job.
- A correction produces a *new* Case that records what a human overrode and on
  which Case, so the machine's original reading stays available to compare
  against. The diff is computed server-side from the original's stored
  extraction, not taken from the client's word for it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cabqp.shared.schemas import CaseCreate
from cabqp.shared.settings import get_settings

# --- FORM-mode validation ----------------------------------------------------


def test_free_text_lookup_needs_only_text():
    """The free-text box is unchanged: anything non-blank is a valid lookup."""
    body = CaseCreate(text="Nguyễn Văn Hùng, Bệnh viện 19-8")
    assert body.input_mode == "TEXT"


def test_form_mode_accepts_a_code_and_a_unit():
    body = CaseCreate(
        text="Mã số: CA-2026-0417\nĐơn vị công tác: Bệnh viện 19-8",
        input_mode="FORM",
        subject_code="CA-2026-0417",
        unit_name="Bệnh viện 19-8",
    )
    assert body.subject_code == "CA-2026-0417"


def test_form_mode_accepts_a_name_and_a_unit():
    body = CaseCreate(
        text="Họ và tên: Nguyễn Văn Hùng\nĐơn vị công tác: Bệnh viện 19-8",
        input_mode="FORM",
        subject_name="Nguyễn Văn Hùng",
        unit_name="Bệnh viện 19-8",
    )
    assert body.subject_name == "Nguyễn Văn Hùng"


def test_form_mode_rejects_a_submission_with_neither_name_nor_code():
    with pytest.raises(ValidationError) as exc:
        CaseCreate(text="Đơn vị công tác: Bệnh viện 19-8", input_mode="FORM", unit_name="Bệnh viện 19-8")
    assert "mã số cán bộ hoặc họ và tên" in str(exc.value)


def test_form_mode_rejects_a_submission_with_no_unit():
    with pytest.raises(ValidationError) as exc:
        CaseCreate(text="Họ và tên: Nguyễn Văn Hùng", input_mode="FORM", subject_name="Nguyễn Văn Hùng")
    assert "Đơn vị công tác là bắt buộc" in str(exc.value)


def test_form_mode_treats_blank_strings_as_absent():
    """A whitespace-only box is an empty box, not a supplied value."""
    with pytest.raises(ValidationError):
        CaseCreate(
            text="x",
            input_mode="FORM",
            subject_name="   ",
            subject_code="",
            unit_name="Bệnh viện 19-8",
        )


def test_unit_code_alone_satisfies_the_unit_requirement():
    body = CaseCreate(
        text="x", input_mode="FORM", subject_code="CA-1", unit_code="BCA-91183111B5FE"
    )
    assert body.unit_code == "BCA-91183111B5FE"


# --- Correction flow ---------------------------------------------------------


@pytest.fixture
def client(app_database):
    from cabqp.main import app

    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_unit(app_database):
    """One QA-approved unit for the resolver to match against.

    Seeded the same way `test_golden_suites.py` does it — a Unit row with an
    APPROVED qa_status is what the resolver's canonical-exact tier reads.
    """
    from cabqp.shared.db import SessionLocal
    from cabqp.shared.models import Source, Unit
    from cabqp.shared.normalization import normalize_text

    name = "Bệnh viện 19-8"
    session = SessionLocal()
    try:
        if session.query(Unit).filter_by(id="unit_test_bv198").first() is None:
            source = Source(
                authority="TEST", url="https://example.invalid/bv198", source_kind="OFFICIAL"
            )
            session.add(source)
            session.flush()
            session.add(
                Unit(
                    id="unit_test_bv198",
                    canonical_name=name,
                    normalized_key=normalize_text(name),
                    organization_type="BCA",
                    qa_status="APPROVED",
                    active=True,
                    source_id=source.id,
                    coverage_group="BCA_CENTRAL_PUBLIC",
                )
            )
        session.commit()
    finally:
        session.close()
    yield name


def _create(client, **fields):
    response = client.post("/api/v1/cases/text", json=fields)
    assert response.status_code == 200, response.text
    return response.json()


def test_form_submission_is_refused_by_the_api_not_only_the_browser(client):
    """The rule holds for any client, including one that skips the form."""
    response = client.post(
        "/api/v1/cases/text",
        json={"text": "Đơn vị công tác: Bệnh viện 19-8", "input_mode": "FORM", "unit_name": "Bệnh viện 19-8"},
    )
    assert response.status_code == 422, response.text


def test_corrected_case_resolves_on_the_corrected_unit(client, seeded_unit):
    """The operator's value is what gets resolved, not the original misreading."""
    original = _create(
        client,
        text="Họ và tên: Lê Duy Tân\nĐơn vị công tác: Benh vien 19 8 sai chinh ta hoan toan",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name="Benh vien 19 8 sai chinh ta hoan toan",
    )
    corrected = _create(
        client,
        text=f"Họ và tên: Lê Duy Tân\nĐơn vị công tác: {seeded_unit}",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name=seeded_unit,
        corrected_from_case_id=original["case_id"],
    )
    assert corrected["case_id"] != original["case_id"], "a correction must not overwrite the original"
    assert corrected["corrected_from_case_id"] == original["case_id"]

    detail = client.get(f"/api/v1/cases/{corrected['case_id']}").json()
    assert detail["organization_type"] == "BCA"
    assert detail["resolution_status"] == "MATCHED"
    assert detail["current_unit"] == seeded_unit


def test_correction_evidence_records_what_the_operator_changed(client, seeded_unit):
    original = _create(
        client,
        text="Họ và tên: Le Duv Tan\nĐơn vị công tác: Benh vien mot chin tam",
        input_mode="FORM",
        subject_name="Le Duv Tan",
        unit_name="Benh vien mot chin tam",
    )
    corrected = _create(
        client,
        text=f"Họ và tên: Lê Duy Tân\nĐơn vị công tác: {seeded_unit}",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name=seeded_unit,
        corrected_from_case_id=original["case_id"],
    )

    evidence = client.get(f"/api/v1/cases/{corrected['case_id']}").json()["evidence"]
    correction = evidence["operator_correction"]
    assert correction["source_case_id"] == original["case_id"]
    assert set(correction["corrected_fields"]) == {"subject_name", "unit_name"}
    # The "from" side is read out of the original's stored extraction, so it is
    # what the pipeline produced rather than what the client claimed it showed.
    assert correction["changes"]["unit_name"]["from"] == "Benh vien mot chin tam"
    assert correction["changes"]["unit_name"]["to"] == seeded_unit


def test_an_untouched_field_is_not_reported_as_corrected(client, seeded_unit):
    original = _create(
        client,
        text="Họ và tên: Lê Duy Tân\nĐơn vị công tác: Sai don vi",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name="Sai don vi",
    )
    corrected = _create(
        client,
        text=f"Họ và tên: Lê Duy Tân\nĐơn vị công tác: {seeded_unit}",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name=seeded_unit,
        corrected_from_case_id=original["case_id"],
    )
    evidence = client.get(f"/api/v1/cases/{corrected['case_id']}").json()["evidence"]
    assert evidence["operator_correction"]["corrected_fields"] == ["unit_name"]


def test_the_original_case_is_left_intact(client, seeded_unit):
    """The machine's first reading stays available to compare against."""
    original = _create(
        client,
        text="Họ và tên: Lê Duy Tân\nĐơn vị công tác: Don vi khong ton tai",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name="Don vi khong ton tai",
    )
    before = client.get(f"/api/v1/cases/{original['case_id']}").json()
    _create(
        client,
        text=f"Họ và tên: Lê Duy Tân\nĐơn vị công tác: {seeded_unit}",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name=seeded_unit,
        corrected_from_case_id=original["case_id"],
    )
    after = client.get(f"/api/v1/cases/{original['case_id']}").json()
    assert after["current_unit"] == before["current_unit"]
    assert after["organization_type"] == before["organization_type"]
    assert after["evidence"]["operator_correction"] is None


def test_correcting_an_unknown_case_is_refused(client):
    response = client.post(
        "/api/v1/cases/text",
        json={
            "text": "Họ và tên: X\nĐơn vị công tác: Y",
            "input_mode": "FORM",
            "subject_name": "X",
            "unit_name": "Y",
            "corrected_from_case_id": "case_does_not_exist",
        },
    )
    assert response.status_code == 404


def test_a_correction_is_audited_as_its_own_action(client, seeded_unit):
    original = _create(
        client,
        text="Họ và tên: Lê Duy Tân\nĐơn vị công tác: Sai",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name="Sai",
    )
    corrected = _create(
        client,
        text=f"Họ và tên: Lê Duy Tân\nĐơn vị công tác: {seeded_unit}",
        input_mode="FORM",
        subject_name="Lê Duy Tân",
        unit_name=seeded_unit,
        corrected_from_case_id=original["case_id"],
    )
    entries = client.get("/api/v1/admin/audit", params={"limit": 200}).json()
    actions = {(x["action"], x["entity_id"]) for x in entries}
    assert ("CASE_CORRECTED", corrected["case_id"]) in actions
    assert ("CASE_CREATE", original["case_id"]) in actions
