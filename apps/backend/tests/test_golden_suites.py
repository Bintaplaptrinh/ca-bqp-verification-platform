from __future__ import annotations

from datetime import date
from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.cases.service import process_case
from cabqp.modules.decisioning.policy import PolicyEngine
from cabqp.modules.document_intelligence.extraction import extract
from cabqp.modules.document_intelligence.file_validation import validate_upload
from cabqp.modules.document_intelligence.parsers import parse_bytes
from cabqp.modules.document_intelligence.subject_split import detect_subject_blocks
from cabqp.modules.resolution.service import Resolver
from cabqp.shared.db import Base
from cabqp.shared.models import (
    Case,
    EligibilityAssessment,
    PolicyRule,
    ReviewCase,
    Source,
    Unit,
    UnitCode,
    UnitName,
    VerificationResult,
)
from cabqp.shared.normalization import normalize_text


def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_unit(
    db: Session,
    *,
    uid: str,
    name: str,
    org: str,
    code: str | None = None,
    alias: str | None = None,
    coverage: str = "TEST",
) -> Unit:
    src = Source(authority="GOLDEN", url=f"https://example.invalid/{uid}", source_kind="OFFICIAL")
    db.add(src)
    db.flush()
    unit = Unit(
        id=uid,
        canonical_name=name,
        normalized_key=normalize_text(name),
        organization_type=org,
        qa_status="APPROVED",
        active=True,
        source_id=src.id,
        coverage_group=coverage,
    )
    db.add(unit)
    db.flush()
    if code:
        db.add(UnitCode(unit_id=uid, code=code, namespace="DEFAULT", qa_status="APPROVED", source_id=src.id))
    if alias:
        db.add(UnitName(unit_id=uid, name=alias, normalized_key=normalize_text(alias), name_type="ALIAS", qa_status="APPROVED", source_id=src.id))
    db.flush()
    return unit


def seed_policy(db: Session) -> PolicyRule:
    rule = PolicyRule(
        id="GOLDEN-POLICY",
        policy_type="BHXH_SCOPE",
        subject_groups=["CAND"],
        required_fields=["employment_status"],
        rule_expression={"scope_only": True},
        effective_from=date(2025, 1, 1),
        policy_version="golden-v1",
        source_kind="OFFICIAL",
        source_ref="golden-policy-source",
        active=True,
    )
    db.add(rule)
    db.flush()
    return rule


def test_golden_clean_exact_code_and_canonical_name():
    """GOLDEN-CLEAN: trusted code/canonical exact must resolve deterministically."""
    db = db_session()
    seed_unit(db, uid="u_csgt", name="Cục Cảnh sát giao thông", org="BCA", code="C08")

    by_code = Resolver(db).resolve(unit_code="C08")
    assert by_code.status == "MATCHED"
    assert by_code.unit_id == "u_csgt"
    assert by_code.match_method == "TRUSTED_CODE"
    assert by_code.decision_confidence == 1.0

    by_name = Resolver(db).resolve(unit_name="Cục Cảnh sát giao thông")
    assert by_name.status == "MATCHED"
    assert by_name.match_method == "CANONICAL_EXACT"
    assert by_name.organization_type == "BCA"


def test_golden_noisy_approved_alias_and_format_noise():
    """GOLDEN-NOISY: human-approved alias survives case/space/punctuation normalization."""
    db = db_session()
    seed_unit(
        db,
        uid="u_108",
        name="Bệnh viện Trung ương Quân đội 108",
        org="BQP",
        alias="Bệnh viện 108",
    )
    out = Resolver(db).resolve(unit_name="  BỆNH-VIỆN   108  ")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_108"
    assert out.match_method == "APPROVED_ALIAS"


def test_golden_ocr_quality_gate_contract():
    """GOLDEN-OCR: image input is signature-validated then explicitly routed to OCR."""
    buf = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    content = buf.getvalue()
    safe_name, mime = validate_upload("scan.png", content, "image/png")
    assert safe_name == "scan.png"
    assert mime == "image/png"
    text, confidence, method = parse_bytes("scan.png", content)
    assert text == ""
    assert confidence == 0.0
    assert method == "OCR_REQUIRED"


