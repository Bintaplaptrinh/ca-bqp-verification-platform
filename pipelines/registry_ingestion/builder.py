from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .normalize import normalized_key, ascii_key
from .taxonomy import classify_unit


def _stable_id(org: str, key: str) -> str:
    digest = hashlib.sha1(f"{org}|{key}".encode("utf-8")).hexdigest()[:12].upper()
    return f"{org}-{digest}"


def _load_curated(project_root: Path, registry_cfg: dict) -> list[pd.DataFrame]:
    frames = []
    for item in registry_cfg.get("curated_fallbacks", []):
        if not item.get("enabled", False):
            continue
        path = project_root / item["path"]
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        if not df.empty:
            frames.append(df)
    return frames


def build_registry(
    candidates: list[dict],
    project_root: Path,
    registry_cfg: dict,
) -> pd.DataFrame:
    min_corroboration = int(
        registry_cfg.get("extraction", {})
        .get("corroboration_required_for_discovery", 2)
    )

    grouped = defaultdict(list)
    for row in candidates:
        key = normalized_key(row["canonical_name_candidate"])
        if key:
            grouped[(row["organization_type"], key)].append(row)

    output = []

    for (org, key), rows in grouped.items():
        names = [r["canonical_name_candidate"] for r in rows]
        display = sorted(names, key=lambda x: (len(x), x))[0]

        strong = any(r["source_role"] == "AUTHORITATIVE_LIST" for r in rows)
        distinct_urls = sorted({r["source_url"] for r in rows})
        distinct_hashes = sorted({r["source_sha256"] for r in rows})
        corroborated = len(distinct_urls) >= min_corroboration

        qa_status = "APPROVED" if strong or corroborated else "PENDING_QA"
        level, coverage_group = classify_unit(display, org)

        output.append({
            "unit_id": _stable_id(org, key),
            "canonical_name": display,
            "organization_type": org,
            "unit_level": level,
            "coverage_group": coverage_group,
            "normalized_key": key,
            "ascii_key": ascii_key(display),
            "source_url": distinct_urls[0],
            "source_urls_json": json.dumps(distinct_urls, ensure_ascii=False),
            "source_sha256": distinct_hashes[0],
            "source_hash_kind": "RAW_SOURCE_SHA256",
            "evidence_count": len(distinct_urls),
            "qa_status": qa_status,
            "registry_version": "",
        })

    dynamic = pd.DataFrame(output)

    curated_frames = _load_curated(project_root, registry_cfg)
    all_frames = []
    if not dynamic.empty:
        all_frames.append(dynamic)
    all_frames.extend(curated_frames)

    if not all_frames:
        return pd.DataFrame()

    merged = pd.concat(all_frames, ignore_index=True, sort=False).fillna("")
    merged["normalized_key"] = merged.apply(
        lambda r: r["normalized_key"] or normalized_key(r["canonical_name"]),
        axis=1,
    )
    merged["ascii_key"] = merged.apply(
        lambda r: r["ascii_key"] or ascii_key(r["canonical_name"]),
        axis=1,
    )

    # Prefer APPROVED then stronger evidence.
    if "evidence_count" not in merged.columns:
        merged["evidence_count"] = "1"
    merged["evidence_count_num"] = pd.to_numeric(
        merged["evidence_count"], errors="coerce"
    ).fillna(1)

    merged["approved_rank"] = merged["qa_status"].eq("APPROVED").astype(int)

    merged = (
        merged.sort_values(
            ["organization_type", "normalized_key", "approved_rank", "evidence_count_num"],
            ascending=[True, True, False, False],
        )
        .drop_duplicates(["organization_type", "normalized_key"], keep="first")
        .copy()
    )

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = f"{registry_cfg['publish_version_prefix']}-{now}"
    merged["registry_version"] = version

    for col in [
        "source_urls_json", "source_hash_kind", "evidence_count"
    ]:
        if col not in merged.columns:
            merged[col] = ""

    return merged[[
        "unit_id","canonical_name","organization_type","unit_level",
        "coverage_group","normalized_key","ascii_key","source_url",
        "source_urls_json","source_sha256","source_hash_kind",
        "evidence_count","qa_status","registry_version"
    ]]


def publish_approved(registry: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """Publish freshly-approved candidates, merging with any registry already
    on disk instead of overwriting it.

    A unit already APPROVED in the published file (including units a human
    approved by hand, which have no corroborating source count the auto
    logic can recompute) is always kept as-is: manual QA decisions must
    never be silently reverted by re-running the crawl/build step.
    """
    approved = registry[registry["qa_status"].eq("APPROVED")].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing = pd.read_csv(output_path, dtype=str).fillna("")
        combined = pd.concat([existing, approved], ignore_index=True, sort=False)
        # Existing (already-published) rows come first, so keep="first"
        # preserves prior manual APPROVED decisions over a re-derived one.
        approved = combined.drop_duplicates(
            ["organization_type", "normalized_key"], keep="first"
        ).reset_index(drop=True)

    approved.to_csv(output_path, index=False, encoding="utf-8-sig")

    review_path = output_path.parent / "registry_pending_qa.csv"
    pending = registry[~registry["qa_status"].eq("APPROVED")].copy()
    # Never re-list a candidate as pending if it was already published/approved
    # (covers manual approvals the auto pass below has no evidence to justify).
    published_keys = set(zip(approved["organization_type"], approved["normalized_key"]))
    pending = pending[
        ~pending.apply(
            lambda r: (r["organization_type"], r["normalized_key"]) in published_keys,
            axis=1,
        )
    ]
    if review_path.exists():
        existing_pending = pd.read_csv(review_path, dtype=str).fillna("")
        pending = pd.concat([existing_pending, pending], ignore_index=True, sort=False)
        pending = pending.drop_duplicates(
            ["organization_type", "normalized_key"], keep="first"
        ).reset_index(drop=True)
        pending = pending[
            ~pending.apply(
                lambda r: (r["organization_type"], r["normalized_key"]) in published_keys,
                axis=1,
            )
        ]
    pending.to_csv(review_path, index=False, encoding="utf-8-sig")

    return approved
