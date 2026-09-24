from __future__ import annotations

import csv
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import inspect, select

# Locate the repo root when running this script directly from a host checkout
# (apps/backend/scripts/seed.py -> repo root is 3 levels up). Inside the Docker image the
# file lives at /app/scripts/seed.py, which has no such ancestor, and `cabqp` is already
# installed via `pip install -e .`, so path injection is unnecessary there.
_here = Path(__file__).resolve()
_candidate_root = _here.parents[3] if len(_here.parents) > 3 else None
if _candidate_root is not None and (_candidate_root / "apps/backend/src").is_dir():
    ROOT: Path | None = _candidate_root
    sys.path.insert(0, str(ROOT / "apps/backend/src"))
else:
    ROOT = None

from cabqp.shared.db import SessionLocal, engine  # noqa: E402
from cabqp.shared.models import (  # noqa: E402
    PolicyRule,
    RegistrySnapshotUnit,
    RegistryVersion,
    Source,
    Unit,
    utcnow,
)
from cabqp.shared.normalization import ascii_key, normalize_text  # noqa: E402
from cabqp.shared.settings import get_settings  # noqa: E402


def require_migrated_schema() -> None:
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables or "units" not in tables:
        raise RuntimeError("Database schema is not migrated. Run `alembic upgrade head` before seeding.")


def resolve_registry_source() -> tuple[Path, str]:
    """Locate the registry CSV to seed from.

    Preference order: explicit REGISTRY_SEED_PATH, the mounted curated registry,
    then the 43-unit bootstrap baseline that ships inside the image.
    """
    candidates: list[Path] = []
    override = os.getenv("REGISTRY_SEED_PATH")
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/app/registry/master_units_registry.csv"))
    if ROOT is not None:
        candidates.extend(
            [
                ROOT / "artifacts/registry/published/master_units_registry.csv",
                ROOT / "datasets/curated/master_units_baseline43.csv",
            ]
        )
    candidates.append(Path("/app/bootstrap/master_units_baseline43.csv"))
    for candidate in candidates:
        if candidate.exists():
            kind = "BASELINE" if "baseline43" in candidate.name else "CURATED_REGISTRY"
            return candidate, kind
    raise RuntimeError(f"Seed registry file not found. Looked in: {[str(c) for c in candidates]}")


def main() -> None:
    settings = get_settings()
    if settings.is_production and not settings.seed_allow_production:
        raise RuntimeError("Refusing to seed production. Set SEED_ALLOW_PRODUCTION=true only for an approved bootstrap.")
    require_migrated_schema()

    db = SessionLocal()
    try:
        path, source_kind = resolve_registry_source()
        version = "2026.09-v2-baseline43" if source_kind == "BASELINE" else "2026.09-curated-registry"
        rv = db.scalar(select(RegistryVersion).where(RegistryVersion.version == version))
        if not rv:
            current = db.scalar(select(RegistryVersion).where(RegistryVersion.status == "PUBLISHED"))
            if current:
                current.status = "DEPRECATED"
            rv = RegistryVersion(
                version=version,
                status="PUBLISHED",
                published_at=utcnow(),
                notes=f"Seed from {path}",
            )
            db.add(rv)
            db.flush()

        # Evidence columns in the curated registry hold very large JSON blobs.
        csv.field_size_limit(2_000_000)
        seeded = 0
        skipped_not_approved = 0
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                # Honour the QA decision recorded in the source data. Seeding must never
                # promote a unit that a human has not approved.
                if (row.get("qa_status") or "").strip().upper() != "APPROVED":
                    skipped_not_approved += 1
                    continue
                seeded += 1
                unit = db.get(Unit, row["unit_id"])
                if not unit:
                    src = Source(
                        authority="OFFICIAL_BASELINE",
                        url=row.get("source_url", ""),
                        checksum=row.get("source_sha256") or None,
                        source_kind="OFFICIAL",
                        retrieved_at=utcnow(),
                    )
                    db.add(src)
                    db.flush()
                    unit = Unit(
                        id=row["unit_id"],
                        canonical_name=row["canonical_name"],
                        normalized_key=row.get("normalized_key") or normalize_text(row["canonical_name"]),
                        # The ingestion pipeline already ships ascii_key; recompute only if absent
                        # so the runtime value can never diverge from the published registry.
                        ascii_key=row.get("ascii_key") or ascii_key(row["canonical_name"]),
                        organization_type=row["organization_type"],
                        unit_level=row.get("unit_level") or None,
                        coverage_group=row.get("coverage_group") or None,
                        qa_status=(row.get("qa_status") or "APPROVED").strip().upper(),
                        registry_version_id=rv.id,
                        source_id=src.id,
                        active=True,
                    )
                    db.add(unit)
                    db.flush()
                snap = db.get(
                    RegistrySnapshotUnit,
                    {"registry_version_id": rv.id, "unit_id": unit.id},
                )
                if not snap:
                    db.add(
                        RegistrySnapshotUnit(
                            registry_version_id=rv.id,
                            unit_id=unit.id,
                            canonical_name=unit.canonical_name,
                            normalized_key=unit.normalized_key,
                            ascii_key=unit.ascii_key,
                            organization_type=unit.organization_type,
                            unit_level=unit.unit_level,
                            coverage_group=unit.coverage_group,
                            parent_unit_id=unit.parent_unit_id,
                            valid_from=unit.valid_from,
                            valid_to=unit.valid_to,
                            source_id=unit.source_id,
                            active=unit.active,
                        )
                    )

        policies = [
            PolicyRule(
                id="BHXH-ND157-2025",
                policy_type="BHXH_BAT_BUOC",
                subject_groups=["QUAN_NHAN", "CAND", "CO_YEU_HUONG_LUONG_NHU_QUAN_NHAN"],
                required_fields=[],
                rule_expression={"scope_only": True},
                effective_from=date(2025, 7, 1),
                policy_version="official-scope-2026.09",
                source_kind="OFFICIAL",
                source_ref="Nghị định 157/2025/NĐ-CP",
            ),
            PolicyRule(
                id="BHXH-TT90-2025-BQP",
                policy_type="BHXH_BQP",
                subject_groups=["QUAN_NHAN", "CO_YEU_HUONG_LUONG_NHU_QUAN_NHAN"],
                required_fields=[],
                rule_expression={"scope_only": True},
                effective_from=date(2025, 1, 1),
                policy_version="official-scope-2026.09",
                source_kind="OFFICIAL",
                source_ref="Thông tư 90/2025/TT-BQP",
            ),
            PolicyRule(
                id="BHXH-TT88-2025-BCA",
                policy_type="BHXH_BCA",
                subject_groups=["CAND"],
                required_fields=[],
                rule_expression={"scope_only": True},
                effective_from=date(2025, 1, 1),
                policy_version="official-scope-2026.09",
                source_kind="OFFICIAL",
                source_ref="Thông tư 88/2025/TT-BCA",
            ),
        ]
        for policy in policies:
            if not db.get(PolicyRule, policy.id):
                db.add(policy)
        db.commit()
        print(
            f"seeded {seeded} approved units from {path} "
            f"(version={version}, skipped_not_approved={skipped_not_approved}) "
            "+ official-scope policy metadata"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