def test_golden_context_current_unit_beats_former_unit():
    """GOLDEN-CONTEXT: CURRENT_WORK_UNIT must not be replaced by the first/historical ORG."""
    text = (
        "Đồng chí Nguyễn Văn A trước đây công tác tại Công an tỉnh A. "
        "Hiện công tác tại Cục Cảnh sát giao thông."
    )
    ex = extract(text, {})
    assert ex.current_unit == "Cục Cảnh sát giao thông"
    assert "Công an tỉnh A" in ex.former_units
    assert ex.relation_confidence >= 0.9


def test_golden_conflict_code_name_disagreement_abstains():
    """GOLDEN-CONFLICT: trusted code and exact name disagreement must produce CONFLICT."""
    db = db_session()
    seed_unit(db, uid="u_a", name="Cục Cảnh sát giao thông", org="BCA", code="C08")
    seed_unit(db, uid="u_b", name="Học viện Quốc phòng", org="BQP", code="BQP-HVQP")
    out = Resolver(db).resolve(unit_code="C08", unit_name="Học viện Quốc phòng")
    assert out.status == "CONFLICT"
    assert out.organization_type == "UNKNOWN"
    assert out.unit_id is None
    assert out.decision_confidence == 0.0


def test_golden_unknown_cold_start_never_maps_to_other():
    """GOLDEN-UNKNOWN: unseen unit must remain UNKNOWN/NEED_REVIEW, never OTHER by absence."""
    db = db_session()
    seed_unit(db, uid="u_known", name="Cục Cảnh sát giao thông", org="BCA")
    case = Case(created_by="golden", input_type="TEXT", raw_text="x", input_payload={"unit_name": "Đơn vị ZZZ hoàn toàn chưa có", "business_fields": {"subject_group": "CAND"}})
    db.add(case)
    db.flush()
    result = process_case(db, case, case.input_payload)
    assert result.organization_type == "UNKNOWN"
    assert result.resolution_status in {"NOT_FOUND", "AMBIGUOUS"}
    assert case.workflow_status == "NEED_REVIEW"
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert review is not None


def test_golden_policy_required_fields_and_effective_date():
    """GOLDEN-POLICY: missing required fields abstain; complete facts evaluate deterministically."""
    db = db_session()
    seed_policy(db)
    case = Case(created_by="golden", input_type="TEXT", raw_text="x")
    db.add(case)
    db.flush()
    result = VerificationResult(case_id=case.id, organization_type="BCA", resolution_status="MATCHED", subject_group="CAND")
    db.add(result)
    db.flush()

    PolicyEngine(db).evaluate(result_id=result.id, subject_group="CAND", facts={}, as_of=date(2026, 1, 1))
    db.flush()
    first = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert first.status == "INSUFFICIENT_DATA"

    PolicyEngine(db).evaluate(
        result_id=result.id,
        subject_group="CAND",
        facts={"employment_status": "ACTIVE"},
        as_of=date(2026, 1, 1),
    )
    db.flush()
    second = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert second.status == "ELIGIBLE"
    assert second.policy_version == "golden-v1"
    assert second.evidence["facts_used"]["employment_status"] == "ACTIVE"


def test_golden_e2e_case_result_evidence_policy_and_versions():
    """GOLDEN-E2E: request -> extraction -> resolution -> subject group -> policy -> final evidence."""
    db = db_session()
    seed_unit(db, uid="u_e2e", name="Cục Cảnh sát giao thông", org="BCA", coverage="BCA_CENTRAL_PUBLIC")
    seed_policy(db)
    structured = {
        "subject_name": "Nguyễn Văn A",
        "position": "Sĩ quan Công an",
        "unit_name": "Cục Cảnh sát giao thông",
        "business_fields": {"subject_group": "CAND", "employment_status": "ACTIVE"},
    }
    case = Case(
        created_by="golden",
        input_type="TEXT",
        raw_text="Đồng chí Nguyễn Văn A hiện công tác tại Cục Cảnh sát giao thông.",
        input_payload=structured,
    )
    db.add(case)
    db.flush()
    result = process_case(db, case, structured)
    db.flush()

    assert case.workflow_status == "COMPLETED"
    assert result.resolution_status == "MATCHED"
    assert result.organization_type == "BCA"
    assert result.subject_group == "CAND"
    assert result.source_kind == "OFFICIAL"
    assert result.parser_version
    assert result.taxonomy_version
    assert result.threshold_version
    assert result.evidence["match_method"] == "CANONICAL_EXACT"
    assessment = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.result_id == result.id))
    assert assessment is not None and assessment.status == "ELIGIBLE"


