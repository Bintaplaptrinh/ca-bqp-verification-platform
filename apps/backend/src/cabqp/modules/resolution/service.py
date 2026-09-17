from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from cabqp.modules.resolution.calibration import ResolverCalibrator
from cabqp.shared.models import (
    RegistrySnapshotCode,
    RegistrySnapshotName,
    RegistrySnapshotUnit,
    RegistryVersion,
    Source,
    Unit,
    UnitCode,
    UnitName,
)
from cabqp.shared.normalization import ascii_key, normalize_text
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class IndexedUnit:
    unit_id: str
    canonical_name: str
    normalized_key: str
    organization_type: str
    coverage_group: str | None
    source_id: str | None
    ascii_key: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool = True
    # (name, normalized_key, valid_from, valid_to, ascii_key)
    aliases: list[tuple[str, str, date | None, date | None, str | None]] = field(default_factory=list)
    codes: list[tuple[str, str, date | None, date | None]] = field(default_factory=list)

    def folded_key(self) -> str:
        """Diacritic-folded canonical key, computed on demand for older snapshots."""
        return self.ascii_key or ascii_key(self.canonical_name)


@dataclass
class Resolution:
    status: str
    organization_type: str
    unit_id: str | None
    canonical_name: str | None
    match_method: str | None
    score: float | None
    margin: float | None
    candidates: list[dict]
    registry_version: str | None
    source_kind: str = "PROVIDED"
    calibration_status: str = "NOT_REQUIRED"
    decision_confidence: float | None = None
    coverage_group: str | None = None


_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: dict[str, tuple[float, list[IndexedUnit]]] = {}
_EMBED_LOCK = threading.Lock()
_EMBED_MODELS: dict[str, object] = {}
_EMBED_CACHE: dict[str, tuple[list[str], np.ndarray]] = {}


def _active_on(as_of: date | None, start: date | None, end: date | None) -> bool:
    if as_of is None:
        as_of = date.today()
    return (start is None or start <= as_of) and (end is None or as_of <= end)


def _tokenize(value: str) -> list[str]:
    return [x for x in normalize_text(value).split() if x]


