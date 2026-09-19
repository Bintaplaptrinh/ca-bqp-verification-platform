from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.cases.service import process_case
from cabqp.modules.person_resolution.service import PersonResolver
from cabqp.modules.resolution.service import Resolver
from cabqp.shared.db import Base
from cabqp.shared.models import Case, Person, PersonCode, ReviewCase, Source, Unit
from cabqp.shared.normalization import ascii_key, normalize_text


def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_unit(db: Session, uid: str, name: str, org: str, coverage: str = "TEST") -> Unit:
    src = Source(authority="TEST", url=f"https://example.invalid/{uid}", source_kind="OFFICIAL")
    db.add(src)
    db.flush()
    unit = Unit(
        id=uid,
        canonical_name=name,
        normalized_key=normalize_text(name),
        ascii_key=ascii_key(name),
        organization_type=org,
        coverage_group=coverage,
        qa_status="APPROVED",
        active=True,
        source_id=src.id,
    )
    db.add(unit)
    db.flush()
    return unit


def seed_person(
    db: Session,
    *,
    pid: str,
    name: str,
    unit_id: str,
    birth_year: int | None = None,
    code: str | None = None,
    source_kind: str = "PROVIDED",
    group: str | None = "CAND",
) -> Person:
    p = Person(
        id=pid,
        full_name=name,
        normalized_key=normalize_text(name),
        ascii_key=ascii_key(name),
        birth_year=birth_year,
        canonical_unit_id=unit_id,
        subject_group_hint=group,
        employment_status="ACTIVE",
        qa_status="APPROVED",
        source_kind=source_kind,
        active=True,
        synthetic_welfare_facts={"synthetic_salary_million": 23.65}
        if source_kind == "SYNTHETIC_DEMO"
        else None,
    )
    db.add(p)
    db.flush()
    if code:
        db.add(
            PersonCode(
                person_id=pid,
                code=code,
                namespace="TEST",
                qa_status="APPROVED",
            )
        )
        db.flush()
    return p


def test_person_trusted_code_wins_and_has_no_org_type():
    db = db_session()
    seed_unit(db, "u1", "Bệnh viện 19-8", "BCA")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1", code="P001")
    out = PersonResolver(db).resolve(personal_code="P001")
    assert out.status == "MATCHED"
    assert out.person_id == "p1"
    assert out.match_method == "TRUSTED_PERSON_CODE"
    assert not hasattr(out, "organization_type")


def test_person_code_name_conflict_abstains():
    db = db_session()
    seed_unit(db, "u1", "Bệnh viện 19-8", "BCA")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1", code="P001")
    seed_person(db, pid="p2", name="Trần Văn B", unit_id="u1", code="P002")
    out = PersonResolver(db).resolve(full_name="Trần Văn B", personal_code="P001")
    assert out.status == "CONFLICT"
    assert out.person_id is None
    assert out.decision_confidence == 0.0


def test_person_name_collision_across_orgs_is_ambiguous():
    db = db_session()
    seed_unit(db, "u_bca", "Bệnh viện 19-8", "BCA")
    seed_unit(db, "u_bqp", "Bệnh viện Quân y 175", "BQP")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u_bca", birth_year=1988)
    seed_person(db, pid="p2", name="Nguyễn Văn A", unit_id="u_bqp", birth_year=1990)
    out = PersonResolver(db).resolve(full_name="Nguyễn Văn A")
    assert out.status == "AMBIGUOUS"
    assert {c["person_id"] for c in out.candidates} == {"p1", "p2"}




def test_ambiguous_synthetic_roster_preserves_top_level_provenance():
    db = db_session()
    seed_unit(db, "u1", "Đơn vị Một", "BCA")
    seed_unit(db, "u2", "Đơn vị Hai", "BQP")
    seed_person(db, pid="p1", name="Nguyễn Văn Demo", unit_id="u1", source_kind="SYNTHETIC_DEMO")
    seed_person(db, pid="p2", name="Nguyễn Văn Demo", unit_id="u2", source_kind="SYNTHETIC_DEMO")
    out = PersonResolver(db).resolve(full_name="Nguyễn Văn Demo")
    assert out.status == "AMBIGUOUS"
    assert out.source_kind == "SYNTHETIC_DEMO"
    assert {c["source_kind"] for c in out.candidates} == {"SYNTHETIC_DEMO"}