def test_golden_ocr_low_confidence_routes_to_human_review():
    """GOLDEN-OCR quality gate: low OCR confidence must not silently complete."""
    db = db_session()
    seed_unit(db, uid="u_ocr", name="Cục Cảnh sát giao thông", org="BCA")
    structured = {
        "unit_name": "Cục Cảnh sát giao thông",
        "business_fields": {"subject_group": "CAND", "employment_status": "ACTIVE"},
        "_parse_method": "PADDLE_OCR",
        "_parse_confidence": 0.35,
    }
    case = Case(created_by="golden", input_type="FILE", raw_text="sĩ quan công an", input_payload=structured)
    db.add(case)
    db.flush()
    result = process_case(db, case, structured)
    assert result.resolution_status == "MATCHED"
    assert case.workflow_status == "NEED_REVIEW"
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert review is not None
    assert review.reason == "DOCUMENT_PARSE_LOW_CONFIDENCE"
    assert result.evidence["parse_confidence"] == 0.35


def test_golden_conflict_same_name_under_two_organizations_abstains():
    """GOLDEN-CONFLICT: an exact name owned by BCA and BQP must not silently pick one.

    "Cục Hậu cần" genuinely exists under both ministries. Returning whichever row is
    scanned first would invent a force attribution from a name alone.
    """
    db = db_session()
    seed_unit(db, uid="u_bca_hc", name="Cục Hậu cần", org="BCA")
    seed_unit(db, uid="u_bqp_hc", name="Cục Hậu cần", org="BQP")

    out = Resolver(db).resolve(unit_name="Cục Hậu cần")
    assert out.status == "AMBIGUOUS"
    assert out.organization_type == "UNKNOWN"
    assert out.unit_id is None
    assert out.match_method == "EXACT_NAME_AMBIGUOUS"
    assert out.decision_confidence == 0.0
    assert {c["organization_type"] for c in out.candidates} == {"BCA", "BQP"}


def test_golden_conflict_trusted_code_disambiguates_shared_name():
    """A trusted code still resolves a name that several organizations share."""
    db = db_session()
    seed_unit(db, uid="u_bca_hc2", name="Cục Hậu cần", org="BCA")
    seed_unit(db, uid="u_bqp_hc2", name="Cục Hậu cần", org="BQP", code="BQP-HC")

    out = Resolver(db).resolve(unit_name="Cục Hậu cần", unit_code="BQP-HC")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_bqp_hc2"
    assert out.organization_type == "BQP"
    assert out.match_method == "TRUSTED_CODE"


def test_golden_clean_unique_exact_name_still_matches():
    """The ambiguity guard must not weaken the ordinary unique-name path."""
    db = db_session()
    seed_unit(db, uid="u_unique", name="Công an tỉnh An Giang", org="BCA")

    out = Resolver(db).resolve(unit_name="Công an tỉnh An Giang")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_unique"
    assert out.match_method == "CANONICAL_EXACT"
    assert out.decision_confidence == 1.0


def test_synthetic_source_kind_is_never_hidden():
    db = db_session()
    src = Source(authority="SYNTHETIC", url="synthetic://unit", source_kind="SYNTHETIC_DEMO")
    db.add(src)
    db.flush()
    unit = Unit(
        id="u_synth",
        canonical_name="Đơn vị mô phỏng",
        normalized_key=normalize_text("Đơn vị mô phỏng"),
        organization_type="BCA",
        qa_status="APPROVED",
        active=True,
        source_id=src.id,
    )
    db.add(unit)
    db.flush()
    out = Resolver(db).resolve(unit_name="Đơn vị mô phỏng")
    assert out.status == "MATCHED"
    assert out.source_kind == "SYNTHETIC_DEMO"


