from __future__ import annotations
from pathlib import Path
import hashlib
import pandas as pd


def ingest_roster(
    input_path: Path,
    organization_type: str,
    source_url: str,
    name_column: str,
) -> pd.DataFrame:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        src = pd.read_csv(input_path, dtype=str).fillna("")
    elif suffix in {".xlsx", ".xls"}:
        src = pd.read_excel(input_path, dtype=str).fillna("")
    else:
        raise ValueError("Roster must be CSV/XLSX/XLS")

    if name_column not in src.columns:
        raise ValueError(f"Missing roster column: {name_column}")

    checksum = hashlib.sha256(input_path.read_bytes()).hexdigest()
    rows = []
    for _, row in src.iterrows():
        name = str(row[name_column]).strip()
        if name:
            rows.append({
                "organization_type": organization_type,
                "canonical_name": name,
                "source_url": source_url,
                "source_sha256": checksum,
                "qa_status": "PENDING_QA",
            })
    return pd.DataFrame(rows)
