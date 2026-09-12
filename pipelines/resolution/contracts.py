"""Data contracts for the unit resolution module, exact match stage.

This module defines the only types that cross the boundary between the
resolution engine and its callers. The system team builds the database,
backend and frontend against these types.

All values are plain data. Nothing here imports a web framework, an ORM or a
database driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any


class ResolutionStatus(StrEnum):
    """Outcome of the unit resolution step."""

    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"


class OrganizationType(StrEnum):
    """Management scope of a unit."""

    BCA = "BCA"
    BQP = "BQP"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class MatchMethod(StrEnum):
    """How the winning candidate was found."""

    CODE_EXACT = "CODE_EXACT"
    CODE_ALIAS_EXACT = "CODE_ALIAS_EXACT"
    CANONICAL_EXACT = "CANONICAL_EXACT"
    ALIAS_EXACT = "ALIAS_EXACT"
    NONE = "NONE"


class NormalizationLevel(StrEnum):
    """Which deterministic normalization produced the match.

    STRICT: whitespace collapse plus case folding only.
    ASCII_FOLDED: STRICT plus Unicode diacritic folding and d-stroke folding.
    Both levels are exact string equality, not fuzzy matching.
    """

    STRICT = "STRICT"
    ASCII_FOLDED = "ASCII_FOLDED"


class ReviewReason(StrEnum):
    """Why a result must be routed to human review."""

    CODE_NAME_CONFLICT = "CODE_NAME_CONFLICT"
    AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
    UNRESOLVED_CODE = "UNRESOLVED_CODE"
    NAME_NOT_IN_REGISTRY = "NAME_NOT_IN_REGISTRY"
    OUT_OF_VALIDITY_WINDOW = "OUT_OF_VALIDITY_WINDOW"
    REGISTRY_DATA_DEFECT = "REGISTRY_DATA_DEFECT"


class ValidityNote(StrEnum):
    """Why a candidate is not usable at the requested date."""

    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    INVALID_WINDOW = "INVALID_WINDOW"


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class UnitRecord:
    """One canonical unit as published by a registry snapshot."""

    unit_id: int
    unit_code: str | None
    canonical_name: str
    organization_type: OrganizationType
    unit_level: str
    valid_from: date
    valid_to: date | None
    registry_version: str
    qa_confidence: str

    def validity_note(self, as_of: date) -> ValidityNote | None:
        """Return None when the unit is usable at as_of, otherwise the reason."""
        if self.valid_to is not None and self.valid_to < self.valid_from:
            return ValidityNote.INVALID_WINDOW
        if as_of < self.valid_from:
            return ValidityNote.OUT_OF_WINDOW
        if self.valid_to is not None and as_of > self.valid_to:
            return ValidityNote.OUT_OF_WINDOW
        return None

    def is_valid_at(self, as_of: date) -> bool:
        return self.validity_note(as_of) is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_code": self.unit_code,
            "canonical_name": self.canonical_name,
            "organization_type": str(self.organization_type),
            "unit_level": self.unit_level,
            "valid_from": _iso(self.valid_from),
            "valid_to": _iso(self.valid_to),
            "registry_version": self.registry_version,
            "qa_confidence": self.qa_confidence,
        }


@dataclass(frozen=True)
class Candidate:
    """A registry entry that matched the input, valid or not."""

    unit: UnitRecord
    matched_value: str
    matched_field: str
    normalization_level: NormalizationLevel
    is_valid_at: bool
    validity_note: ValidityNote | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit.unit_id,
            "unit_code": self.unit.unit_code,
            "canonical_name": self.unit.canonical_name,
            "organization_type": str(self.unit.organization_type),
            "matched_value": self.matched_value,
            "matched_field": self.matched_field,
            "normalization_level": str(self.normalization_level),
            "is_valid_at": self.is_valid_at,
            "validity_note": str(self.validity_note) if self.validity_note else None,
            "valid_from": _iso(self.unit.valid_from),
            "valid_to": _iso(self.unit.valid_to),
        }


@dataclass(frozen=True)
class ResolutionInput:
    """Structured input of one resolution request.

    The caller supplies already separated fields. Extracting these fields from
    free text or from a document is the job of the document intelligence stage
    and is out of scope for this module.
    """

    current_unit_text: str | None = None
    unit_code_text: str | None = None
    as_of_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_unit_text": self.current_unit_text,
            "unit_code_text": self.unit_code_text,
            "as_of_date": _iso(self.as_of_date),
        }


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of one resolution request, always with evidence."""

    resolution_status: ResolutionStatus
    organization_type: OrganizationType
    matched_unit: UnitRecord | None
    match_method: MatchMethod
    requires_review: bool
    review_reason: ReviewReason | None
    registry_version: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_status": str(self.resolution_status),
            "organization_type": str(self.organization_type),
            "matched_unit": self.matched_unit.to_dict() if self.matched_unit else None,
            "match_method": str(self.match_method),
            "requires_review": self.requires_review,
            "review_reason": str(self.review_reason) if self.review_reason else None,
            "registry_version": self.registry_version,
            "evidence": self.evidence,
        }
