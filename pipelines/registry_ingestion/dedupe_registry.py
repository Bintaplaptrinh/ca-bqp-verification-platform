"""Deduplicate one or more Master Unit Registry CSVs into a single clean file.

Two units are treated as the same unit when they share
(organization_type, normalized_key) — normalized_key is recomputed from
canonical_name so a cleaned-up name ("Bệnh viện 19-8") correctly collapses
with older, messier rows that still carry the same underlying name.

When several rows collapse into one:
- a row already qa_status=APPROVED wins over one that is not
- among rows with the same qa_status, higher evidence_count wins
- ties keep the first file's row (so file order encodes priority)

Merging never drops a coverage_group present in an earlier input just
because a later input happens not to mention it — each input is unioned in,
not used to replace the others.

Usage:
    python -m pipelines.registry_ingestion.dedupe_registry \
        --in artifacts/registry/published/master_units_registry.csv \
        --in artifacts/registry/published/master_units_registry_repaired_v3.csv \
        --out artifacts/registry/published/master_units_registry.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .normalize import normalized_key, ascii_key

REGISTRY_COLUMNS = [
    "unit_id", "canonical_name", "organization_type", "unit_level",
    "coverage_group", "normalized_key", "ascii_key", "source_url",
    "source_urls_json", "source_sha256", "source_hash_kind",
    "evidence_count", "qa_status", "registry_version",
]


def dedupe(frames: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")

    combined["normalized_key"] = combined["canonical_name"].apply(normalized_key)
    combined["ascii_key"] = combined["canonical_name"].apply(ascii_key)

    combined["evidence_count_num"] = pd.to_numeric(
        combined.get("evidence_count", 1), errors="coerce"
    ).fillna(1)
    combined["approved_rank"] = combined["qa_status"].eq("APPROVED").astype(int)
    # Stable sort preserves input file order as the final tiebreaker.
    combined["_input_order"] = range(len(combined))

    deduped = (
        combined.sort_values(
            ["approved_rank", "evidence_count_num", "_input_order"],
            ascending=[False, False, True],
        )
        .drop_duplicates(["organization_type", "normalized_key"], keep="first")
        .sort_values("_input_order")
        .reset_index(drop=True)
    )

    for col in REGISTRY_COLUMNS:
        if col not in deduped.columns:
            deduped[col] = ""

    return deduped[REGISTRY_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in", dest="inputs", action="append", required=True,
        help="Input registry CSV. Repeat to merge several files; first file wins ties.",
    )
    parser.add_argument("--out", required=True, help="Output deduplicated CSV path.")
    args = parser.parse_args()

    frames = [pd.read_csv(p, dtype=str).fillna("") for p in args.inputs]
    before = sum(len(f) for f in frames)

    result = dedupe(frames)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"Input rows (all files, before dedupe): {before}")
    print(f"Output rows (after dedupe):            {len(result)}")
    print()
    print("coverage_group breakdown:")
    print(result["coverage_group"].value_counts().to_string())


if __name__ == "__main__":
    main()
