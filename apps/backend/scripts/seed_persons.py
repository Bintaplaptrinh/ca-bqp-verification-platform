from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from sqlalchemy import func, inspect, select

_here = Path(__file__).resolve()
_candidate_root = _here.parents[3] if len(_here.parents) > 3 else None
if _candidate_root is not None and (_candidate_root / "apps/backend/src").is_dir():
    ROOT: Path | None = _candidate_root
    sys.path.insert(0, str(ROOT / "apps/backend/src"))
else:
    ROOT = None

from cabqp.shared.db import SessionLocal, engine  # noqa: E402
from cabqp.shared.models import (  # noqa: E402
    Person,
    PersonCode,
    PersonCodeSnapshot,
    PersonRegistrySnapshot,
    PersonRegistryVersion,
    Unit,
    utcnow,
)
from cabqp.shared.normalization import ascii_key, normalize_text  # noqa: E402
from cabqp.shared.settings import get_settings  # noqa: E402

GROUP_MAP = {
    "CAND_NCO": "CAND",
    "CAND_OFFICER": "CAND",
    "MILITARY_OFFICER": "QUAN_NHAN",
    "PROFESSIONAL_MILITARY": "QUAN_NHAN",
}
EMPLOYMENT_STATUSES = {"ACTIVE", "CONTRACT", "TEMPORARY", "INACTIVE", "RETIRED", "UNKNOWN"}
SYNTHETIC_WELFARE_COLUMNS = (
    "synthetic_service_years",
    "synthetic_pay_grade",
    "synthetic_pay_coefficient",
    "synthetic_base_salary_million_vnd",
    "synthetic_allowance_million_vnd",
    "synthetic_total_income_million_vnd",
)


def require_migrated_schema() -> None:
    tables = set(inspect(engine).get_table_names())
    required = {"alembic_version", "units", "persons", "person_registry_versions"}
    missing = required - tables
    if missing:
        raise RuntimeError(
            f"Database schema is not migrated for person registry. Missing: {sorted(missing)}. "
            "Run `alembic upgrade head` first."
        )


def resolve_person_source() -> Path:
    candidates: list[Path] = []
    override = os.getenv("PERSON_ROSTER_SEED_PATH")
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/app/synthetic/synthetic_records.csv"))
    if ROOT is not None:
        candidates.append(ROOT / "artifacts/synthetic/synthetic_records.csv")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Synthetic person roster not found. Looked in: {[str(x) for x in candidates]}")


def _birth_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if 1900 <= value <= 2200 else None


