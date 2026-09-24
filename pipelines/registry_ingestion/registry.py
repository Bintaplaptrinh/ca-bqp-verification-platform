from __future__ import annotations
from pathlib import Path
import pandas as pd


REQUIRED_COLUMNS = {
    "unit_id","canonical_name","organization_type","unit_level",
    "coverage_group","normalized_key","ascii_key","source_url",
    "source_sha256","qa_status","registry_version",
}


def load_published_registry(path: Path, config: dict | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Published Registry not found: {path}")

    df = pd.read_csv(path, dtype=str).fillna("")
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Registry missing columns: {sorted(missing)}")

    df = df[df["qa_status"].eq("APPROVED")].copy()

    if df.empty:
        raise ValueError("No APPROVED units in published Registry")
    if df["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in published Registry")
    if df[["organization_type","normalized_key"]].duplicated().any():
        raise ValueError("Duplicate normalized unit name inside organization")
    if df["source_url"].str.strip().eq("").any():
        raise ValueError("Approved unit missing source_url")
    if df["source_sha256"].str.strip().eq("").any():
        raise ValueError("Approved unit missing source_sha256")

    return df