def test_person_narrowing_by_birth_year_and_unit():
    db = db_session()
    seed_unit(db, "u1", "Đơn vị Một", "BCA")
    seed_unit(db, "u2", "Đơn vị Hai", "BQP")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1", birth_year=1988)
    seed_person(db, pid="p2", name="Nguyễn Văn A", unit_id="u2", birth_year=1990)
    by_year = PersonResolver(db).resolve(full_name="Nguyễn Văn A", birth_year=1990)
    by_unit = PersonResolver(db).resolve(full_name="Nguyễn Văn A", unit_id="u1")
    assert by_year.status == "MATCHED" and by_year.person_id == "p2"
    assert by_unit.status == "MATCHED" and by_unit.person_id == "p1"


def test_same_org_diacritic_fold_collision_still_abstains():
    db = db_session()
    seed_unit(db, "u1", "Đơn vị Một", "BCA")
    seed_person(db, pid="p1", name="Đỗ Minh Quân", unit_id="u1")
    seed_person(db, pid="p2", name="Do Minh Quan", unit_id="u1")
    out = PersonResolver(db).resolve(full_name="Đỗ Minh Quan")
    assert out.status == "AMBIGUOUS"
    assert {c["person_id"] for c in out.candidates} == {"p1", "p2"}


def test_person_not_found_stays_not_found_and_synthetic_label_survives():
    db = db_session()
    seed_unit(db, "u1", "Đơn vị Một", "BCA")
    seed_person(
        db,
        pid="p1",
        name="Nguyễn Văn A",
        unit_id="u1",
        code="SYN-1",
        source_kind="SYNTHETIC_DEMO",
    )
    matched = PersonResolver(db).resolve(personal_code="SYN-1")
    missing = PersonResolver(db).resolve(full_name="Tên Hoàn Toàn Không Có Trong Roster XYZ")
    assert matched.source_kind == "SYNTHETIC_DEMO"
    assert matched.synthetic_welfare_facts == {"synthetic_salary_million": 23.65}
    assert missing.status == "NOT_FOUND"
    assert missing.person_id is None


def test_abbreviated_name_does_not_return_fuzzy_autocomplete_candidates():
    db = db_session()
    seed_unit(db, "u1", "Test Unit", "BCA")
    seed_person(db, pid="p1", name="Nguyen Van An", unit_id="u1")
    seed_person(db, pid="p2", name="Nguyen Van Nam", unit_id="u1")

    out = PersonResolver(db).resolve(full_name="Nguyen Van A")

    assert out.status == "NOT_FOUND"
    assert out.match_method == "INCOMPLETE_NAME_QUERY"
    assert out.score is None
    assert out.candidates == []


def test_below_threshold_name_similarity_is_not_an_identity_candidate():
    db = db_session()
    seed_unit(db, "u1", "Test Unit", "BCA")
    seed_person(db, pid="p1", name="Tran Minh Tu", unit_id="u1")
    seed_person(db, pid="p2", name="Tran Minh Mai", unit_id="u1")

    out = PersonResolver(db).resolve(full_name="Tran Minh Tam")

    assert out.status == "NOT_FOUND"
    assert out.match_method == "FUZZY_NAME"
    assert out.candidates == []


def test_unit_resolver_trusted_unit_id_handoff():
    db = db_session()
    seed_unit(db, "u1", "Bệnh viện 19-8", "BCA")
    out = Resolver(db).resolve(unit_id="u1")
    assert out.status == "MATCHED"
    assert out.organization_type == "BCA"
    assert out.match_method == "TRUSTED_UNIT_ID"


def test_bare_name_case_handoff_resolves_org_and_completes():
    db = db_session()
    seed_unit(db, "u1", "Bệnh viện 19-8", "BCA", coverage="BCA_CENTRAL_PUBLIC")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1", birth_year=1988)
    structured = {
        "text": "Nguyễn Văn A",
        "subject_name": "Nguyễn Văn A",
        "business_fields": {"birth_year": 1988},
    }
    case = Case(created_by="tester", input_type="TEXT", raw_text="Nguyễn Văn A", input_payload=structured)
    db.add(case)
    db.flush()
    result = process_case(db, case, structured)
    assert result.resolution_status == "MATCHED"
    assert result.organization_type == "BCA"
    assert result.unit_id == "u1"
    assert result.evidence["person_resolution"]["person_id"] == "p1"
    assert result.evidence["canonical_name"] == "Bệnh viện 19-8"
    assert case.workflow_status == "COMPLETED"


