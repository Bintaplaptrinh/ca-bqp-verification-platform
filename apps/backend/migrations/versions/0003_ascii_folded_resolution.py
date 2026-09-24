"""diacritic-folded resolution keys

Adds an ascii_key column next to each normalized_key so a name written without
Vietnamese diacritics can still resolve. The folded key is stored alongside the
accented one (never replacing it) so an exact accented match keeps priority.

Revision ID: 0003_ascii_folded_resolution
Revises: 0002_input_intelligence_bulk
"""
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0003_ascii_folded_resolution"
down_revision = "0002_input_intelligence_bulk"
branch_labels = None
depends_on = None


TABLES = ("units", "unit_names", "registry_snapshot_units", "registry_snapshot_names")


def _fold_map() -> tuple[str, str]:
    """Build the translate() argument pair for diacritic folding.

    Derived from unicodedata so it stays in step with
    cabqp.shared.normalization.ascii_key: every character that decomposes to a single
    base letter plus combining marks maps to that base letter. Đ/đ carry no combining
    mark and are handled explicitly, exactly as ascii_key does.
    """
    accented: list[str] = ["Đ", "đ"]
    plain: list[str] = ["D", "d"]
    for code_point in range(0xC0, 0x1EFF + 1):
        char = chr(code_point)
        if char in ("Đ", "đ") or not char.isalpha():
            continue
        decomposed = unicodedata.normalize("NFD", char)
        base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
        if len(base) == 1 and base.isascii() and base != char:
            accented.append(char)
            plain.append(base)
    assert len(accented) == len(plain), "fold map sides must stay aligned"
    return "".join(accented), "".join(plain)


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("ascii_key", sa.String(500), nullable=True))

    op.create_index("ix_units_ascii_key", "units", ["ascii_key"])
    op.create_index("ix_unit_names_ascii_key", "unit_names", ["ascii_key"])
    op.create_index(
        "ix_snapshot_unit_version_ascii",
        "registry_snapshot_units",
        ["registry_version_id", "ascii_key"],
    )

    # Backfill existing rows. unaccent() is not assumed to be installed, so the fold is
    # expressed as a translate() map. The two sides are derived from unicodedata rather
    # than typed out by hand: a hand-aligned pair of long strings silently mis-pairs
    # characters if either side drifts by one, which corrupts the key instead of failing.
    accented, plain = _fold_map()
    for table in TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET ascii_key = translate(normalized_key, :accented, :plain)"
            ).bindparams(accented=accented, plain=plain)
        )


def downgrade():
    op.drop_index("ix_snapshot_unit_version_ascii", table_name="registry_snapshot_units")
    op.drop_index("ix_unit_names_ascii_key", table_name="unit_names")
    op.drop_index("ix_units_ascii_key", table_name="units")
    for table in TABLES:
        op.drop_column(table, "ascii_key")
