"""Exact match unit resolution.

Cascade, in priority order:

1. unit code exact match against the registry code index
2. unit code text matched as an approved alias, only when step 1 found nothing
3. canonical name exact match
4. approved alias exact match

Every step is exact string equality after deterministic normalization. Fuzzy
matching, ranking, scoring and calibration belong to the next milestone and are
deliberately absent here.

Business rules enforced, from the project plan:

- an exact code match is the strongest evidence and is never overridden by a
  name match, but a name that points to a different unit produces CONFLICT
- a name or alias match is accepted only when the registry entry is approved
  and valid at the requested date
- a unit outside its validity window is never returned as MATCHED
- NOT_FOUND never becomes OTHER; organization_type is UNKNOWN unless MATCHED
- every outcome, including NOT_FOUND and CONFLICT, carries full evidence and is
  returned as a value, not raised as an exception
"""

from __future__ import annotations

from datetime import date

from pipelines.resolution.contracts import (
    Candidate,
    MatchMethod,
    OrganizationType,
    ResolutionInput,
    ResolutionResult,
    ResolutionStatus,
    ReviewReason,
    UnitRecord,
    ValidityNote,
)
from pipelines.resolution.registry_lookup import CANONICAL_FIELD, UnitRegistryLookup
from pipelines.resolution.text_normalize import (
    fold_ascii,
    is_blank,
    normalize_code,
    normalize_name,
)

MAX_EVIDENCE_CANDIDATES = 10


class EmptyResolutionInputError(ValueError):
    """Raised when neither a unit name nor a unit code is supplied."""


def resolve(request: ResolutionInput, lookup: UnitRegistryLookup) -> ResolutionResult:
    """Resolve one structured request against a registry snapshot."""
    if is_blank(request.current_unit_text) and is_blank(request.unit_code_text):
        raise EmptyResolutionInputError(
            "current_unit_text or unit_code_text must be supplied"
        )

    as_of = request.as_of_date or date.today()
    name_text = request.current_unit_text
    code_text = request.unit_code_text

    code_candidates = [] if is_blank(code_text) else lookup.find_by_code(code_text, as_of)
    code_alias_candidates: list[Candidate] = []
    if not is_blank(code_text) and not code_candidates:
        code_alias_candidates = lookup.find_by_name(code_text, as_of)
    name_candidates = [] if is_blank(name_text) else lookup.find_by_name(name_text, as_of)

    valid_code = _valid(code_candidates)
    valid_code_alias = _valid(code_alias_candidates)
    valid_name = _valid(name_candidates)

    if valid_code:
        code_side, code_method = valid_code, MatchMethod.CODE_EXACT
    else:
        code_side, code_method = valid_code_alias, MatchMethod.CODE_ALIAS_EXACT

    code_units = _unit_ids(code_side)
    name_units = _unit_ids(valid_name)

    status = ResolutionStatus.NOT_FOUND
    method = MatchMethod.NONE
    matched: UnitRecord | None = None
    review_reason: ReviewReason | None = None
    decision_note: str | None = None

    if code_units and name_units:
        shared = code_units & name_units
        if len(shared) == 1:
            unit_id = next(iter(shared))
            status = ResolutionStatus.MATCHED
            matched = _unit_by_id(code_side + valid_name, unit_id)
            method = code_method
            if len(name_units) > 1 or len(code_units) > 1:
                decision_note = "code and name intersection narrowed to a single unit"
        elif not shared:
            status = ResolutionStatus.CONFLICT
            review_reason = ReviewReason.CODE_NAME_CONFLICT
            decision_note = "code and name resolve to different units"
        else:
            status = ResolutionStatus.AMBIGUOUS
            review_reason = ReviewReason.AMBIGUOUS_CANDIDATES
            decision_note = "code and name share more than one candidate unit"
    elif code_units:
        if len(code_units) == 1:
            status = ResolutionStatus.MATCHED
            matched = code_side[0].unit
            method = code_method
            if not is_blank(name_text):
                review_reason = ReviewReason.NAME_NOT_IN_REGISTRY
                decision_note = "code matched but the supplied name is not in the registry"
        else:
            status = ResolutionStatus.AMBIGUOUS
            review_reason = ReviewReason.AMBIGUOUS_CANDIDATES
            decision_note = "code matches more than one unit valid at the requested date"
    elif name_units:
        if len(name_units) == 1:
            status = ResolutionStatus.MATCHED
            matched = valid_name[0].unit
            method = _name_match_method(valid_name)
            if not is_blank(code_text):
                review_reason = ReviewReason.UNRESOLVED_CODE
                decision_note = "name matched but the supplied code is not in the registry"
        else:
            status = ResolutionStatus.AMBIGUOUS
            review_reason = ReviewReason.AMBIGUOUS_CANDIDATES
            decision_note = "name matches more than one unit valid at the requested date"
    else:
        status = ResolutionStatus.NOT_FOUND
        review_reason, decision_note = _not_found_reason(
            code_candidates + code_alias_candidates + name_candidates,
            has_code_text=not is_blank(code_text),
        )

    requires_review = status is not ResolutionStatus.MATCHED or review_reason is not None
    organization_type = (
        matched.organization_type if status is ResolutionStatus.MATCHED and matched else OrganizationType.UNKNOWN
    )

    evidence = _build_evidence(
        request=request,
        as_of=as_of,
        registry_version=lookup.registry_version(),
        code_candidates=code_candidates,
        code_alias_candidates=code_alias_candidates,
        name_candidates=name_candidates,
        status=status,
        method=method,
        matched=matched,
        requires_review=requires_review,
        review_reason=review_reason,
        decision_note=decision_note,
    )

    return ResolutionResult(
        resolution_status=status,
        organization_type=organization_type,
        matched_unit=matched,
        match_method=method,
        requires_review=requires_review,
        review_reason=review_reason,
        registry_version=lookup.registry_version(),
        evidence=evidence,
    )


