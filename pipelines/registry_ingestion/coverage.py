from __future__ import annotations

import json
from pathlib import Path


def write_coverage(registry, targets: list[dict], output_path: Path):
    groups = []
    for target in targets:
        group_id = target["group_id"]
        subset = registry[registry["coverage_group"].eq(group_id)]
        approved = len(subset)
        expected = target.get("expected_count")
        mode = target["mode"]

        if expected is not None:
            complete = approved >= int(expected)
            status = "COMPLETE" if complete else "INCOMPLETE"
        else:
            complete = None
            status = "PUBLIC_SOURCE_SATURATED" if approved else "NO_PUBLIC_UNITS_APPROVED"

        if mode == "ROSTER_REQUIRED_FOR_COMPLETE" and expected is not None:
            # Count alone is not enough to claim verified roster completeness.
            if approved >= int(expected):
                status = "COUNT_REACHED_ROSTER_VERIFICATION_STILL_REQUIRED"
                complete = False

        groups.append({
            "group_id": group_id,
            "organization_type": target["organization_type"],
            "mode": mode,
            "expected_count": expected,
            "approved_count": approved,
            "complete": complete,
            "status": status,
        })

    report = {
        "registry_units_approved": len(registry),
        "groups": groups,
        "note": (
            "PUBLIC_SATURATION means all configured official public sources were crawled; "
            "it never means 100% of non-public/internal units."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
