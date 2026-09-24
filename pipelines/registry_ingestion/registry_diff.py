from __future__ import annotations
import pandas as pd


def registry_diff(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    old = old.set_index("unit_id", drop=False)
    new = new.set_index("unit_id", drop=False)
    rows = []

    for unit_id in sorted(set(new.index) - set(old.index)):
        rows.append({"change_type": "ADDED", "unit_id": unit_id})

    for unit_id in sorted(set(old.index) - set(new.index)):
        rows.append({"change_type": "REMOVED_OR_MISSING", "unit_id": unit_id})

    for unit_id in sorted(set(old.index) & set(new.index)):
        changed = []
        for field in [
            "canonical_name","organization_type","unit_level",
            "coverage_group","registry_version",
        ]:
            if old.at[unit_id, field] != new.at[unit_id, field]:
                changed.append(field)
        if changed:
            rows.append({
                "change_type": "CHANGED",
                "unit_id": unit_id,
                "changed_fields": "|".join(changed),
            })

    return pd.DataFrame(rows)