def _valid(candidates: list[Candidate]) -> list[Candidate]:
    return [candidate for candidate in candidates if candidate.is_valid_at]


def _unit_ids(candidates: list[Candidate]) -> set[int]:
    return {candidate.unit.unit_id for candidate in candidates}


def _unit_by_id(candidates: list[Candidate], unit_id: int) -> UnitRecord | None:
    for candidate in candidates:
        if candidate.unit.unit_id == unit_id:
            return candidate.unit
    return None


def _name_match_method(candidates: list[Candidate]) -> MatchMethod:
    if any(candidate.matched_field == CANONICAL_FIELD for candidate in candidates):
        return MatchMethod.CANONICAL_EXACT
    return MatchMethod.ALIAS_EXACT


def _not_found_reason(
    candidates: list[Candidate], has_code_text: bool
) -> tuple[ReviewReason, str | None]:
    if any(candidate.validity_note is ValidityNote.INVALID_WINDOW for candidate in candidates):
        return (
            ReviewReason.REGISTRY_DATA_DEFECT,
            "the only candidates carry an invalid validity window in the registry",
        )
    if candidates:
        return (
            ReviewReason.OUT_OF_VALIDITY_WINDOW,
            "candidates exist but none is valid at the requested date",
        )
    if has_code_text:
        return ReviewReason.UNRESOLVED_CODE, "the supplied code is not in the registry"
    return ReviewReason.NAME_NOT_IN_REGISTRY, "the supplied name is not in the registry"


def _build_evidence(
    request: ResolutionInput,
    as_of: date,
    registry_version: str,
    code_candidates: list[Candidate],
    code_alias_candidates: list[Candidate],
    name_candidates: list[Candidate],
    status: ResolutionStatus,
    method: MatchMethod,
    matched: UnitRecord | None,
    requires_review: bool,
    review_reason: ReviewReason | None,
    decision_note: str | None,
) -> dict:
    return {
        "input": request.to_dict(),
        "as_of_date": as_of.isoformat(),
        "registry_version": registry_version,
        "normalization": {
            "name_strict": None if is_blank(request.current_unit_text) else normalize_name(request.current_unit_text),
            "name_ascii_folded": None if is_blank(request.current_unit_text) else fold_ascii(request.current_unit_text),
            "code": None if is_blank(request.unit_code_text) else normalize_code(request.unit_code_text),
        },
        "candidates": {
            "by_code": _serialize(code_candidates),
            "by_code_as_alias": _serialize(code_alias_candidates),
            "by_name": _serialize(name_candidates),
        },
        "candidate_counts": {
            "by_code": len(code_candidates),
            "by_code_as_alias": len(code_alias_candidates),
            "by_name": len(name_candidates),
        },
        "decision": {
            "resolution_status": str(status),
            "match_method": str(method),
            "matched_unit_id": matched.unit_id if matched else None,
            "requires_review": requires_review,
            "review_reason": str(review_reason) if review_reason else None,
            "note": decision_note,
        },
    }


def _serialize(candidates: list[Candidate]) -> list[dict]:
    return [candidate.to_dict() for candidate in candidates[:MAX_EVIDENCE_CANDIDATES]]
