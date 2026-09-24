"""Diacritic-folded resolution regressions.

Vietnamese unit names are routinely typed without diacritics. Folding is added as the
last exact-match tier: an accented canonical or approved-alias hit must still win, and
folding must not quietly merge units that belong to different organizations.
"""
from __future__ import annotations

import importlib.util
import unicodedata
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cabqp.modules.resolution.service import Resolver
from cabqp.shared.db import Base
from cabqp.shared.models import Source, Unit, UnitName
from cabqp.shared.normalization import ascii_key, normalize_text

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0003_ascii_folded_resolution.py"
)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_unit(db: Session, *, uid: str, name: str, org: str, alias: str | None = None) -> Unit:
    source = Source(authority="TEST", url=f"https://example.invalid/{uid}", source_kind="OFFICIAL")
    db.add(source)
    db.flush()
    unit = Unit(
        id=uid,
        canonical_name=name,
        normalized_key=normalize_text(name),
        ascii_key=ascii_key(name),
        organization_type=org,
        qa_status="APPROVED",
        active=True,
        source_id=source.id,
    )
    db.add(unit)
    db.flush()
    if alias:
        db.add(
            UnitName(
                unit_id=uid,
                name=alias,
                normalized_key=normalize_text(alias),
                ascii_key=ascii_key(alias),
                name_type="ALIAS",
                qa_status="APPROVED",
                source_id=source.id,
            )
        )
        db.flush()
    return unit


def test_name_without_diacritics_resolves(db):
    seed_unit(db, uid="u_kt", name="Cục Kỹ thuật", org="BQP")
    out = Resolver(db).resolve(unit_name="Cuc Ky thuat")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_kt"
    assert out.match_method == "ASCII_FOLDED"


def test_accented_spelling_still_outranks_folded_match(db):
    seed_unit(db, uid="u_kt", name="Cục Kỹ thuật", org="BQP")
    exact = Resolver(db).resolve(unit_name="Cục Kỹ thuật")
    folded = Resolver(db).resolve(unit_name="Cuc Ky thuat")
    assert exact.match_method == "CANONICAL_EXACT"
    assert folded.match_method == "ASCII_FOLDED"
    # Folding is machine-derived evidence and must score below the canonical spelling.
    assert exact.score is not None and folded.score is not None
    assert exact.score > folded.score


def test_approved_alias_beats_folded_canonical(db):
    """An accented alias hit is stronger evidence than folding another unit's name."""
    seed_unit(db, uid="u_108", name="Bệnh viện Trung ương Quân đội 108", org="BQP", alias="Bệnh viện 108")
    out = Resolver(db).resolve(unit_name="Bệnh viện 108")
    assert out.match_method == "APPROVED_ALIAS"


def test_alias_without_diacritics_resolves(db):
    seed_unit(db, uid="u_108", name="Bệnh viện Trung ương Quân đội 108", org="BQP", alias="Bệnh viện 108")
    out = Resolver(db).resolve(unit_name="Benh vien 108")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_108"
    assert out.match_method == "ASCII_FOLDED_ALIAS"


def test_folding_does_not_merge_units_from_different_organizations(db):
    """Folding widens matching, so the multi-org guard must hold for folded input too."""
    seed_unit(db, uid="u_bca", name="Cục Đối ngoại", org="BCA")
    seed_unit(db, uid="u_bqp", name="Cục Đối ngoại", org="BQP")
    out = Resolver(db).resolve(unit_name="Cuc Doi ngoai")
    assert out.status == "AMBIGUOUS"
    assert out.organization_type == "UNKNOWN"
    assert out.unit_id is None
    assert out.decision_confidence == 0.0
    assert {c["organization_type"] for c in out.candidates} == {"BCA", "BQP"}


def test_folding_does_not_merge_distinct_communes_in_the_same_force(db):
    """Distinct places can collide once diacritics are dropped.

    "Phú Hữu" and "Phú Hựu" are different communes, as are "Ba Tô"/"Ba Tơ" and
    "Bình Thành"/"Bình Thạnh". They share an organization, so the multi-org check alone
    would not catch them: picking either one would attach a subject to the wrong commune.
    """
    seed_unit(db, uid="u_huu", name="Công an xã Phú Hữu", org="BCA")
    seed_unit(db, uid="u_huu2", name="Công an xã Phú Hựu", org="BCA")

    folded = Resolver(db).resolve(unit_name="Cong an xa Phu Huu")
    assert folded.status == "AMBIGUOUS"
    assert folded.unit_id is None
    assert folded.decision_confidence == 0.0

    # The accented spelling is unambiguous and must still resolve exactly.
    exact = Resolver(db).resolve(unit_name="Công an xã Phú Hựu")
    assert exact.status == "MATCHED"
    assert exact.unit_id == "u_huu2"
    assert exact.match_method == "CANONICAL_EXACT"


def test_unknown_name_is_not_rescued_by_folding(db):
    """Folding must not turn an unrelated name into a match."""
    seed_unit(db, uid="u_kt", name="Cục Kỹ thuật", org="BQP")
    out = Resolver(db).resolve(unit_name="Don vi hoan toan khong ton tai")
    assert out.status in {"NOT_FOUND", "AMBIGUOUS"}
    assert out.organization_type == "UNKNOWN"


def test_snapshot_without_ascii_key_still_folds(db):
    """Rows predating the ascii_key column fall back to computing the fold on demand."""
    unit = seed_unit(db, uid="u_old", name="Học viện Quốc phòng", org="BQP")
    unit.ascii_key = None
    db.flush()
    out = Resolver(db).resolve(unit_name="Hoc vien Quoc phong")
    assert out.status == "MATCHED"
    assert out.unit_id == "u_old"


def _load_migration():
    spec = importlib.util.spec_from_file_location("m0003", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_fold_map_is_aligned_and_matches_ascii_key():
    """The SQL backfill and the Python fold must not drift apart.

    A hand-aligned translate() pair silently mis-pairs characters when one side gains or
    loses an entry, writing a corrupted key rather than failing, so the mapping is derived
    and verified instead of trusted.
    """
    accented, plain = _load_migration()._fold_map()
    assert len(accented) == len(plain)
    assert len(set(accented)) == len(accented)

    table = str.maketrans(accented, plain)
    samples = [
        "Cục Đối ngoại",
        "Công an xã Phú Hữu",
        "Bộ Tư lệnh Cảnh sát cơ động",
        "Học viện Kỹ thuật Quân sự",
        "Bệnh viện 19-8",
    ]
    for name in samples:
        assert normalize_text(name).translate(table) == ascii_key(name)


def test_migration_fold_map_covers_vietnamese_letters():
    """Every Vietnamese precomposed letter must fold, đ/Đ included."""
    accented, _ = _load_migration()._fold_map()
    for char in "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ":
        assert char in accented, f"{char!r} missing from fold map"
        assert unicodedata.normalize("NFD", char)[0].isascii() or char == "đ"
