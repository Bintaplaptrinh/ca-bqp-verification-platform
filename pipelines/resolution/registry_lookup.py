"""Registry lookup boundary for the unit resolution module.

UnitRegistryLookup is the seam between this module and the storage layer. The
resolver only knows this interface, so the system team can implement a
PostgreSQL backed lookup without touching resolution logic.

CsvUnitRegistryLookup is the reference implementation used for development,
tests and offline QA. It reads the published registry artifacts and keeps them
in memory. It is not intended for production serving.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Protocol, runtime_checkable

from pipelines.resolution.contracts import (
    Candidate,
    NormalizationLevel,
    OrganizationType,
    UnitRecord,
)
from pipelines.resolution.text_normalize import (
    fold_ascii,
    is_blank,
    normalize_code,
    normalize_name,
)

MASTER_UNITS_FILE = "master_units.csv"
UNIT_ALIASES_FILE = "unit_aliases.csv"
APPROVED_ALIAS_DELTA_FILE = "unit_aliases_approved_delta.csv"

UNAPPROVED_ALIAS_TYPES = frozenset({"typo_ocr"})
UNAPPROVED_GENERATOR_SOURCES = frozenset({"noise_injector"})

CANONICAL_FIELD = "canonical"
CODE_FIELD = "unit_code"


@runtime_checkable
class UnitRegistryLookup(Protocol):
    """Read only access to one published registry snapshot."""

    def registry_version(self) -> str:
        """Return the registry version of the snapshot backing this lookup."""

    def find_by_code(self, code_text: str, as_of: date) -> list[Candidate]:
        """Return every unit whose code equals the normalized input code.

        Candidates that are outside their validity window at as_of must still
        be returned, with is_valid_at set to False, so that the caller can tell
        an unknown code apart from a code that only existed in the past.
        """

    def find_by_name(self, name_text: str, as_of: date, approved_only: bool = True) -> list[Candidate]:
        """Return every unit whose canonical name or alias equals the input.

        Matching is exact after normalization. STRICT matches are preferred; the
        ASCII folded index is consulted only when STRICT yields nothing.
        """


@dataclass(frozen=True)
class RegistryIntegrityReport:
    """Data quality signals observed while loading a registry snapshot."""

    unit_count: int
    alias_count: int
    approved_alias_count: int
    delta_alias_count: int
    inverted_validity_windows: list[str]
    duplicate_codes_same_window: list[str]
    registry_version: str
    content_checksum_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_count": self.unit_count,
            "alias_count": self.alias_count,
            "approved_alias_count": self.approved_alias_count,
            "delta_alias_count": self.delta_alias_count,
            "inverted_validity_windows": self.inverted_validity_windows,
            "duplicate_codes_same_window": self.duplicate_codes_same_window,
            "registry_version": self.registry_version,
            "content_checksum_sha256": self.content_checksum_sha256,
        }


def _parse_date(value: str, default: date | None = None) -> date | None:
    value = (value or "").strip()
    if not value:
        return default
    return date.fromisoformat(value)


def _default_dataset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "datasets" / "samples"


class CsvUnitRegistryLookup:
    """In memory lookup over the published registry CSV artifacts."""

    def __init__(
        self,
        units: list[UnitRecord],
        alias_rows: list[tuple[int, str, str, str]],
        content_checksum: str = "",
        delta_alias_count: int = 0,
    ) -> None:
        self._units: dict[int, UnitRecord] = {unit.unit_id: unit for unit in units}
        self._code_index: dict[str, list[UnitRecord]] = {}
        self._name_index_strict: dict[str, list[tuple[int, str, str]]] = {}
        self._name_index_folded: dict[str, list[tuple[int, str, str]]] = {}
        self._alias_rows = alias_rows
        self._content_checksum = content_checksum
        self._delta_alias_count = delta_alias_count

        for unit in units:
            if unit.unit_code:
                self._code_index.setdefault(normalize_code(unit.unit_code), []).append(unit)

        for unit_id, alias_name, alias_type, generator_source in alias_rows:
            if self._is_unapproved(alias_type, generator_source):
                continue
            entry = (unit_id, alias_name, alias_type)
            self._name_index_strict.setdefault(normalize_name(alias_name), []).append(entry)
            self._name_index_folded.setdefault(fold_ascii(alias_name), []).append(entry)

        self._name_index_strict_all: dict[str, list[tuple[int, str, str]]] = {}
        self._name_index_folded_all: dict[str, list[tuple[int, str, str]]] = {}
        for unit_id, alias_name, alias_type, _generator_source in alias_rows:
            entry = (unit_id, alias_name, alias_type)
            self._name_index_strict_all.setdefault(normalize_name(alias_name), []).append(entry)
            self._name_index_folded_all.setdefault(fold_ascii(alias_name), []).append(entry)

        versions = {unit.registry_version for unit in units}
        self._registry_version = versions.pop() if len(versions) == 1 else "MIXED"

    @staticmethod
    def _is_unapproved(alias_type: str, generator_source: str) -> bool:
        return alias_type in UNAPPROVED_ALIAS_TYPES or generator_source in UNAPPROVED_GENERATOR_SOURCES

    @classmethod
    def from_dataset_dir(cls, dataset_dir: str | Path | None = None) -> CsvUnitRegistryLookup:
        """Build a lookup from master_units.csv, unit_aliases.csv and the delta file."""
        directory = Path(dataset_dir) if dataset_dir is not None else _default_dataset_dir()
        master_path = directory / MASTER_UNITS_FILE
        alias_path = directory / UNIT_ALIASES_FILE
        delta_path = directory / APPROVED_ALIAS_DELTA_FILE

        units: list[UnitRecord] = []
        raw_units: list[dict[str, str]] = []
        with master_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                raw_units.append(dict(row))
                units.append(
                    UnitRecord(
                        unit_id=int(row["unit_id"]),
                        unit_code=(row.get("unit_code") or "").strip() or None,
                        canonical_name=row["canonical_name"],
                        organization_type=OrganizationType(row["organization_type"]),
                        unit_level=row.get("unit_level", ""),
                        valid_from=_parse_date(row.get("valid_from", ""), date(1900, 1, 1)),
                        valid_to=_parse_date(row.get("valid_to", "")),
                        registry_version=row.get("registry_version", ""),
                        qa_confidence=row.get("qa_confidence", ""),
                    )
                )

        alias_rows: list[tuple[int, str, str, str]] = []
        with alias_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                alias_rows.append(
                    (
                        int(row["unit_id"]),
                        row["alias_name"],
                        row.get("alias_type", ""),
                        row.get("generator_source", ""),
                    )
                )

        delta_count = 0
        if delta_path.exists():
            code_to_units: dict[str, list[UnitRecord]] = {}
            for unit in units:
                if unit.unit_code:
                    code_to_units.setdefault(normalize_code(unit.unit_code), []).append(unit)
            with delta_path.open(encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    code = normalize_code(row.get("unit_code", ""))
                    alias_name = (row.get("alias_name") or "").strip()
                    if not code or not alias_name:
                        continue
                    for unit in code_to_units.get(code, []):
                        alias_rows.append(
                            (
                                unit.unit_id,
                                alias_name,
                                row.get("alias_type", "approved_common_name"),
                                row.get("generator_source", "manual_review"),
                            )
                        )
                        delta_count += 1

        checksum = hashlib.sha256(
            json.dumps(raw_units, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return cls(units, alias_rows, content_checksum=checksum, delta_alias_count=delta_count)

    def registry_version(self) -> str:
        return self._registry_version

    def unit_count(self) -> int:
        return len(self._units)

    def get_unit(self, unit_id: int) -> UnitRecord | None:
        return self._units.get(unit_id)

    def find_by_code(self, code_text: str, as_of: date) -> list[Candidate]:
        if is_blank(code_text):
            return []
        key = normalize_code(code_text)
        candidates: list[Candidate] = []
        for unit in self._code_index.get(key, []):
            note = unit.validity_note(as_of)
            candidates.append(
                Candidate(
                    unit=unit,
                    matched_value=unit.unit_code or "",
                    matched_field=CODE_FIELD,
                    normalization_level=NormalizationLevel.STRICT,
                    is_valid_at=note is None,
                    validity_note=note,
                )
            )
        return candidates

    def find_by_name(self, name_text: str, as_of: date, approved_only: bool = True) -> list[Candidate]:
        if is_blank(name_text):
            return []
        strict_index = self._name_index_strict if approved_only else self._name_index_strict_all
        folded_index = self._name_index_folded if approved_only else self._name_index_folded_all

        entries = strict_index.get(normalize_name(name_text), [])
        level = NormalizationLevel.STRICT
        if not entries:
            entries = folded_index.get(fold_ascii(name_text), [])
            level = NormalizationLevel.ASCII_FOLDED

        candidates: list[Candidate] = []
        seen: set[tuple[int, str]] = set()
        for unit_id, alias_name, alias_type in entries:
            unit = self._units.get(unit_id)
            if unit is None:
                continue
            key = (unit_id, alias_name)
            if key in seen:
                continue
            seen.add(key)
            note = unit.validity_note(as_of)
            candidates.append(
                Candidate(
                    unit=unit,
                    matched_value=alias_name,
                    matched_field=alias_type,
                    normalization_level=level,
                    is_valid_at=note is None,
                    validity_note=note,
                )
            )
        return candidates

    def integrity_report(self) -> RegistryIntegrityReport:
        """Report data quality signals of the loaded snapshot."""
        inverted = [
            unit.unit_code or str(unit.unit_id)
            for unit in self._units.values()
            if unit.valid_to is not None and unit.valid_to < unit.valid_from
        ]

        overlapping: list[str] = []
        for code, units in self._code_index.items():
            if len(units) < 2:
                continue
            ordered = sorted(units, key=lambda unit: unit.valid_from)
            for earlier, later in pairwise(ordered):
                earlier_end = earlier.valid_to
                if earlier_end is None or earlier_end >= later.valid_from:
                    overlapping.append(code)
                    break

        approved = sum(
            1
            for _unit_id, _alias, alias_type, generator in self._alias_rows
            if not self._is_unapproved(alias_type, generator)
        )
        return RegistryIntegrityReport(
            unit_count=len(self._units),
            alias_count=len(self._alias_rows),
            approved_alias_count=approved,
            delta_alias_count=self._delta_alias_count,
            inverted_validity_windows=sorted(set(inverted)),
            duplicate_codes_same_window=sorted(set(overlapping)),
            registry_version=self._registry_version,
            content_checksum_sha256=self._content_checksum,
        )
