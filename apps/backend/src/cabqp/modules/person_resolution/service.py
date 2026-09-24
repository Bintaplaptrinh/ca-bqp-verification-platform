from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.resolution.service import Resolver
from cabqp.shared.models import (
    Person,
    PersonCode,
    PersonCodeSnapshot,
    PersonName,
    PersonNameSnapshot,
    PersonRegistrySnapshot,
    PersonRegistryVersion,
    Unit,
)
from cabqp.shared.normalization import ascii_key, normalize_text
from cabqp.shared.settings import get_settings


@dataclass
class IndexedPerson:
    person_id: str
    full_name: str
    normalized_key: str
    ascii_key: str | None
    birth_year: int | None
    canonical_unit_id: str
    canonical_unit_name: str | None
    employment_status: str
    subject_group_hint: str | None
    source_kind: str
    synthetic_welfare_facts: dict | None
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool = True
    aliases: list[tuple[str, str, str | None]] = field(default_factory=list)
    codes: list[tuple[str, str]] = field(default_factory=list)

    def folded_key(self) -> str:
        return self.ascii_key or ascii_key(self.full_name)


@dataclass
class PersonResolution:
    status: str
    person_id: str | None
    full_name: str | None
    canonical_unit_id: str | None
    canonical_unit_name: str | None
    birth_year: int | None
    employment_status: str | None
    subject_group_hint: str | None
    match_method: str | None
    score: float | None
    margin: float | None
    candidates: list[dict]
    registry_version: str | None
    source_kind: str = "PROVIDED"
    decision_confidence: float | None = None
    synthetic_welfare_facts: dict | None = None


_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: dict[str, tuple[float, list[IndexedPerson]]] = {}


def _active_on(as_of: date | None, start: date | None, end: date | None) -> bool:
    target = as_of or date.today()
    return (start is None or start <= target) and (end is None or target <= end)


