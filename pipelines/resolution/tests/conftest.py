"""Pytest configuration for the unit resolution test suite.

The repository is not installed as a package, so the repository root is added
to sys.path here. This mirrors the path handling used by the other pipeline
scripts and keeps the suite runnable with a bare pytest call, without Docker
and without a database.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.resolution.contracts import (  # noqa: E402
    Candidate,
    NormalizationLevel,
    OrganizationType,
    UnitRecord,
)
from pipelines.resolution.registry_lookup import CsvUnitRegistryLookup  # noqa: E402

DATASET_DIR = REPO_ROOT / "datasets" / "samples"


def make_unit(
    unit_id: int,
    unit_code: str | None,
    canonical_name: str,
    organization_type: str = "BCA",
    valid_from: date = date(2018, 1, 1),
    valid_to: date | None = None,
) -> UnitRecord:
    """Build a unit record for tests that do not need the published dataset."""
    return UnitRecord(
        unit_id=unit_id,
        unit_code=unit_code,
        canonical_name=canonical_name,
        organization_type=OrganizationType(organization_type),
        unit_level="test_level",
        valid_from=valid_from,
        valid_to=valid_to,
        registry_version="test",
        qa_confidence="HIGH",
    )


class FakeRegistryLookup:
    """Minimal in test registry used to exercise every cascade branch."""

    def __init__(
        self,
        codes: dict[str, list[UnitRecord]] | None = None,
        names: dict[str, list[tuple[UnitRecord, str]]] | None = None,
        version: str = "test-1",
    ) -> None:
        self._codes = codes or {}
        self._names = names or {}
        self._version = version

    def registry_version(self) -> str:
        return self._version

    def find_by_code(self, code_text: str, as_of: date) -> list[Candidate]:
        return [
            _candidate(unit, unit.unit_code or "", "unit_code", as_of)
            for unit in self._codes.get(code_text.strip().upper(), [])
        ]

    def find_by_name(self, name_text: str, as_of: date, approved_only: bool = True) -> list[Candidate]:
        key = " ".join(name_text.split()).casefold()
        return [
            _candidate(unit, name_text, field, as_of)
            for unit, field in self._names.get(key, [])
        ]


def _candidate(unit: UnitRecord, value: str, field: str, as_of: date) -> Candidate:
    note = unit.validity_note(as_of)
    return Candidate(
        unit=unit,
        matched_value=value,
        matched_field=field,
        normalization_level=NormalizationLevel.STRICT,
        is_valid_at=note is None,
        validity_note=note,
    )


@pytest.fixture(scope="session")
def dataset_lookup() -> CsvUnitRegistryLookup:
    """Lookup backed by the published registry artifacts in datasets/samples."""
    return CsvUnitRegistryLookup.from_dataset_dir(DATASET_DIR)
