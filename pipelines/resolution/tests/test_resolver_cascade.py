"""Branch by branch tests of the exact match cascade, with a fake registry."""

from __future__ import annotations

import json
from datetime import date

import pytest
from conftest import FakeRegistryLookup, make_unit

from pipelines.resolution.contracts import (
    MatchMethod,
    OrganizationType,
    ResolutionInput,
    ResolutionStatus,
    ReviewReason,
)
from pipelines.resolution.resolver import EmptyResolutionInputError, resolve

AS_OF = date(2026, 1, 1)

TRAFFIC = make_unit(1, "BCA_C08", "Cuc Canh sat giao thong", "BCA")
CYBER = make_unit(2, "BCA_A05", "Cuc An ninh mang", "BCA")
HOSPITAL = make_unit(3, "BQP_BV108", "Benh vien Trung uong Quan doi 108", "BQP")
CLOSED = make_unit(4, "BQP_QD1", "Quan doan 1", "BQP", valid_to=date(2023, 12, 31))
BROKEN = make_unit(
    5, "BCA_CA_HTAY", "Cong an Tinh Ha Tay", "BCA", valid_from=date(2018, 1, 1), valid_to=date(2008, 8, 1)
)


def lookup(**kwargs) -> FakeRegistryLookup:
    return FakeRegistryLookup(**kwargs)


def test_code_exact_match():
    result = resolve(ResolutionInput(unit_code_text="BCA_C08", as_of_date=AS_OF), lookup(codes={"BCA_C08": [TRAFFIC]}))
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.match_method is MatchMethod.CODE_EXACT
    assert result.organization_type is OrganizationType.BCA
    assert result.matched_unit is TRAFFIC
    assert result.requires_review is False


def test_canonical_name_exact_match():
    registry = lookup(names={"cuc canh sat giao thong": [(TRAFFIC, "canonical")]})
    result = resolve(ResolutionInput(current_unit_text="Cuc Canh sat giao thong", as_of_date=AS_OF), registry)
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.match_method is MatchMethod.CANONICAL_EXACT
    assert result.requires_review is False


def test_alias_exact_match():
    registry = lookup(names={"bv 108": [(HOSPITAL, "alias")]})
    result = resolve(ResolutionInput(current_unit_text="BV 108", as_of_date=AS_OF), registry)
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.match_method is MatchMethod.ALIAS_EXACT
    assert result.organization_type is OrganizationType.BQP


def test_code_and_name_agree_keeps_code_as_method():
    registry = lookup(
        codes={"BCA_C08": [TRAFFIC]},
        names={"cuc canh sat giao thong": [(TRAFFIC, "canonical")]},
    )
    result = resolve(
        ResolutionInput(current_unit_text="Cuc Canh sat giao thong", unit_code_text="BCA_C08", as_of_date=AS_OF),
        registry,
    )
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.match_method is MatchMethod.CODE_EXACT
    assert result.requires_review is False


def test_code_and_name_disagree_is_conflict():
    registry = lookup(
        codes={"BCA_A05": [CYBER]},
        names={"cuc canh sat giao thong": [(TRAFFIC, "canonical")]},
    )
    result = resolve(
        ResolutionInput(current_unit_text="Cuc Canh sat giao thong", unit_code_text="BCA_A05", as_of_date=AS_OF),
        registry,
    )
    assert result.resolution_status is ResolutionStatus.CONFLICT
    assert result.organization_type is OrganizationType.UNKNOWN
    assert result.matched_unit is None
    assert result.review_reason is ReviewReason.CODE_NAME_CONFLICT


def test_alias_shared_by_two_units_is_ambiguous():
    registry = lookup(names={"cuc": [(TRAFFIC, "abbreviation"), (CYBER, "abbreviation")]})
    result = resolve(ResolutionInput(current_unit_text="Cuc", as_of_date=AS_OF), registry)
    assert result.resolution_status is ResolutionStatus.AMBIGUOUS
    assert result.review_reason is ReviewReason.AMBIGUOUS_CANDIDATES
    assert result.matched_unit is None


def test_code_narrows_an_ambiguous_name():
    registry = lookup(
        codes={"BCA_C08": [TRAFFIC]},
        names={"cuc": [(TRAFFIC, "abbreviation"), (CYBER, "abbreviation")]},
    )
    result = resolve(
        ResolutionInput(current_unit_text="Cuc", unit_code_text="BCA_C08", as_of_date=AS_OF), registry
    )
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.matched_unit is TRAFFIC