def test_bare_name_collision_routes_to_person_review():
    db = db_session()
    seed_unit(db, "u1", "Đơn vị BCA", "BCA", coverage="BCA_TEST")
    seed_unit(db, "u2", "Đơn vị BQP", "BQP", coverage="BQP_TEST")
    seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1")
    seed_person(db, pid="p2", name="Nguyễn Văn A", unit_id="u2")
    structured = {"text": "Nguyễn Văn A", "subject_name": "Nguyễn Văn A", "business_fields": {}}
    case = Case(created_by="tester", input_type="TEXT", raw_text="Nguyễn Văn A", input_payload=structured)
    db.add(case)
    db.flush()
    result = process_case(db, case, structured)
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert result.resolution_status == "AMBIGUOUS"
    assert result.organization_type == "UNKNOWN"
    assert case.workflow_status == "NEED_REVIEW"
    assert review is not None and review.reason == "PERSON_AMBIGUOUS"
    assert len(result.evidence["person_resolution"]["candidates"]) == 2


def test_api_bare_name_case_exposes_person_and_scope_contract():
    from fastapi.testclient import TestClient

    from cabqp.main import app
    from cabqp.shared.db import get_db

    db = db_session()
    seed_unit(db, "u_api", "Bệnh viện 19-8", "BCA", coverage="BCA_CENTRAL_PUBLIC")
    seed_person(db, pid="p_api", name="Nguyễn Văn API", unit_id="u_api", birth_year=1987)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/cases/text",
            json={
                "text": "Nguyễn Văn API",
                "business_fields": {"birth_year": 1987},
            },
        )
        assert created.status_code == 200, created.text
        detail = client.get(f"/api/v1/cases/{created.json()['case_id']}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["person"]["person_id"] == "p_api"
        assert body["current_unit"] == "Bệnh viện 19-8"
        assert body["organization_type"] == "BCA"
        assert body["in_scope"] is True
        assert body["resolution_status"] == "MATCHED"
        assert body["verification_status"] == "Đã xác định"
        assert body["salary_status"] == "Không đủ dữ liệu"
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_api_multi_subject_text_creates_one_case_per_person():
    from fastapi.testclient import TestClient

    from cabqp.main import app
    from cabqp.shared.db import get_db
    from cabqp.shared.models import Case

    db=db_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db]=override_db
    try:
        client=TestClient(app)
        created=client.post(
            "/api/v1/cases/text",
            json={"text":"""Họ và tên: Nguyễn Văn Một
CCCD: 001082946111
Đơn vị công tác: Cục Kỹ thuật

Họ và tên: Trần Thị Hai
CCCD: 001082946222
Đơn vị công tác: Cục Chính trị"""},
        )
        assert created.status_code == 200,created.text
        payload=created.json()
        assert payload["subject_count"] == 2
        assert len(payload["case_ids"]) == 2
        cases=[db.get(Case,case_id) for case_id in payload["case_ids"]]
        assert [case.raw_text.splitlines()[0] for case in cases] == [
            "Họ và tên: Nguyễn Văn Một","Họ và tên: Trần Thị Hai"
        ]
    finally:
        app.dependency_overrides.pop(get_db,None)
        db.close()