class Resolver:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.calibrator = ResolverCalibrator()

    def _published_version_row(self) -> RegistryVersion | None:
        return self.db.scalar(
            select(RegistryVersion)
            .where(RegistryVersion.status == "PUBLISHED")
            .order_by(RegistryVersion.published_at.desc())
        )

    def _source_kind(self, source_id: str | None) -> str:
        if not source_id:
            return "PROVIDED"
        src = self.db.get(Source, source_id)
        return src.source_kind if src else "PROVIDED"

    def _load_snapshot_index(self, rv: RegistryVersion) -> list[IndexedUnit]:
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _INDEX_CACHE.get(rv.id)
            if cached and now - cached[0] < self.settings.resolver_cache_ttl_seconds:
                return cached[1]

        rows = list(
            self.db.scalars(
                select(RegistrySnapshotUnit).where(
                    RegistrySnapshotUnit.registry_version_id == rv.id,
                    RegistrySnapshotUnit.active.is_(True),
                )
            )
        )
        by_id = {
            row.unit_id: IndexedUnit(
                unit_id=row.unit_id,
                canonical_name=row.canonical_name,
                normalized_key=row.normalized_key,
                ascii_key=row.ascii_key,
                organization_type=row.organization_type,
                coverage_group=row.coverage_group,
                source_id=row.source_id,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                active=row.active,
            )
            for row in rows
        }
        for name in self.db.scalars(
            select(RegistrySnapshotName).where(RegistrySnapshotName.registry_version_id == rv.id)
        ):
            unit = by_id.get(name.unit_id)
            if unit:
                unit.aliases.append(
                    (name.name, name.normalized_key, name.valid_from, name.valid_to, name.ascii_key)
                )
        for code in self.db.scalars(
            select(RegistrySnapshotCode).where(RegistrySnapshotCode.registry_version_id == rv.id)
        ):
            unit = by_id.get(code.unit_id)
            if unit:
                unit.codes.append((code.code, code.namespace, code.valid_from, code.valid_to))
        units = list(by_id.values())
        with _CACHE_LOCK:
            _INDEX_CACHE[rv.id] = (now, units)
        return units

    def _load_legacy_index(self) -> list[IndexedUnit]:
        # Compatibility path for tests/dev databases with no published registry snapshot.
        units = list(
            self.db.scalars(select(Unit).where(Unit.active.is_(True), Unit.qa_status == "APPROVED"))
        )
        out: list[IndexedUnit] = []
        for unit in units:
            item = IndexedUnit(
                unit_id=unit.id,
                canonical_name=unit.canonical_name,
                normalized_key=unit.normalized_key,
                ascii_key=unit.ascii_key,
                organization_type=unit.organization_type,
                coverage_group=unit.coverage_group,
                source_id=unit.source_id,
                valid_from=unit.valid_from,
                valid_to=unit.valid_to,
                active=unit.active,
            )
            for n in self.db.scalars(
                select(UnitName).where(UnitName.unit_id == unit.id, UnitName.qa_status == "APPROVED")
            ):
                item.aliases.append((n.name, n.normalized_key, n.valid_from, n.valid_to, n.ascii_key))
            for c in self.db.scalars(
                select(UnitCode).where(UnitCode.unit_id == unit.id, UnitCode.qa_status == "APPROVED")
            ):
                item.codes.append((c.code, c.namespace, c.valid_from, c.valid_to))
            out.append(item)
        return out

    def _index(self) -> tuple[RegistryVersion | None, list[IndexedUnit]]:
        rv = self._published_version_row()
        return rv, self._load_snapshot_index(rv) if rv else self._load_legacy_index()

    def _resolve_trusted_unit_id(self, unit_id: str, as_of: date | None) -> Resolution:
        """Resolve an already-trusted FK without rebuilding the text-search index."""
        rv = self._published_version_row()
        version = rv.version if rv else None
        if rv:
            row = self.db.get(
                RegistrySnapshotUnit,
                {"registry_version_id": rv.id, "unit_id": unit_id},
            )
            if row is None or not row.active or not _active_on(as_of, row.valid_from, row.valid_to):
                return Resolution(
                    "NOT_FOUND", "UNKNOWN", None, None, "TRUSTED_UNIT_ID_NOT_FOUND",
                    None, None, [], version, decision_confidence=0.0
                )
            return Resolution(
                "MATCHED", row.organization_type, row.unit_id, row.canonical_name,
                "TRUSTED_UNIT_ID", 100.0, 100.0, [], version,
                self._source_kind(row.source_id), "NOT_REQUIRED", 1.0, row.coverage_group
            )

        unit = self.db.get(Unit, unit_id)
        if (
            unit is None
            or not unit.active
            or unit.qa_status != "APPROVED"
            or not _active_on(as_of, unit.valid_from, unit.valid_to)
        ):
            return Resolution(
                "NOT_FOUND", "UNKNOWN", None, None, "TRUSTED_UNIT_ID_NOT_FOUND",
                None, None, [], None, decision_confidence=0.0
            )
        return Resolution(
            "MATCHED", unit.organization_type, unit.id, unit.canonical_name,
            "TRUSTED_UNIT_ID", 100.0, 100.0, [], None,
            self._source_kind(unit.source_id), "NOT_REQUIRED", 1.0, unit.coverage_group
        )

    def _resolve_code(self, units: list[IndexedUnit], unit_code: str | None, as_of: date | None) -> IndexedUnit | None:
        if not unit_code:
            return None
        target = unit_code.strip().casefold()
        for unit in units:
            if not _active_on(as_of, unit.valid_from, unit.valid_to):
                continue
            for code, _namespace, start, end in unit.codes:
                if code.casefold() == target and _active_on(as_of, start, end):
                    return unit
        return None

    def _resolve_exact_name(self, units: list[IndexedUnit], unit_name: str | None, as_of: date | None) -> tuple[IndexedUnit | None, str | None]:
        """Resolve an exact canonical/alias name.

        Several organizations can legitimately own a unit with the same name
        (e.g. "Cục Hậu cần" exists under both BCA and BQP). Returning the first
        row scanned would silently invent a force attribution, so an exact name
        that maps to more than one organization is reported as ambiguous instead.
        """
        if not unit_name:
            return None, None
        key = normalize_text(unit_name)

        canonical = [
            unit
            for unit in units
            if _active_on(as_of, unit.valid_from, unit.valid_to) and unit.normalized_key == key
        ]
        if canonical:
            return self._single_or_ambiguous(canonical, "CANONICAL_EXACT")

        aliased = [
            unit
            for unit in units
            if _active_on(as_of, unit.valid_from, unit.valid_to)
            and any(
                alias_key == key and _active_on(as_of, start, end)
                for _name, alias_key, start, end, _alias_ascii in unit.aliases
            )
        ]
        if aliased:
            return self._single_or_ambiguous(aliased, "APPROVED_ALIAS")

        # Diacritic-folded fallback. Deliberately the last exact-match tier: an accented
        # canonical or alias hit above always wins, so folding only ever rescues input
        # that would otherwise reach fuzzy matching or NOT_FOUND.
        folded = ascii_key(unit_name)
        if folded:
            folded_canonical = [
                unit
                for unit in units
                if _active_on(as_of, unit.valid_from, unit.valid_to) and unit.folded_key() == folded
            ]
            if folded_canonical:
                return self._single_or_ambiguous(folded_canonical, "ASCII_FOLDED")

            folded_alias = [
                unit
                for unit in units
                if _active_on(as_of, unit.valid_from, unit.valid_to)
                and any(
                    (alias_ascii or ascii_key(alias_name)) == folded and _active_on(as_of, start, end)
                    for alias_name, _alias_key, start, end, alias_ascii in unit.aliases
                )
            ]
            if folded_alias:
                return self._single_or_ambiguous(folded_alias, "ASCII_FOLDED_ALIAS")
        return None, None

    @staticmethod
    def _single_or_ambiguous(matches: list[IndexedUnit], method: str) -> tuple[IndexedUnit | None, str | None]:
        if len(matches) == 1:
            return matches[0], method
        if len({unit.organization_type for unit in matches}) == 1 and len({unit.unit_id for unit in matches}) == 1:
            return matches[0], method
        # Same spelling, different organizations: the name alone cannot identify the unit.
        return None, "EXACT_NAME_AMBIGUOUS"

    def _fuzzy_scores(self, units: list[IndexedUnit], unit_name: str, as_of: date | None) -> dict[str, float]:
        key = normalize_text(unit_name)
        scores: dict[str, float] = {}
        for unit in units:
            if not _active_on(as_of, unit.valid_from, unit.valid_to):
                continue
            best = float(fuzz.WRatio(key, unit.normalized_key))
            for _name, alias_key, start, end, _alias_ascii in unit.aliases:
                if _active_on(as_of, start, end):
                    best = max(best, float(fuzz.WRatio(key, alias_key)))
            scores[unit.unit_id] = best
        return scores

    def _bm25_scores(self, units: list[IndexedUnit], unit_name: str, as_of: date | None) -> dict[str, float]:
        query = _tokenize(unit_name)
        if not query:
            return {}
        docs: dict[str, list[str]] = {}
        for unit in units:
            if not _active_on(as_of, unit.valid_from, unit.valid_to):
                continue
            text = unit.canonical_name + " " + " ".join(
                alias[0] for alias in unit.aliases if _active_on(as_of, alias[2], alias[3])
            )
            docs[unit.unit_id] = _tokenize(text)
        n = len(docs)
        if not n:
            return {}
        avgdl = sum(len(x) for x in docs.values()) / n or 1.0
        df: dict[str, int] = {}
        for tokens in docs.values():
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        raw: dict[str, float] = {}
        k1, b = 1.5, 0.75
        for uid, tokens in docs.items():
            score = 0.0
            dl = len(tokens) or 1
            for term in query:
                tf = tokens.count(term)
                if not tf:
                    continue
                idf = math.log(1.0 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
                score += idf * (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * dl / avgdl))
            raw[uid] = score
        max_score = max(raw.values(), default=0.0)
        if max_score <= 0:
            return {uid: 0.0 for uid in raw}
        return {uid: value / max_score for uid, value in raw.items()}

    def _semantic_scores(self, version_key: str, units: list[IndexedUnit], unit_name: str, as_of: date | None) -> dict[str, float]:
        if not self.settings.embedding_enabled:
            return {}
        active_units = [u for u in units if _active_on(as_of, u.valid_from, u.valid_to)]
        if not active_units:
            return {}
        try:
            from sentence_transformers import SentenceTransformer

            with _EMBED_LOCK:
                model = _EMBED_MODELS.get(self.settings.embedding_model_name)
                if model is None:
                    model = SentenceTransformer(
                        self.settings.embedding_model_name,
                        local_files_only=self.settings.embedding_local_files_only,
                    )
                    _EMBED_MODELS[self.settings.embedding_model_name] = model
                cached = _EMBED_CACHE.get(version_key)
                ids = [u.unit_id for u in active_units]
                if not cached or cached[0] != ids:
                    corpus = [u.canonical_name for u in active_units]
                    matrix = np.asarray(model.encode(corpus, normalize_embeddings=True, show_progress_bar=False))
                    _EMBED_CACHE[version_key] = (ids, matrix)
                else:
                    matrix = cached[1]
            query = np.asarray(model.encode([unit_name], normalize_embeddings=True, show_progress_bar=False))[0]
            similarities = matrix @ query
            return {uid: float(max(0.0, min(1.0, sim))) for uid, sim in zip(ids, similarities, strict=True)}
        except Exception as exc:
            logger.warning(
                "semantic_resolver_unavailable",
                extra={"event": {"error_type": type(exc).__name__}},
            )
            return {}

    def _rank(self, rv: RegistryVersion | None, units: list[IndexedUnit], unit_name: str, as_of: date | None) -> list[dict]:
        fuzzy_scores = self._fuzzy_scores(units, unit_name, as_of)
        bm25_scores = self._bm25_scores(units, unit_name, as_of)
        # Avoid loading a transformer unless lexical/fuzzy evidence is not already decisive.
        fuzzy_sorted = sorted(fuzzy_scores.values(), reverse=True)
        lexical_decisive = bool(
            fuzzy_sorted
            and fuzzy_sorted[0] >= self.settings.resolver_fuzzy_threshold + 3
            and (fuzzy_sorted[0] - (fuzzy_sorted[1] if len(fuzzy_sorted) > 1 else 0.0)) >= self.settings.resolver_margin_threshold + 4
        )
        semantic_scores = {} if lexical_decisive else self._semantic_scores(rv.id if rv else "legacy", units, unit_name, as_of)
        by_id = {u.unit_id: u for u in units}
        rows = []
        for uid, unit in by_id.items():
            if not _active_on(as_of, unit.valid_from, unit.valid_to):
                continue
            f = fuzzy_scores.get(uid, 0.0)
            b = bm25_scores.get(uid, 0.0)
            sem = semantic_scores.get(uid, 0.0)
            combined = 0.65 * (f / 100.0) + 0.20 * b + 0.15 * sem
            rows.append(
                {
                    "unit": unit,
                    "fuzzy": f,
                    "bm25": b,
                    "semantic": sem,
                    "combined": combined,
                }
            )
        rows.sort(key=lambda x: (x["combined"], x["fuzzy"]), reverse=True)
        return rows[: self.settings.resolver_candidate_limit]

    def _candidates_payload(self, ranked: list[dict]) -> list[dict]:
        return [
            {
                "unit_id": row["unit"].unit_id,
                "canonical_name": row["unit"].canonical_name,
                "organization_type": row["unit"].organization_type,
                "coverage_group": row["unit"].coverage_group,
                "score": round(row["combined"] * 100.0, 2),
                "fuzzy_score": round(row["fuzzy"], 2),
                "bm25_score": round(row["bm25"], 4),
                "semantic_score": round(row["semantic"], 4),
            }
            for row in ranked
        ]

    def resolve(
        self,
        unit_name: str | None = None,
        unit_code: str | None = None,
        as_of_date: date | None = None,
        unit_id: str | None = None,
    ) -> Resolution:
        if unit_id:
            return self._resolve_trusted_unit_id(unit_id, as_of_date)
        rv, units = self._index()
        version = rv.version if rv else None
        code_unit = self._resolve_code(units, unit_code, as_of_date)
        name_unit, name_method = self._resolve_exact_name(units, unit_name, as_of_date)

        # An exact name owned by several organizations identifies no single unit. A trusted
        # code still disambiguates it, so only abstain when the code gives us nothing.
        if name_method == "EXACT_NAME_AMBIGUOUS" and not code_unit:
            key = normalize_text(unit_name or "")
            folded = ascii_key(unit_name or "")
            tied = [
                unit
                for unit in units
                if _active_on(as_of_date, unit.valid_from, unit.valid_to)
                and (
                    unit.normalized_key == key
                    or unit.folded_key() == folded
                    or any(
                        (alias_key == key or (alias_ascii or ascii_key(alias_name)) == folded)
                        and _active_on(as_of_date, start, end)
                        for alias_name, alias_key, start, end, alias_ascii in unit.aliases
                    )
                )
            ]
            return Resolution(
                "AMBIGUOUS",
                "UNKNOWN",
                None,
                None,
                "EXACT_NAME_AMBIGUOUS",
                100.0,
                0.0,
                [
                    {
                        "unit_id": unit.unit_id,
                        "canonical_name": unit.canonical_name,
                        "organization_type": unit.organization_type,
                        "coverage_group": unit.coverage_group,
                        "score": 100.0,
                        "evidence": "EXACT_NAME_MULTI_ORG",
                    }
                    for unit in tied
                ],
                version,
                "PROVIDED",
                "NOT_REQUIRED",
                0.0,
            )

        if code_unit and name_unit and code_unit.unit_id != name_unit.unit_id:
            candidates = [
                {
                    "unit_id": code_unit.unit_id,
                    "canonical_name": code_unit.canonical_name,
                    "organization_type": code_unit.organization_type,
                    "coverage_group": code_unit.coverage_group,
                    "score": 100.0,
                    "evidence": "TRUSTED_CODE",
                },
                {
                    "unit_id": name_unit.unit_id,
                    "canonical_name": name_unit.canonical_name,
                    "organization_type": name_unit.organization_type,
                    "coverage_group": name_unit.coverage_group,
                    "score": 100.0,
                    "evidence": name_method,
                },
            ]
            return Resolution("CONFLICT", "UNKNOWN", None, None, "CODE_NAME_CONFLICT", 100.0, 0.0, candidates, version, "PROVIDED", "NOT_REQUIRED", 0.0)

        if code_unit:
            # Detect a strong contradictory name even if the name is not an exact alias.
            if unit_name and not name_unit:
                ranked = self._rank(rv, units, unit_name, as_of_date)
                if ranked:
                    top = ranked[0]
                    second = ranked[1] if len(ranked) > 1 else None
                    margin = (top["combined"] - (second["combined"] if second else 0.0)) * 100.0
                    if top["unit"].unit_id != code_unit.unit_id and top["fuzzy"] >= 97.0 and margin >= 10.0:
                        return Resolution(
                            "CONFLICT",
                            "UNKNOWN",
                            None,
                            None,
                            "CODE_STRONG_NAME_CONFLICT",
                            top["combined"] * 100.0,
                            margin,
                            self._candidates_payload(ranked),
                            version,
                            "PROVIDED",
                            "NOT_REQUIRED",
                            0.0,
                        )
            return Resolution(
                "MATCHED",
                code_unit.organization_type,
                code_unit.unit_id,
                code_unit.canonical_name,
                "TRUSTED_CODE",
                100.0,
                100.0,
                [],
                version,
                self._source_kind(code_unit.source_id),
                "NOT_REQUIRED",
                1.0,
                code_unit.coverage_group,
            )

        if name_unit:
            # Evidence strength, strongest first: canonical spelling, then a human-approved
            # alias, then a diacritic-folded match (machine-derived, so it ranks lowest).
            name_match_scores = {
                "CANONICAL_EXACT": 100.0,
                "APPROVED_ALIAS": 99.0,
                "ASCII_FOLDED": 97.0,
                "ASCII_FOLDED_ALIAS": 96.0,
            }
            score = name_match_scores.get(name_method or "", 99.0)
            return Resolution(
                "MATCHED",
                name_unit.organization_type,
                name_unit.unit_id,
                name_unit.canonical_name,
                name_method,
                score,
                score,
                [],
                version,
                self._source_kind(name_unit.source_id),
                "NOT_REQUIRED",
                1.0,
                name_unit.coverage_group,
            )

        if not unit_name:
            return Resolution("NOT_FOUND", "UNKNOWN", None, None, None, None, None, [], version, decision_confidence=0.0)

        ranked = self._rank(rv, units, unit_name, as_of_date)
        candidates = self._candidates_payload(ranked)
        if not ranked:
            return Resolution("NOT_FOUND", "UNKNOWN", None, None, None, None, None, [], version, decision_confidence=0.0)

        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        combined_score = top["combined"] * 100.0
        margin = (top["combined"] - (second["combined"] if second else 0.0)) * 100.0
        calibration = self.calibrator.predict(
            fuzzy=top["fuzzy"],
            margin=margin,
            bm25=top["bm25"],
            semantic=top["semantic"],
        )
        calibration_status = f"{calibration.method}:{calibration.version}"
        strong = top["fuzzy"] >= self.settings.resolver_fuzzy_threshold and margin >= self.settings.resolver_margin_threshold
        calibrated_ok = calibration.available and calibration.probability >= self.settings.resolver_calibrated_accept_threshold
        calibration_requirement_ok = calibrated_ok or not self.settings.resolver_require_calibration_for_fuzzy_autoaccept

        if strong and calibration_requirement_ok:
            unit = top["unit"]
            return Resolution(
                "MATCHED",
                unit.organization_type,
                unit.unit_id,
                unit.canonical_name,
                "HYBRID_FUZZY_BM25_SEMANTIC",
                combined_score,
                margin,
                candidates,
                version,
                self._source_kind(unit.source_id),
                calibration_status,
                calibration.probability,
                unit.coverage_group,
            )

        if (
            self.settings.resolver_allow_semantic_autoaccept
            and top["semantic"] >= self.settings.resolver_semantic_threshold
            and (top["semantic"] - (second["semantic"] if second else 0.0)) >= self.settings.resolver_semantic_margin_threshold
            and calibrated_ok
        ):
            unit = top["unit"]
            return Resolution(
                "MATCHED",
                unit.organization_type,
                unit.unit_id,
                unit.canonical_name,
                "SEMANTIC_CALIBRATED",
                combined_score,
                margin,
                candidates,
                version,
                self._source_kind(unit.source_id),
                calibration_status,
                calibration.probability,
                unit.coverage_group,
            )

        # Unknown remains UNKNOWN; NEVER map NOT_FOUND to OTHER without positive registry evidence.
        if combined_score >= max(50.0, self.settings.resolver_fuzzy_threshold - 15.0):
            return Resolution(
                "AMBIGUOUS",
                "UNKNOWN",
                None,
                None,
                "HYBRID_RANKING",
                combined_score,
                margin,
                candidates,
                version,
                "PROVIDED",
                calibration_status,
                calibration.probability,
            )
        return Resolution(
            "NOT_FOUND",
            "UNKNOWN",
            None,
            None,
            "HYBRID_RANKING",
            combined_score,
            margin,
            candidates,
            version,
            "PROVIDED",
            calibration_status,
            calibration.probability,
        )