def test_unknown_name_is_not_found_and_never_other():
    result = resolve(ResolutionInput(current_unit_text="Phong XYZ", as_of_date=AS_OF), lookup())
    assert result.resolution_status is ResolutionStatus.NOT_FOUND
    assert result.organization_type is OrganizationType.UNKNOWN
    assert result.review_reason is ReviewReason.NAME_NOT_IN_REGISTRY
    assert result.requires_review is True


def test_unresolved_code_with_matching_name_is_flagged_for_review():
    registry = lookup(names={"cuc canh sat giao thong": [(TRAFFIC, "canonical")]})
    result = resolve(
        ResolutionInput(current_unit_text="Cuc Canh sat giao thong", unit_code_text="BCA_XXX", as_of_date=AS_OF),
        registry,
    )
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.review_reason is ReviewReason.UNRESOLVED_CODE
    assert result.requires_review is True


def test_matching_code_with_unknown_name_is_flagged_for_review():
    registry = lookup(codes={"BCA_C08": [TRAFFIC]})
    result = resolve(
        ResolutionInput(current_unit_text="Phong XYZ", unit_code_text="BCA_C08", as_of_date=AS_OF), registry
    )
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.review_reason is ReviewReason.NAME_NOT_IN_REGISTRY


def test_code_text_resolved_through_an_approved_alias():
    registry = lookup(names={"c08": [(TRAFFIC, "abbreviation")]})
    result = resolve(ResolutionInput(unit_code_text="C08", as_of_date=AS_OF), registry)
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.match_method is MatchMethod.CODE_ALIAS_EXACT


def test_expired_unit_is_not_matched():
    registry = lookup(codes={"BQP_QD1": [CLOSED]})
    result = resolve(ResolutionInput(unit_code_text="BQP_QD1", as_of_date=AS_OF), registry)
    assert result.resolution_status is ResolutionStatus.NOT_FOUND
    assert result.review_reason is ReviewReason.OUT_OF_VALIDITY_WINDOW
    assert result.evidence["candidates"]["by_code"][0]["validity_note"] == "OUT_OF_WINDOW"


def test_expired_unit_matches_inside_its_own_window():
    registry = lookup(codes={"BQP_QD1": [CLOSED]})
    result = resolve(ResolutionInput(unit_code_text="BQP_QD1", as_of_date=date(2020, 6, 1)), registry)
    assert result.resolution_status is ResolutionStatus.MATCHED
    assert result.requires_review is False


def test_inverted_validity_window_is_reported_as_a_data_defect():
    registry = lookup(codes={"BCA_CA_HTAY": [BROKEN]})
    result = resolve(ResolutionInput(unit_code_text="BCA_CA_HTAY", as_of_date=date(2007, 1, 1)), registry)
    assert result.resolution_status is ResolutionStatus.NOT_FOUND
    assert result.review_reason is ReviewReason.REGISTRY_DATA_DEFECT


def test_empty_input_is_rejected():
    with pytest.raises(EmptyResolutionInputError):
        resolve(ResolutionInput(), lookup())
    with pytest.raises(EmptyResolutionInputError):
        resolve(ResolutionInput(current_unit_text="   "), lookup())


def test_evidence_is_complete_and_json_serializable():
    registry = lookup(codes={"BCA_C08": [TRAFFIC]})
    result = resolve(ResolutionInput(unit_code_text="bca_c08", as_of_date=AS_OF), registry)
    evidence = result.evidence
    assert evidence["input"]["unit_code_text"] == "bca_c08"
    assert evidence["as_of_date"] == "2026-01-01"
    assert evidence["normalization"]["code"] == "BCA_C08"
    assert evidence["candidates"]["by_code"][0]["unit_id"] == TRAFFIC.unit_id
    assert evidence["decision"]["match_method"] == "CODE_EXACT"
    assert json.loads(json.dumps(result.to_dict()))["resolution_status"] == "MATCHED"


def test_result_dictionary_carries_registry_version():
    registry = lookup(codes={"BCA_C08": [TRAFFIC]}, version="v9.9.9")
    result = resolve(ResolutionInput(unit_code_text="BCA_C08", as_of_date=AS_OF), registry)
    assert result.to_dict()["registry_version"] == "v9.9.9"