class PersonResolver:
    """Resolve person identity only.

    This service deliberately does not expose organization_type. A matched person's
    canonical_unit_id must be handed to the unit Resolver, which remains the sole
    authority for BCA/BQP/OTHER/UNKNOWN classification.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _published_version_row(self) -> PersonRegistryVersion | None:
        return self.db.scalar(
            select(PersonRegistryVersion)
            .where(PersonRegistryVersion.status == "PUBLISHED")
            .order_by(PersonRegistryVersion.published_at.desc())
        )

    def _unit_names(self, unit_ids: set[str]) -> dict[str, str]:
        if not unit_ids:
            return {}
        return {
            u.id: u.canonical_name
            for u in self.db.scalars(select(Unit).where(Unit.id.in_(sorted(unit_ids))))
        }

    def _load_snapshot_index(self, rv: PersonRegistryVersion) -> list[IndexedPerson]:
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _INDEX_CACHE.get(rv.id)
            if cached and now - cached[0] < self.settings.resolver_cache_ttl_seconds:
                return cached[1]

        snapshots = list(
            self.db.scalars(
                select(PersonRegistrySnapshot).where(
                    PersonRegistrySnapshot.registry_version_id == rv.id,
                    PersonRegistrySnapshot.active.is_(True),
                )
            )
        )
        unit_names = self._unit_names({p.canonical_unit_id for p in snapshots})
        by_id = {
            p.person_id: IndexedPerson(
                person_id=p.person_id,
                full_name=p.full_name,
                normalized_key=p.normalized_key,
                ascii_key=p.ascii_key,
                birth_year=p.birth_year,
                canonical_unit_id=p.canonical_unit_id,
                canonical_unit_name=unit_names.get(p.canonical_unit_id),
                employment_status=p.employment_status,
                subject_group_hint=p.subject_group_hint,
                source_kind=p.source_kind,
                synthetic_welfare_facts=p.synthetic_welfare_facts,
                valid_from=p.valid_from,
                valid_to=p.valid_to,
                active=p.active,
            )
            for p in snapshots
        }
        for alias in self.db.scalars(
            select(PersonNameSnapshot).where(PersonNameSnapshot.registry_version_id == rv.id)
        ):
            person = by_id.get(alias.person_id)
            if person:
                person.aliases.append((alias.name, alias.normalized_key, alias.ascii_key))
        for code in self.db.scalars(
            select(PersonCodeSnapshot).where(PersonCodeSnapshot.registry_version_id == rv.id)
        ):
            person = by_id.get(code.person_id)
            if person:
                person.codes.append((code.code, code.namespace))

        people = list(by_id.values())
        with _CACHE_LOCK:
            _INDEX_CACHE[rv.id] = (now, people)
        return people

    def _load_live_index(self) -> list[IndexedPerson]:
        people = list(
            self.db.scalars(
                select(Person).where(Person.active.is_(True), Person.qa_status == "APPROVED")
            )
        )
        unit_names = self._unit_names({p.canonical_unit_id for p in people})
        out: list[IndexedPerson] = []
        for p in people:
            item = IndexedPerson(
                person_id=p.id,
                full_name=p.full_name,
                normalized_key=p.normalized_key,
                ascii_key=p.ascii_key,
                birth_year=p.birth_year,
                canonical_unit_id=p.canonical_unit_id,
                canonical_unit_name=unit_names.get(p.canonical_unit_id),
                employment_status=p.employment_status,
                subject_group_hint=p.subject_group_hint,
                source_kind=p.source_kind,
                synthetic_welfare_facts=p.synthetic_welfare_facts,
                valid_from=p.valid_from,
                valid_to=p.valid_to,
                active=p.active,
            )
            for alias in self.db.scalars(
                select(PersonName).where(
                    PersonName.person_id == p.id,
                    PersonName.qa_status == "APPROVED",
                )
            ):
                item.aliases.append((alias.name, alias.normalized_key, alias.ascii_key))
            for code in self.db.scalars(
                select(PersonCode).where(
                    PersonCode.person_id == p.id,
                    PersonCode.qa_status == "APPROVED",
                )
            ):
                item.codes.append((code.code, code.namespace))
            out.append(item)
        return out

    def _index(self) -> tuple[PersonRegistryVersion | None, list[IndexedPerson]]:
        rv = self._published_version_row()
        return rv, self._load_snapshot_index(rv) if rv else self._load_live_index()

    @staticmethod
    def _candidate(person: IndexedPerson, *, score: float, evidence: str) -> dict:
        return {
            "person_id": person.person_id,
            "full_name": person.full_name,
            "birth_year": person.birth_year,
            "canonical_unit_id": person.canonical_unit_id,
            "canonical_unit_name": person.canonical_unit_name,
            "employment_status": person.employment_status,
            "source_kind": person.source_kind,
            "score": round(score, 2),
            "evidence": evidence,
        }

    def _code_matches(
        self, people: list[IndexedPerson], personal_code: str | None, as_of: date | None
    ) -> list[IndexedPerson]:
        if not personal_code:
            return []
        target = personal_code.strip().casefold()
        return [
            p
            for p in people
            if _active_on(as_of, p.valid_from, p.valid_to)
            and any(code.casefold() == target for code, _namespace in p.codes)
        ]

    def _exact_name_matches(
        self, people: list[IndexedPerson], full_name: str | None, as_of: date | None
    ) -> tuple[list[IndexedPerson], str | None]:
        if not full_name:
            return [], None
        key = normalize_text(full_name)
        canonical = [
            p
            for p in people
            if _active_on(as_of, p.valid_from, p.valid_to) and p.normalized_key == key
        ]
        if canonical:
            return canonical, "CANONICAL_EXACT"

        aliases = [
            p
            for p in people
            if _active_on(as_of, p.valid_from, p.valid_to)
            and any(alias_key == key for _name, alias_key, _ascii in p.aliases)
        ]
        if aliases:
            return aliases, "APPROVED_ALIAS"

        folded = ascii_key(full_name)
        if not folded:
            return [], None
        canonical_folded = [
            p
            for p in people
            if _active_on(as_of, p.valid_from, p.valid_to) and p.folded_key() == folded
        ]
        if canonical_folded:
            return canonical_folded, "ASCII_FOLDED"
        alias_folded = [
            p
            for p in people
            if _active_on(as_of, p.valid_from, p.valid_to)
            and any((alias_ascii or ascii_key(alias_name)) == folded for alias_name, _key, alias_ascii in p.aliases)
        ]
        if alias_folded:
            return alias_folded, "ASCII_FOLDED_ALIAS"
        return [], None

    def _narrow(
        self,
        candidates: list[IndexedPerson],
        *,
        birth_year: int | None,
        unit_id: str | None,
        unit_name: str | None,
        as_of: date | None,
    ) -> tuple[list[IndexedPerson], bool]:
        narrowed = list(candidates)
        used = False
        if birth_year is not None:
            used = True
            narrowed = [p for p in narrowed if p.birth_year == birth_year]

        narrowed_unit_id = unit_id
        if narrowed_unit_id is None and unit_name:
            used = True
            unit_resolution = Resolver(self.db).resolve(unit_name=unit_name, as_of_date=as_of)
            if unit_resolution.status == "MATCHED":
                narrowed_unit_id = unit_resolution.unit_id
            else:
                return [], True
        if narrowed_unit_id is not None:
            used = True
            narrowed = [p for p in narrowed if p.canonical_unit_id == narrowed_unit_id]
        return narrowed, used

    def _matched(
        self,
        p: IndexedPerson,
        *,
        method: str,
        score: float,
        margin: float,
        version: str | None,
        confidence: float = 1.0,
    ) -> PersonResolution:
        return PersonResolution(
            status="MATCHED",
            person_id=p.person_id,
            full_name=p.full_name,
            canonical_unit_id=p.canonical_unit_id,
            canonical_unit_name=p.canonical_unit_name,
            birth_year=p.birth_year,
            employment_status=p.employment_status,
            subject_group_hint=p.subject_group_hint,
            match_method=method,
            score=score,
            margin=margin,
            candidates=[],
            registry_version=version,
            source_kind=p.source_kind,
            decision_confidence=confidence,
            synthetic_welfare_facts=p.synthetic_welfare_facts,
        )

    def _abstain(
        self,
        status: str,
        *,
        method: str | None,
        score: float | None,
        margin: float | None,
        candidates: list[dict],
        version: str | None,
    ) -> PersonResolution:
        # Preserve provenance even when identity resolution abstains. If every
        # candidate comes from the same source class (notably SYNTHETIC_DEMO),
        # surface that class at the resolution level as well. Mixed/empty
        # candidate sets stay PROVIDED because there is no single authoritative
        # source kind to claim; per-candidate provenance remains in evidence.
        kinds = {str(c.get("source_kind")) for c in candidates if c.get("source_kind")}
        source_kind = next(iter(kinds)) if len(kinds) == 1 else "PROVIDED"
        return PersonResolution(
            status=status,
            person_id=None,
            full_name=None,
            canonical_unit_id=None,
            canonical_unit_name=None,
            birth_year=None,
            employment_status=None,
            subject_group_hint=None,
            match_method=method,
            score=score,
            margin=margin,
            candidates=candidates,
            registry_version=version,
            source_kind=source_kind,
            decision_confidence=0.0,
        )

    def resolve(
        self,
        *,
        full_name: str | None = None,
        personal_code: str | None = None,
        birth_year: int | None = None,
        unit_id: str | None = None,
        unit_name: str | None = None,
        as_of_date: date | None = None,
    ) -> PersonResolution:
        rv, people = self._index()
        version = rv.version if rv else None

        code_matches = self._code_matches(people, personal_code, as_of_date)
        exact_matches, exact_method = self._exact_name_matches(people, full_name, as_of_date)

        if len({p.person_id for p in code_matches}) > 1:
            return self._abstain(
                "AMBIGUOUS",
                method="PERSON_CODE_AMBIGUOUS",
                score=100.0,
                margin=0.0,
                candidates=[self._candidate(p, score=100.0, evidence="TRUSTED_CODE") for p in code_matches],
                version=version,
            )
        code_person = code_matches[0] if code_matches else None

        if code_person and len(exact_matches) == 1 and exact_matches[0].person_id != code_person.person_id:
            return self._abstain(
                "CONFLICT",
                method="PERSON_CODE_NAME_CONFLICT",
                score=100.0,
                margin=0.0,
                candidates=[
                    self._candidate(code_person, score=100.0, evidence="TRUSTED_CODE"),
                    self._candidate(exact_matches[0], score=100.0, evidence=exact_method or "EXACT_NAME"),
                ],
                version=version,
            )
        if code_person:
            return self._matched(
                code_person,
                method="TRUSTED_PERSON_CODE",
                score=100.0,
                margin=100.0,
                version=version,
            )

        if exact_matches:
            narrowed, narrowing_used = self._narrow(
                exact_matches,
                birth_year=birth_year,
                unit_id=unit_id,
                unit_name=unit_name,
                as_of=as_of_date,
            )
            if len(narrowed) == 1:
                method = f"{exact_method}_NARROWED" if narrowing_used else (exact_method or "EXACT_NAME")
                score_map = {
                    "CANONICAL_EXACT": 100.0,
                    "APPROVED_ALIAS": 99.0,
                    "ASCII_FOLDED": 97.0,
                    "ASCII_FOLDED_ALIAS": 96.0,
                }
                return self._matched(
                    narrowed[0],
                    method=method,
                    score=score_map.get(exact_method or "", 99.0),
                    margin=100.0,
                    version=version,
                )
            if narrowing_used and not narrowed:
                return self._abstain(
                    "CONFLICT",
                    method="PERSON_NARROWING_CONFLICT",
                    score=100.0,
                    margin=0.0,
                    candidates=[self._candidate(p, score=100.0, evidence=exact_method or "EXACT_NAME") for p in exact_matches],
                    version=version,
                )
            return self._abstain(
                "AMBIGUOUS",
                method="PERSON_EXACT_NAME_AMBIGUOUS",
                score=100.0,
                margin=0.0,
                candidates=[self._candidate(p, score=100.0, evidence=exact_method or "EXACT_NAME") for p in (narrowed or exact_matches)],
                version=version,
            )

        if not full_name:
            return self._abstain(
                "NOT_FOUND", method=None, score=None, margin=None, candidates=[], version=version
            )

        active_people = [p for p in people if _active_on(as_of_date, p.valid_from, p.valid_to)]
        query = normalize_text(full_name)
        # A one-letter name token is commonly an abbreviation (for example
        # "Nguyen Van A"). WRatio scores it very highly against unrelated names
        # such as "Nguyen Van An/Nam/Lan". Unless the registry contains an exact
        # name (handled above), abstain instead of presenting autocomplete-like
        # suggestions as identity candidates.
        if any(len(token) == 1 for token in query.split()):
            return self._abstain(
                "NOT_FOUND",
                method="INCOMPLETE_NAME_QUERY",
                score=None,
                margin=None,
                candidates=[],
                version=version,
            )

        ranked: list[tuple[IndexedPerson, float]] = []
        for p in active_people:
            score = float(fuzz.WRatio(query, p.normalized_key))
            for _name, alias_key, _ascii in p.aliases:
                score = max(score, float(fuzz.WRatio(query, alias_key)))
            ranked.append((p, score))
        ranked.sort(key=lambda row: row[1], reverse=True)
        ranked = ranked[: self.settings.resolver_candidate_limit]
        payload = [self._candidate(p, score=score, evidence="FUZZY_NAME") for p, score in ranked]
        if not ranked:
            return self._abstain(
                "NOT_FOUND", method="FUZZY_NAME", score=None, margin=None, candidates=[], version=version
            )

        top_person, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second_score
        strong = (
            top_score >= self.settings.resolver_fuzzy_threshold
            and margin >= self.settings.resolver_margin_threshold
        )
        if strong:
            narrowed, narrowing_used = self._narrow(
                [top_person],
                birth_year=birth_year,
                unit_id=unit_id,
                unit_name=unit_name,
                as_of=as_of_date,
            )
            if narrowing_used and not narrowed:
                return self._abstain(
                    "CONFLICT",
                    method="PERSON_FUZZY_NARROWING_CONFLICT",
                    score=top_score,
                    margin=margin,
                    candidates=payload,
                    version=version,
                )
            return self._matched(
                top_person,
                method="FUZZY_NAME",
                score=top_score,
                margin=margin,
                version=version,
                confidence=max(0.0, min(1.0, top_score / 100.0)),
            )

        # Only expose fuzzy candidates that actually clear the configured
        # identity threshold. Lower scores are search similarities, not
        # evidence that the records may be the same person.
        if top_score >= self.settings.resolver_fuzzy_threshold:
            return self._abstain(
                "AMBIGUOUS",
                method="FUZZY_NAME",
                score=top_score,
                margin=margin,
                candidates=payload,
                version=version,
            )
        return self._abstain(
            "NOT_FOUND",
            method="FUZZY_NAME",
            score=top_score,
            margin=margin,
            candidates=[],
            version=version,
        )