def main() -> None:
    settings = get_settings()
    if settings.is_production and not settings.seed_allow_production:
        raise RuntimeError(
            "Refusing to seed synthetic persons into production. "
            "Use an approved real-data ingestion flow instead."
        )
    require_migrated_schema()
    path = resolve_person_source()

    db = SessionLocal()
    try:
        version_name = "2026.09-synthetic-person-roster-v1"
        rv = db.scalar(
            select(PersonRegistryVersion).where(PersonRegistryVersion.version == version_name)
        )
        if rv:
            if rv.status != "PUBLISHED":
                raise RuntimeError(
                    f"Synthetic bootstrap version {version_name} already exists with status={rv.status}; "
                    "refusing to mutate/relabel an existing version."
                )
            existing_snapshots = db.scalar(
                select(func.count()).select_from(PersonRegistrySnapshot).where(
                    PersonRegistrySnapshot.registry_version_id == rv.id
                )
            ) or 0
            if existing_snapshots:
                print(
                    "person roster seed already applied "
                    f"(version={version_name}, snapshot_persons={existing_snapshots}); no mutation performed"
                )
                return
        else:
            current = db.scalar(
                select(PersonRegistryVersion).where(PersonRegistryVersion.status == "PUBLISHED")
            )
            if current:
                current.status = "DEPRECATED"
            rv = PersonRegistryVersion(
                version=version_name,
                status="PUBLISHED",
                published_at=utcnow(),
                notes=f"Synthetic demo person roster seeded from {path}",
            )
            db.add(rv)
            db.flush()

        csv.field_size_limit(2_000_000)
        seeded = 0
        existing = 0
        skipped_unit_not_found = 0
        skipped_unit_untrusted = 0
        existing_id_conflict = 0
        group_hint_unmapped = 0
        invalid_employment = 0
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                # This bootstrap imports fabricated data only. APPROVED here means
                # "usable by resolver", never "verified real-world person". The
                # permanent SYNTHETIC_DEMO marker is the authority boundary.
                if (row.get("source_kind") or "").strip().upper() != "SYNTHETIC_DEMO":
                    continue
                unit_id = (row.get("canonical_unit_id") or "").strip()
                unit = db.get(Unit, unit_id)
                if not unit:
                    skipped_unit_not_found += 1
                    continue
                if not unit.active or unit.qa_status != "APPROVED":
                    skipped_unit_untrusted += 1
                    continue

                person_id = (row.get("subject_id") or "").strip()
                if not person_id:
                    continue
                person = db.get(Person, person_id)
                if person:
                    if person.source_kind != "SYNTHETIC_DEMO":
                        existing_id_conflict += 1
                        continue
                    existing += 1
                else:
                    raw_group = (row.get("subject_group") or "").strip().upper()
                    group_hint = GROUP_MAP.get(raw_group)
                    if raw_group and group_hint is None:
                        group_hint_unmapped += 1
                    employment = (row.get("employment_status") or "UNKNOWN").strip().upper()
                    if employment not in EMPLOYMENT_STATUSES:
                        employment = "UNKNOWN"
                        invalid_employment += 1
                    welfare = {
                        col: row.get(col, "")
                        for col in SYNTHETIC_WELFARE_COLUMNS
                        if row.get(col, "") != ""
                    }
                    person = Person(
                        id=person_id,
                        full_name=(row.get("full_name") or "").strip(),
                        normalized_key=normalize_text(row.get("full_name") or ""),
                        ascii_key=ascii_key(row.get("full_name") or ""),
                        birth_year=_birth_year(row.get("birth_year")),
                        canonical_unit_id=unit_id,
                        subject_group_hint=group_hint,
                        employment_status=employment,
                        qa_status="APPROVED",
                        registry_version_id=rv.id,
                        source_id=None,
                        source_kind="SYNTHETIC_DEMO",
                        active=True,
                        synthetic_welfare_facts=welfare or None,
                    )
                    db.add(person)
                    db.flush()
                    seeded += 1

                personal_code = (row.get("personal_code") or "").strip()
                if personal_code:
                    existing_code = db.scalar(
                        select(PersonCode).where(
                            PersonCode.code == personal_code,
                            PersonCode.namespace == "SYNTHETIC",
                        )
                    )
                    if existing_code and existing_code.person_id != person.id:
                        raise RuntimeError(
                            f"Synthetic personal_code collision: {personal_code} belongs to "
                            f"{existing_code.person_id}, not {person.id}"
                        )
                    if not existing_code:
                        db.add(
                            PersonCode(
                                person_id=person.id,
                                code=personal_code,
                                code_type="PERSON_CODE",
                                namespace="SYNTHETIC",
                                qa_status="APPROVED",
                            )
                        )
                        db.flush()

                snap = db.get(
                    PersonRegistrySnapshot,
                    {"registry_version_id": rv.id, "person_id": person.id},
                )
                if not snap:
                    db.add(
                        PersonRegistrySnapshot(
                            registry_version_id=rv.id,
                            person_id=person.id,
                            full_name=person.full_name,
                            normalized_key=person.normalized_key,
                            ascii_key=person.ascii_key,
                            birth_year=person.birth_year,
                            canonical_unit_id=person.canonical_unit_id,
                            subject_group_hint=person.subject_group_hint,
                            employment_status=person.employment_status,
                            source_id=person.source_id,
                            source_kind=person.source_kind,
                            active=person.active,
                            valid_from=person.valid_from,
                            valid_to=person.valid_to,
                            synthetic_welfare_facts=person.synthetic_welfare_facts,
                        )
                    )
                codes = list(
                    db.scalars(
                        select(PersonCode).where(
                            PersonCode.person_id == person.id,
                            PersonCode.qa_status == "APPROVED",
                        )
                    )
                )
                for code in codes:
                    code_snap = db.get(
                        PersonCodeSnapshot,
                        {"registry_version_id": rv.id, "person_code_id": code.id},
                    )
                    if not code_snap:
                        db.add(
                            PersonCodeSnapshot(
                                registry_version_id=rv.id,
                                person_code_id=code.id,
                                person_id=person.id,
                                code=code.code,
                                code_type=code.code_type,
                                namespace=code.namespace,
                                source_id=code.source_id,
                            )
                        )

        db.commit()
        print(
            "person roster seed complete "
            f"(version={version_name}, seeded={seeded}, existing={existing}, "
            f"skipped_unit_not_found={skipped_unit_not_found}, "
            f"skipped_unit_untrusted={skipped_unit_untrusted}, "
            f"existing_id_conflict={existing_id_conflict}, "
            f"group_hint_unmapped={group_hint_unmapped}, invalid_employment={invalid_employment})"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
