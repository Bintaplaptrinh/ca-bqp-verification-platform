from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.decisioning.policy import PolicyEngine
from cabqp.modules.document_intelligence.extraction import extract
from cabqp.modules.person_resolution.service import PersonResolution, PersonResolver
from cabqp.modules.resolution.service import Resolution, Resolver
from cabqp.modules.subject_group.service import classify_subject_group
from cabqp.shared.metrics import CASE_TRANSITIONS, RESOLUTION_RESULTS, REVIEW_EVENTS
from cabqp.shared.models import Case, Document, ExtractedRecord, ReviewCase, VerificationResult
from cabqp.shared.settings import get_settings


def _source_document_id(db: Session, case: Case) -> str | None:
    """Identify which Document this extraction came from, when that is unambiguous.

    ``Document.case_id`` is not schema-unique, so a Case could in principle hold
    more than one. Trace it only when exactly one exists; guessing which of several
    produced a field would be evidence the platform cannot stand behind. Text cases
    have no document at all and keep ``None``.
    """
    document_ids = list(
        db.scalars(select(Document.id).where(Document.case_id == case.id).limit(2))
    )
    return document_ids[0] if len(document_ids) == 1 else None


def _upsert_extracted_record(db: Session, case: Case, ex, structured: dict) -> ExtractedRecord:
    rec = db.scalar(select(ExtractedRecord).where(ExtractedRecord.case_id == case.id).limit(1))
    if rec is None:
        rec = ExtractedRecord(case_id=case.id)
        db.add(rec)
    # Document -> Extraction traceability. The column and the API projection both
    # existed but nothing ever wrote it, so every record reported a null source.
    rec.document_id = _source_document_id(db, case) or rec.document_id
    rec.subject_name = ex.subject_name
    rec.subject_code = ex.subject_code
    rec.position = ex.position
    rec.current_unit_raw = ex.current_unit
    rec.former_units = ex.former_units
    rec.extracted_fields = ex.fields | {"structured": structured}
    rec.extraction_confidence = ex.extraction_confidence
    rec.relation_confidence = ex.relation_confidence
    db.flush()
    return rec


def _upsert_result(db: Session, case: Case) -> VerificationResult:
    result = db.scalar(select(VerificationResult).where(VerificationResult.case_id == case.id))
    if result is None:
        result = VerificationResult(case_id=case.id, resolution_status="NOT_FOUND")
        db.add(result)
        db.flush()
    return result


def _review_scope(resolution) -> str | None:
    if resolution.coverage_group:
        return resolution.coverage_group
    groups = {
        x.get("coverage_group")
        for x in (resolution.candidates or [])[:5]
        if x.get("coverage_group")
    }
    return next(iter(groups)) if len(groups) == 1 else "UNASSIGNED"


def _person_resolution_evidence(person: PersonResolution | None) -> dict | None:
    if person is None:
        return None
    return {
        "status": person.status,
        "person_id": person.person_id,
        "full_name": person.full_name,
        "canonical_unit_id": person.canonical_unit_id,
        "canonical_unit_name": person.canonical_unit_name,
        "birth_year": person.birth_year,
        "employment_status": person.employment_status,
        "subject_group_hint": person.subject_group_hint,
        "match_method": person.match_method,
        "score": person.score,
        "margin": person.margin,
        "candidates": person.candidates,
        "registry_version": person.registry_version,
        "source_kind": person.source_kind,
        "decision_confidence": person.decision_confidence,
        "synthetic_welfare_facts": person.synthetic_welfare_facts,
    }


