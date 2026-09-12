"""Golden regression over datasets/samples/hard_cases.jsonl.

Each hard case is paired with a structured input in fixtures/hard_case_inputs.json,
because this module consumes separated fields rather than raw document text.
Cases that exact matching cannot serve are kept in the suite as strict expected
failures or explicit skips, so the backlog stays visible.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from conftest import DATASET_DIR

from pipelines.resolution.contracts import ResolutionInput
from pipelines.resolution.resolver import EmptyResolutionInputError, resolve

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hard_case_inputs.json"
HARD_CASES_PATH = DATASET_DIR / "hard_cases.jsonl"

FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]
CASES_BY_ID = {case["case_id"]: case for case in CASES}


def _hard_case_ids() -> list[str]:
    ids = []
    with HARD_CASES_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                ids.append(json.loads(line)["case_id"])
    return ids


def _build_input(payload: dict) -> ResolutionInput:
    as_of = payload.get("as_of_date")
    return ResolutionInput(
        current_unit_text=payload.get("current_unit_text"),
        unit_code_text=payload.get("unit_code_text"),
        as_of_date=date.fromisoformat(as_of) if as_of else None,
    )


def _assert_expectation(result, expected: dict) -> None:
    assert str(result.resolution_status) == expected["resolution_status"]
    assert str(result.organization_type) == expected["organization_type"]
    assert result.requires_review is expected["requires_review"]
    if "match_method" in expected:
        assert str(result.match_method) == expected["match_method"]
    if "review_reason" in expected:
        assert str(result.review_reason) == expected["review_reason"]
    if "unit_id" in expected:
        assert result.matched_unit is not None
        assert result.matched_unit.unit_id == expected["unit_id"]


def test_every_hard_case_has_a_fixture_entry():
    assert sorted(CASES_BY_ID) == sorted(_hard_case_ids())


def test_scope_counts_are_stable():
    scopes = [case["scope"] for case in CASES]
    assert scopes.count("in_scope") == 13
    assert scopes.count("deferred_xfail") == 2
    assert scopes.count("out_of_scope_skip") == 1


@pytest.mark.parametrize("case", [c for c in CASES if c["scope"] == "in_scope"], ids=lambda c: c["case_id"])
def test_in_scope_hard_cases(case, dataset_lookup):
    request_payload = case["input"]
    if "expected_error" in case:
        with pytest.raises(EmptyResolutionInputError):
            resolve(_build_input(request_payload), dataset_lookup)
        return
    result = resolve(_build_input(request_payload), dataset_lookup)
    _assert_expectation(result, case["expected"])
    assert result.evidence["decision"]["resolution_status"] == case["expected"]["resolution_status"]
    assert result.registry_version == "v2.0.0"


@pytest.mark.parametrize("case", [c for c in CASES if c["scope"] == "deferred_xfail"], ids=lambda c: c["case_id"])
@pytest.mark.xfail(strict=True, reason="not solvable by exact matching at this stage, see fixture note")
def test_deferred_hard_cases_still_fail(case, dataset_lookup):
    result = resolve(_build_input(case["input"]), dataset_lookup)
    _assert_expectation(result, case["expected"])


@pytest.mark.parametrize("case", [c for c in CASES if c["scope"] == "out_of_scope_skip"], ids=lambda c: c["case_id"])
def test_out_of_scope_hard_cases(case):
    pytest.skip(case["note"])