def test_api_case_subjects_lists_the_whole_split_group():
    """Every Case in a multi-subject document can enumerate its siblings.

    The frontend shows a roster of names for such a document instead of the first
    person's verdict, so each member has to answer with the same ordered group,
    and a single-subject Case has to answer with exactly itself.
    """
    from fastapi.testclient import TestClient

    from cabqp.main import app
    from cabqp.shared.db import get_db

    db = db_session()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/cases/text",
            json={"text": """Họ và tên: Nguyễn Văn Một
CCCD: 001082946111
Đơn vị công tác: Cục Kỹ thuật

Họ và tên: Trần Thị Hai
CCCD: 001082946222
Đơn vị công tác: Cục Chính trị"""},
        )
        assert created.status_code == 200, created.text
        case_ids = created.json()["case_ids"]
        assert len(case_ids) == 2

        for case_id in case_ids:
            listed = client.get(f"/api/v1/cases/{case_id}/subjects")
            assert listed.status_code == 200, listed.text
            group = listed.json()
            assert group["subject_count"] == 2
            assert [row["block_index"] for row in group["items"]] == [0, 1]
            assert [row["case_id"] for row in group["items"]] == case_ids
            assert [row["subject_name"] for row in group["items"]] == [
                "Nguyễn Văn Một",
                "Trần Thị Hai",
            ]

        single = client.post("/api/v1/cases/text", json={"text": "Họ và tên: Lê Văn Đơn"})
        assert single.status_code == 200, single.text
        solo = client.get(f"/api/v1/cases/{single.json()['case_id']}/subjects")
        assert solo.status_code == 200, solo.text
        assert solo.json()["subject_count"] == 1
        assert solo.json()["items"][0]["case_id"] == single.json()["case_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_person_registry_qa_publish_snapshot_roundtrip():
    from cabqp.modules.person_resolution.registry_service import PersonRegistryService
    from cabqp.shared.models import PersonRegistrySnapshot
    from cabqp.shared.schemas import PersonCreate, PersonQADecision

    db = db_session()
    seed_unit(db, "u_pub", "Đơn vị Publish", "BCA")
    svc = PersonRegistryService(db, actor="admin-test")
    person = svc.create_person(
        PersonCreate(
            full_name="Lê Thị Publish",
            birth_year=1991,
            canonical_unit_id="u_pub",
            subject_group_hint="CAND",
            employment_status="ACTIVE",
            source_kind="PROVIDED",
            source_url="https://example.invalid/person-roster",
            source_authority="TEST AUTHORITY",
        )
    )
    assert person.qa_status == "PENDING_QA"
    rv = svc.decide_person_qa(person, PersonQADecision(decision="APPROVE"))
    assert rv is not None and rv.status == "DRAFT"
    assert db.get(
        PersonRegistrySnapshot,
        {"registry_version_id": rv.id, "person_id": person.id},
    ) is not None
    svc.validate_version(rv, "test validate")
    svc.approve_version(rv, "test approve")
    svc.publish_version(rv, "test publish")
    db.flush()
    resolved = PersonResolver(db).resolve(full_name="Lê Thị Publish")
    assert resolved.status == "MATCHED"
    assert resolved.person_id == person.id
    assert resolved.registry_version == rv.version


def test_person_approval_requires_active_approved_unit():
    from fastapi import HTTPException

    from cabqp.modules.person_resolution.registry_service import PersonRegistryService
    from cabqp.shared.schemas import PersonCreate, PersonQADecision

    db = db_session()
    src = Source(authority="TEST", url="https://example.invalid/unit-pending", source_kind="OFFICIAL")
    db.add(src)
    db.flush()
    unit = Unit(
        id="u_pending",
        canonical_name="Đơn vị chưa QA",
        normalized_key=normalize_text("Đơn vị chưa QA"),
        ascii_key=ascii_key("Đơn vị chưa QA"),
        organization_type="BCA",
        qa_status="PENDING_QA",
        active=True,
        source_id=src.id,
    )
    db.add(unit)
    db.flush()
    svc = PersonRegistryService(db, actor="admin-test")
    person = svc.create_person(
        PersonCreate(
            full_name="Người Chưa Duyệt Unit",
            canonical_unit_id="u_pending",
            employment_status="ACTIVE",
            source_kind="PROVIDED",
            source_url="https://example.invalid/person",
        )
    )
    try:
        svc.decide_person_qa(person, PersonQADecision(decision="APPROVE"))
        raise AssertionError("approval should have been blocked")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "active APPROVED unit" in str(exc.detail)


def test_matched_unknown_unit_still_requires_review():
    db = db_session()
    seed_unit(db, "u_unknown", "Đơn vị chưa phân loại", "UNKNOWN")
    seed_person(db, pid="p_unknown", name="Nguyễn Văn Unknown", unit_id="u_unknown")
    structured = {"text": "Nguyễn Văn Unknown", "subject_name": "Nguyễn Văn Unknown", "business_fields": {}}
    case = Case(created_by="tester", input_type="TEXT", raw_text="Nguyễn Văn Unknown", input_payload=structured)
    db.add(case)
    db.flush()
    result = process_case(db, case, structured)
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert result.resolution_status == "MATCHED"
    assert result.organization_type == "UNKNOWN"
    assert case.workflow_status == "NEED_REVIEW"
    assert review is not None and review.reason == "ORGANIZATION_TYPE_UNKNOWN"


def test_api_ambiguous_person_preserves_subject_and_never_claims_scope():
    from fastapi.testclient import TestClient

    from cabqp.main import app
    from cabqp.shared.db import get_db

    db = db_session()
    seed_unit(db, "u_a", "Đơn vị A", "BCA")
    seed_unit(db, "u_b", "Đơn vị B", "BQP")
    seed_person(db, pid="pa", name="Nguyễn Trùng Tên", unit_id="u_a")
    seed_person(db, pid="pb", name="Nguyễn Trùng Tên", unit_id="u_b")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/cases/text",
            json={"text": "Nguyễn Trùng Tên", "business_fields": {}},
        )
        assert created.status_code == 200, created.text
        body = client.get(f"/api/v1/cases/{created.json()['case_id']}").json()
        assert body["subject"]["name"] == "Nguyễn Trùng Tên"
        assert body["resolution_status"] == "AMBIGUOUS"
        assert body["organization_type"] == "UNKNOWN"
        assert body["in_scope"] is None
        assert body["workflow_status"] == "NEED_REVIEW"
        assert body["verification_status"] == "Cần xác minh"
        assert len(body["person"]["candidates"]) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_salary_status_uses_explicit_versioned_outcome_field_not_policy_name():
    from cabqp.api.cases import _salary_status
    from cabqp.shared.models import EligibilityAssessment, PolicyRule, VerificationResult

    db = db_session()
    case = Case(created_by="tester", input_type="TEXT", raw_text="x")
    db.add(case)
    db.flush()
    result = VerificationResult(
        case_id=case.id,
        organization_type="BCA",
        resolution_status="MATCHED",
        subject_group="CAND",
    )
    db.add(result)
    db.flush()
    insurance = PolicyRule(
        id="policy-insurance",
        policy_type="BHXH_SCOPE",
        subject_groups=["CAND"],
        required_fields=[],
        rule_expression={"scope_only": True},
        policy_version="v1",
        source_kind="OFFICIAL",
        source_ref="source",
        active=True,
    )
    salary = PolicyRule(
        id="policy-compensation-opaque-name",
        policy_type="BENEFIT_RULE",
        subject_groups=["CAND"],
        required_fields=[],
        rule_expression={"outcome_field": "salary_status"},
        policy_version="v2",
        source_kind="OFFICIAL",
        source_ref="source",
        active=True,
    )
    db.add_all([insurance, salary])
    db.flush()
    insurance_assessment = EligibilityAssessment(
        result_id=result.id,
        policy_id=insurance.id,
        status="ELIGIBLE",
        reason="insurance",
        evidence={},
        policy_version="v1",
        source_kind="OFFICIAL",
    )
    db.add(insurance_assessment)
    db.flush()
    assert _salary_status(db, [insurance_assessment]) == "Không đủ dữ liệu"

    salary_assessment = EligibilityAssessment(
        result_id=result.id,
        policy_id=salary.id,
        status="ELIGIBLE",
        reason="salary",
        evidence={},
        policy_version="v2",
        source_kind="OFFICIAL",
    )
    db.add(salary_assessment)
    db.flush()
    assert _salary_status(db, [insurance_assessment, salary_assessment]) == "Có"


def test_updating_approved_person_reopens_qa_instead_of_mutating_trusted_live_record():
    from cabqp.modules.person_resolution.registry_service import PersonRegistryService
    from cabqp.shared.schemas import PersonUpdate

    db = db_session()
    seed_unit(db, "u1", "Bệnh viện 19-8", "BCA")
    person = seed_person(db, pid="p1", name="Nguyễn Văn A", unit_id="u1")
    assert person.qa_status == "APPROVED"

    PersonRegistryService(db, actor="admin").update_person(
        person,
        PersonUpdate(full_name="Nguyễn Văn A cập nhật"),
    )
    db.flush()

    assert person.full_name == "Nguyễn Văn A cập nhật"
    assert person.normalized_key == normalize_text("Nguyễn Văn A cập nhật")
    assert person.qa_status == "PENDING_QA"
    # Live fallback only consumes APPROVED records, so the unreviewed edit is not resolvable.
    assert PersonResolver(db).resolve(full_name="Nguyễn Văn A cập nhật").status == "NOT_FOUND"