def _person_candidates_with_review_scope(db: Session, candidates: list[dict]) -> list[dict]:
    """Enrich person candidates using the authoritative unit Resolver.

    PersonResolver remains identity-only. Organization type and review scope are
    projected here from the current unit registry version, so candidate evidence
    cannot drift into becoming a second organization authority.
    """
    resolved_units: dict[str, Resolution] = {}
    for candidate in candidates:
        unit_id = candidate.get("canonical_unit_id")
        if unit_id and str(unit_id) not in resolved_units:
            resolved_units[str(unit_id)] = Resolver(db).resolve(unit_id=str(unit_id))
    enriched: list[dict] = []
    for candidate in candidates:
        unit_id = str(candidate.get("canonical_unit_id") or "")
        unit_resolution = resolved_units.get(unit_id)
        enriched.append(
            {
                **candidate,
                "canonical_unit_name": (
                    unit_resolution.canonical_name
                    if unit_resolution and unit_resolution.status == "MATCHED"
                    else candidate.get("canonical_unit_name")
                ),
                "organization_type": (
                    unit_resolution.organization_type
                    if unit_resolution and unit_resolution.status == "MATCHED"
                    else "UNKNOWN"
                ),
                "coverage_group": (
                    unit_resolution.coverage_group
                    if unit_resolution and unit_resolution.status == "MATCHED"
                    else None
                ),
            }
        )
    return enriched