_MULTI_SUBJECT_TEXT = (
    "Họ và tên: Nguyễn Văn Một\n"
    "CCCD: 001082946111\n"
    "Chức vụ: Chuyên viên\n"
    "Đơn vị công tác: Cục Kỹ thuật\n"
    "\n"
    "Họ và tên: Trần Thị Hai\n"
    "CCCD: 001082946222\n"
    "Chức vụ: Trưởng phòng\n"
    "Đơn vị công tác: Cục Chính trị\n"
)


def test_golden_multi_subject_text_splits_into_two_blocks():
    """A free-text document with two 'Họ và tên' blocks must yield two independent blocks."""
    blocks = detect_subject_blocks(_MULTI_SUBJECT_TEXT, "PLAIN_TEXT")
    assert len(blocks) == 2
    assert all(not b.ambiguous for b in blocks)

    first = extract(blocks[0].text, {})
    second = extract(blocks[1].text, {})
    assert first.subject_name == "Nguyễn Văn Một"
    assert first.current_unit == "Cục Kỹ thuật"
    assert second.subject_name == "Trần Thị Hai"
    assert second.current_unit == "Cục Chính trị"


def test_golden_multi_subject_produces_two_independent_cases():
    """Each detected block must become its own Case with its own ExtractedRecord/VerificationResult."""
    db = db_session()
    seed_unit(db, uid="u_kt", name="Cục Kỹ thuật", org="BQP")
    seed_unit(db, uid="u_ct", name="Cục Chính trị", org="BQP")

    blocks = detect_subject_blocks(_MULTI_SUBJECT_TEXT, "PLAIN_TEXT")
    assert len(blocks) == 2

    results = []
    for block in blocks:
        case = Case(
            created_by="golden",
            input_type="FILE",
            raw_text=block.text,
            idempotency_key=f"doc_multi_subject:{block.index}",
        )
        db.add(case)
        db.flush()
        structured = {
            "_split_source": {
                "document_id": "doc_multi_subject",
                "block_index": block.index,
                "block_count": len(blocks),
            }
        }
        results.append((case, process_case(db, case, structured)))

    (case_a, result_a), (case_b, result_b) = results
    assert case_a.id != case_b.id
    assert result_a.id != result_b.id
    assert result_a.organization_type == "BQP"
    assert result_b.organization_type == "BQP"
    assert result_a.evidence["split_source"]["block_index"] == 0
    assert result_b.evidence["split_source"]["block_index"] == 1
    rec_a = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case_a.id))
    rec_b = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case_b.id))
    assert rec_a is not None and rec_b is not None and rec_a.id != rec_b.id


def test_golden_multi_subject_ocr_document_abstains_instead_of_guessing():
    """OCR/hybrid documents with multiple name labels must abstain to review, not auto-split."""
    blocks = detect_subject_blocks(_MULTI_SUBJECT_TEXT, "OCR")
    assert len(blocks) == 1
    assert blocks[0].ambiguous
    assert blocks[0].ambiguous_reason == "MULTIPLE_SUBJECTS_OCR_UNSUPPORTED"

    db = db_session()
    seed_unit(db, uid="u_kt2", name="Cục Kỹ thuật", org="BQP")
    structured = {
        "_batch_warnings": [
            {"code": blocks[0].ambiguous_reason, "column": None, "message_vi": ""}
        ],
    }
    case = Case(created_by="golden", input_type="FILE", raw_text=blocks[0].text, input_payload=structured)
    db.add(case)
    db.flush()
    process_case(db, case, structured)
    assert case.workflow_status == "NEED_REVIEW"
    review = db.scalar(select(ReviewCase).where(ReviewCase.case_id == case.id))
    assert review is not None
    assert review.reason == "MULTIPLE_SUBJECTS_OCR_UNSUPPORTED"