def process_case(db: Session, case: Case, structured: dict | None = None):
    s = get_settings()
    structured = structured if structured is not None else (case.input_payload or {})
    case.input_payload = structured
    case.workflow_status = "PROCESSING"

    ex = extract(case.raw_text or "", structured)
    _upsert_extracted_record(db, case, ex, structured)

    raw_as_of = structured.get("as_of_date")
    as_of = case.created_at.date() if case.created_at else date.today()
    if isinstance(raw_as_of, date):
        as_of = raw_as_of
    elif isinstance(raw_as_of, str) and raw_as_of:
        try:
            as_of = date.fromisoformat(raw_as_of)
        except ValueError:
            # Invalid user-provided dates must not silently change policy semantics;
            # fall back to immutable Case creation date for deterministic replay.
            as_of = case.created_at.date() if case.created_at else date.today()

    business_fields = dict(structured.get("business_fields") or {})
    unit_code = structured.get("unit_code") or ex.unit_code
    person_resolution: PersonResolution | None = None
    person_lookup = bool((ex.subject_name or ex.subject_code) and not ex.current_unit and not unit_code)
    # A unit code is the same fact CURRENT_WORK_UNIT carries, expressed as an
    # identifier instead of a name. The document therefore has no free-text unit
    # relation to score, exactly as a bare-name lookup has none, and the generic
    # four-field completeness score must not penalize the missing `current_unit`.
    # Whether the code actually resolves stays a separate gate below (`r.status`),
    # so this never turns an unresolvable code into a decision.
    unit_code_lookup = bool(unit_code and not ex.current_unit)
    # Both shapes supply identity/unit evidence directly rather than through a
    # narrative relation, and share the same confidence treatment.
    relationless_lookup = person_lookup or unit_code_lookup
    if person_lookup:
        raw_birth_year = business_fields.get("birth_year")
        try:
            birth_year = int(raw_birth_year) if raw_birth_year not in (None, "") else None
        except (TypeError, ValueError):
            birth_year = None
        person_resolution = PersonResolver(db).resolve(
            full_name=ex.subject_name,
            personal_code=ex.subject_code,
            birth_year=birth_year,
            as_of_date=as_of,
        )
        if person_resolution.status == "MATCHED" and person_resolution.canonical_unit_id:
            r = Resolver(db).resolve(
                unit_id=person_resolution.canonical_unit_id,
                as_of_date=as_of,
            )
        else:
            person_candidates = _person_candidates_with_review_scope(
                db, person_resolution.candidates
            )
            r = Resolution(
                status=person_resolution.status,
                organization_type="UNKNOWN",
                unit_id=None,
                canonical_name=None,
                match_method=person_resolution.match_method,
                score=person_resolution.score,
                margin=person_resolution.margin,
                candidates=person_candidates,
                registry_version=None,
                source_kind=person_resolution.source_kind,
                calibration_status="NOT_REQUIRED",
                decision_confidence=0.0,
                coverage_group=None,
            )
    else:
        r = Resolver(db).resolve(
            unit_name=ex.current_unit,
            unit_code=unit_code,
            as_of_date=as_of,
        )
    person_evidence = _person_resolution_evidence(person_resolution)
    if person_evidence is not None and person_resolution and person_resolution.status != "MATCHED":
        # Candidate unit/org fields are enriched in the case layer through Unit Resolver;
        # preserve that authoritative projection in every downstream evidence surface.
        person_evidence["candidates"] = r.candidates
    # Preserve an explicitly labelled group from documents. Classification still
    # validates it against KNOWN_GROUPS and abstains for broad/invalid values such
    # as "BQP"; this is direct document evidence, not inference from unit membership.
    labelled_group = (ex.fields.get("labelled_fields") or {}).get("subject_group")
    if labelled_group and not business_fields.get("subject_group"):
        business_fields["subject_group"] = labelled_group
    if (
        person_resolution
        and person_resolution.subject_group_hint
        and not business_fields.get("subject_group")
    ):
        # Roster group is a hint only. classify_subject_group still validates it against
        # KNOWN_GROUPS, so an unknown hint cannot become a business conclusion.
        business_fields["subject_group"] = person_resolution.subject_group_hint
    parse_confidence = structured.get("_parse_confidence")
    parse_method = structured.get("_parse_method")
    parse_quality = structured.get("_parse_quality") or {}
    parse_evidence = structured.get("_parse_evidence") or {}
    try:
        parse_confidence = float(parse_confidence) if parse_confidence is not None else None
    except (TypeError, ValueError):
        parse_confidence = None
    gate_failed = str(parse_quality.get("gate_result", "")).upper() == "FAIL"
    is_ocr = parse_method in {"OCR", "PADDLE_OCR", "PDF_HYBRID"}
    parse_quality_low = bool(
        gate_failed
        or (parse_confidence is not None and parse_confidence < (s.ocr_min_confidence if is_ocr else s.document_parse_min_confidence))
    )
    sg, sg_conf, sg_method = classify_subject_group(
        organization_type=r.organization_type,
        position=ex.position,
        text=case.raw_text or "",
        fields=business_fields,
    )

    resolution_conf = r.decision_confidence if r.decision_confidence is not None else 0.0
    field_confidence = ex.fields.get("field_confidence") or {}
    # Extraction completeness is workflow-specific. A deliberate bare-name or unit-code
    # lookup does not claim to provide position/current-unit, so the generic four-field
    # document completeness score must not penalize it. The identity field actually
    # supplied is the extraction gate for these audited lookup paths.
    if relationless_lookup:
        identity_scores = [
            float(field_confidence[key])
            for key in ("subject_name", "subject_code")
            if field_confidence.get(key) is not None
        ]
        decision_extraction_confidence = min(identity_scores) if identity_scores else 0.0
    else:
        decision_extraction_confidence = ex.extraction_confidence
    confidence_inputs: list[float | None] = [decision_extraction_confidence, resolution_conf]
    # A bare-name lookup takes its unit from the resolved roster FK, and a unit-code
    # lookup states the unit outright. Neither has a CURRENT_WORK_UNIT relation in the
    # input, so do not punish these valid paths with relation_confidence=0.
    if not relationless_lookup:
        confidence_inputs.append(ex.relation_confidence)
    if person_resolution is not None:
        confidence_inputs.append(person_resolution.decision_confidence)
    decision_conf = min(
        [x for x in confidence_inputs if x is not None],
        default=0.0,
    )

    result = _upsert_result(db, case)
    result.unit_id = r.unit_id
    result.organization_type = r.organization_type
    result.resolution_status = r.status
    result.subject_group = sg
    result.match_method = r.match_method
    result.resolution_score = r.score
    result.candidate_margin = r.margin
    result.decision_confidence = decision_conf
    result.top_candidates = r.candidates
    result.registry_version = r.registry_version
    result.source_kind = (
        person_resolution.source_kind
        if person_resolution is not None
        else r.source_kind
    )
    result.taxonomy_version = s.taxonomy_version
    result.parser_version = s.parser_version
    result.model_version = s.model_version
    result.threshold_version = s.threshold_version
    RESOLUTION_RESULTS.labels(
        status=r.status,
        method=r.match_method or "NONE",
        organization_type=r.organization_type,
    ).inc()
    result.evidence = {
        "current_unit_raw": ex.current_unit,
        "canonical_name": r.canonical_name,
        "former_units": ex.former_units,
        "person_resolution": person_evidence,
        "person_registry_version": person_resolution.registry_version if person_resolution else None,
        "subject_group_method": sg_method,
        "subject_group_confidence": sg_conf,
        "extraction_confidence": ex.extraction_confidence,
        "decision_extraction_confidence": decision_extraction_confidence,
        "relation_confidence": ex.relation_confidence,
        "resolution_score": r.score,
        "candidate_margin": r.margin,
        "resolution_confidence": r.decision_confidence,
        "match_method": r.match_method,
        "calibration_status": r.calibration_status,
        "registry_version": r.registry_version,
        "taxonomy_version": s.taxonomy_version,
        "parser_version": s.parser_version,
        "model_version": s.model_version,
        "threshold_version": s.threshold_version,
        "source_kind": result.source_kind,
        "unit_source_kind": r.source_kind,
        "parse_method": parse_method,
        "parse_confidence": parse_confidence,
        "parse_quality": parse_quality,
        "parse_evidence": parse_evidence,
        "bulk_source": structured.get("_bulk_source"),
        "split_source": structured.get("_split_source"),
        # Present when an operator corrected an earlier Case's extracted fields
        # and re-ran it: says which fields a human overrode, and from what.
        "operator_correction": structured.get("_operator_correction"),
        "as_of_date": as_of.isoformat() if as_of else None,
    }
    db.flush()

    batch_warnings = structured.get("_batch_warnings") or []
    extraction_quality_low = decision_extraction_confidence < s.extraction_min_confidence
    upstream_needs_review = (
        r.status != "MATCHED"
        or r.organization_type == "UNKNOWN"
        or (person_resolution is not None and person_resolution.status != "MATCHED")
        or extraction_quality_low
        or (not relationless_lookup and ex.relation_confidence < 0.7)
        or sg is None
        or parse_quality_low
        or bool(batch_warnings)
    )

    # Policy is part of the business decision, not a post-processing decoration.
    # Evaluate it only after upstream identity/unit/group evidence is strong enough;
    # if an applicable rule lacks required facts, the Case must abstain to review.
    facts = {
        **business_fields,
        "organization_type": r.organization_type,
        "subject_group": sg,
        "position": ex.position,
        "subject_code": ex.subject_code,
    }
    policy_assessments = []
    if not upstream_needs_review:
        policy_assessments = PolicyEngine(db).evaluate(
            result_id=result.id,
            subject_group=sg,
            facts=facts,
            as_of=as_of,
        )
    policy_insufficient = any(a.status == "INSUFFICIENT_DATA" for a in policy_assessments)
    result.evidence = {
        **(result.evidence or {}),
        "policy_summary": [
            {
                "policy_id": a.policy_id,
                "status": a.status,
                "policy_version": a.policy_version,
                "reason": a.reason,
            }
            for a in policy_assessments
        ],
        "policy_as_of_date": as_of.isoformat() if as_of else None,
    }

    needs_review = upstream_needs_review or policy_insufficient
    existing_review = db.scalar(
        select(ReviewCase)
        .where(ReviewCase.case_id == case.id, ReviewCase.status == "OPEN")
        .limit(1)
    )

    if needs_review:
        # Explicit batch warnings are operator-facing data-quality facts and should
        # not be hidden by a downstream generic AMBIGUOUS/NOT_FOUND label.
        if batch_warnings:
            reason = str(batch_warnings[0].get("code") or "BATCH_WARNING")
        elif person_resolution is not None and person_resolution.status != "MATCHED":
            reason = f"PERSON_{person_resolution.status}"
        elif r.status != "MATCHED":
            reason = r.status
        elif r.organization_type == "UNKNOWN":
            reason = "ORGANIZATION_TYPE_UNKNOWN"
        elif parse_quality_low:
            reason = "DOCUMENT_PARSE_LOW_CONFIDENCE"
        elif extraction_quality_low:
            reason = "DOCUMENT_EXTRACTION_LOW_CONFIDENCE"
        elif not relationless_lookup and ex.relation_confidence < 0.7:
            # Must stay the same predicate as the gate above: reporting an uncertain
            # work unit for a Case that was never routed to review on that ground
            # points the reviewer at the wrong fact.
            reason = "CURRENT_WORK_UNIT_UNCERTAIN"
        elif sg is None:
            reason = "SUBJECT_GROUP_INSUFFICIENT"
        else:
            reason = "POLICY_INSUFFICIENT_DATA"
        payload = {
            # Identity of the person under review. Without it a reviewer opening the
            # queue sees only a Case id and has to fetch the Case separately to learn
            # who the review is even about.
            "subject": {
                "name": ex.subject_name,
                "subject_code": ex.subject_code,
                "position": ex.position,
                "birth_year": business_fields.get("birth_year"),
            },
            "resolution": {
                "status": r.status,
                "organization_type": r.organization_type,
                "unit_id": r.unit_id,
                "canonical_name": r.canonical_name,
                "match_method": r.match_method,
                "score": r.score,
                "margin": r.margin,
                "registry_version": r.registry_version,
            },
            "confidence": {
                "decision": decision_conf,
                "resolution": r.decision_confidence,
                "extraction": decision_extraction_confidence,
                "relation": ex.relation_confidence,
                "subject_group": sg_conf,
            },
            # The gate each confidence above was compared against, so a reviewer can
            # see how far short the Case fell rather than just that it fell short.
            "thresholds": {
                "extraction_min": s.extraction_min_confidence,
                "parse_min": s.ocr_min_confidence if is_ocr else s.document_parse_min_confidence,
                "threshold_version": s.threshold_version,
            },
            "case": {
                "created_by": case.created_by,
                "input_type": case.input_type,
                "created_at": case.created_at.isoformat() if case.created_at else None,
            },
            "top_candidates": r.candidates,
            "person_resolution": person_evidence,
            "current_unit_raw": ex.current_unit,
            "former_units": ex.former_units,
            "business_fields": business_fields,
            "subject_group": sg,
            "subject_group_method": sg_method,
            "parse_method": parse_method,
            "parse_confidence": parse_confidence,
            "parse_quality": parse_quality,
            "extraction_confidence": ex.extraction_confidence,
            "field_confidence": ex.fields.get("field_confidence") or {},
            "field_evidence": ex.fields.get("field_evidence") or {},
            "bulk_source": structured.get("_bulk_source"),
            "split_source": structured.get("_split_source"),
            # `reason` keeps only the first warning's code; the reviewer needs the
            # rest, and the Vietnamese message that came with each one.
            "batch_warnings": batch_warnings,
            "policy_assessments": [
                {
                    "policy_id": a.policy_id,
                    "status": a.status,
                    "policy_version": a.policy_version,
                    "reason": a.reason,
                    "evidence": a.evidence,
                }
                for a in policy_assessments
            ],
            "as_of_date": as_of.isoformat() if as_of else None,
        }
        scope = _review_scope(r)
        if existing_review is None:
            db.add(
                ReviewCase(
                    case_id=case.id,
                    result_id=result.id,
                    reason=reason,
                    payload=payload,
                    coverage_group=scope,
                )
            )
        else:
            existing_review.result_id = result.id
            existing_review.reason = reason
            existing_review.payload = payload
            existing_review.coverage_group = scope
            existing_review.version_no += 1
        case.workflow_status = "NEED_REVIEW"
        CASE_TRANSITIONS.labels(status="NEED_REVIEW").inc()
        REVIEW_EVENTS.labels(event="CREATED_OR_UPDATED", reason=reason).inc()
    else:
        if existing_review is not None:
            existing_review.status = "DISMISSED"
            existing_review.decision_note = "Case reprocessed successfully; review no longer required."
            existing_review.version_no += 1
        # Policy was already evaluated above with the Case's business effective date.
        case.workflow_status = "COMPLETED"
        CASE_TRANSITIONS.labels(status="COMPLETED").inc()

    audit(
        db,
        actor="system:case-processor",
        role="SYSTEM",
        action="CASE_DECISION",
        entity_type="CASE",
        entity_id=case.id,
        metadata={
            "result_id": result.id,
            "workflow_status": case.workflow_status,
            "resolution_status": result.resolution_status,
            "organization_type": result.organization_type,
            "subject_group": result.subject_group,
            "registry_version": result.registry_version,
            "person_registry_version": person_resolution.registry_version if person_resolution else None,
            "taxonomy_version": result.taxonomy_version,
            "parser_version": result.parser_version,
            "model_version": result.model_version,
            "threshold_version": result.threshold_version,
            "policy_as_of_date": result.evidence.get("policy_as_of_date"),
            "review_required": needs_review,
        },
    )
    return result
