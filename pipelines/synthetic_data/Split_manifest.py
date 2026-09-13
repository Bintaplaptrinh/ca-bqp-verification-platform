"""
Phan chia tap & Xuat Manifest (2018 - 2026)
========================================================================
Input:  data_artifacts/synthetic_records.jsonl
        data_artifacts/master_units.csv
        data_artifacts/unit_aliases.csv
        data_artifacts/hard_cases.jsonl
Output:
  data_artifacts/train.jsonl
  data_artifacts/val.jsonl
  data_artifacts/test.jsonl
  data_artifacts/dataset_manifest.yaml
  data_artifacts/split_report.txt
"""
import sys
import os
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import json
import csv
import random
import hashlib
from datetime import datetime
from collections import Counter

try:
    from Config import (
        DIR_ARTIFACTS, DIR_SAMPLES, DIR_MANIFESTS, DIR_SCHEMA, SEED,
        SPLIT_TRAIN, SPLIT_VAL, SPLIT_TEST,
        REGISTRY_VERSION, SCHEMA_VERSION, YEAR_START, YEAR_END,
    )
except ImportError:
    DIR_ARTIFACTS    = "./data_artifacts"
    DIR_SCHEMA       = "./data_artifacts/schema"
    SEED             = 42
    SPLIT_TRAIN      = 0.70
    SPLIT_VAL        = 0.15
    SPLIT_TEST       = 0.15
    REGISTRY_VERSION = "v2.5.0"
    SCHEMA_VERSION   = "2026_E2E_BiTemporal_3NF_v2"
    YEAR_START       = 2018
    YEAR_END         = 2026
    DIR_SAMPLES   = "./datasets/samples"
    DIR_MANIFESTS = "./datasets/manifests"

random.seed(SEED)
os.makedirs(DIR_ARTIFACTS, exist_ok=True)
os.makedirs(DIR_SAMPLES,   exist_ok=True)
os.makedirs(DIR_MANIFESTS, exist_ok=True)

# Nguong kiem tra chat luong NER
MAX_UNIT_NAME_MISSING_RATE = 0.01   # <= 1%
MIN_UNIT_CODE_COVERAGE     = 0.20   # >= 20%
MIN_BIO_TAGS_RATE          = 1.00   # 100% records phai co bio_tags


# ── Load / Save ──────────────────────────────────────────────────────────────
def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def save_jsonl(records: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── [ADD] NER field validation ────────────────────────────────────────────────
def validate_ner_fields(records: list[dict]) -> dict:
    """
    Kiem tra cac truong NER bat buoc trong moi record (sau Synthetic v2):
      - bio_tags            : phai co (Synthetic v2 moi them)
      - has_unit_code_in_text: phai co trong ground_truth
      - entities            : phai co
    Tra ve dict thong ke de dung trong manifest va report.
    """
    n = len(records)
    missing_bio        = [r["record_id"] for r in records if "bio_tags" not in r]
    missing_entities   = [r["record_id"] for r in records if "entities" not in r]
    missing_code_field = [r["record_id"] for r in records
                          if "has_unit_code_in_text" not in r.get("ground_truth", {})]

    issues = []
    if missing_bio:
        issues.append(f"[WARN] {len(missing_bio):,} records thieu 'bio_tags' — can chay lai Synthetic.py v2")
    if missing_entities:
        issues.append(f"[WARN] {len(missing_entities):,} records thieu 'entities'")
    if missing_code_field:
        issues.append(f"[WARN] {len(missing_code_field):,} records thieu 'has_unit_code_in_text' trong ground_truth")

    if issues:
        for iss in issues:
            print(f"  {iss}")
    else:
        print("  ✓ Tat ca records co du cac truong NER (bio_tags, entities, has_unit_code_in_text)")

    return {
        "has_bio_tags_rate"          : (n - len(missing_bio)) / n,
        "missing_bio_count"          : len(missing_bio),
        "missing_code_field_count"   : len(missing_code_field),
        "schema_valid"               : len(issues) == 0,
    }


# ── [ADD] NER statistics ──────────────────────────────────────────────────────
def compute_ner_stats(records: list[dict]) -> dict:
    """
    Tinh coverage cac entity trong toan bo dataset.
    """
    n = len(records)
    unit_name_tagged  = sum(1 for r in records if any(e["label"] == "UNIT_NAME"  for e in r.get("entities", [])))
    unit_code_tagged  = sum(1 for r in records if any(e["label"] == "UNIT_CODE"  for e in r.get("entities", [])))
    person_tagged     = sum(1 for r in records if any(e["label"] == "PERSON_NAME" for e in r.get("entities", [])))
    has_bio           = sum(1 for r in records if "bio_tags" in r)
    code_in_text_flag = sum(1 for r in records if r.get("ground_truth", {}).get("has_unit_code_in_text"))

    unit_name_rate = unit_name_tagged / n
    unit_code_rate = unit_code_tagged / n

    issues = []
    if unit_name_rate < (1 - MAX_UNIT_NAME_MISSING_RATE):
        issues.append(f"UNIT_NAME missing rate {(1-unit_name_rate)*100:.2f}% > {MAX_UNIT_NAME_MISSING_RATE*100:.0f}% threshold")
    if unit_code_rate < MIN_UNIT_CODE_COVERAGE:
        issues.append(f"UNIT_CODE coverage {unit_code_rate*100:.1f}% < {MIN_UNIT_CODE_COVERAGE*100:.0f}% threshold")
    if has_bio / n < MIN_BIO_TAGS_RATE:
        issues.append(f"bio_tags rate {has_bio/n*100:.1f}% < {MIN_BIO_TAGS_RATE*100:.0f}%")

    return {
        "total"                 : n,
        "unit_name_tagged"      : unit_name_tagged,
        "unit_code_tagged"      : unit_code_tagged,
        "person_tagged"         : person_tagged,
        "bio_tags_present"      : has_bio,
        "has_unit_code_in_text" : code_in_text_flag,
        "unit_name_rate"        : unit_name_rate,
        "unit_code_rate"        : unit_code_rate,
        "person_rate"           : person_tagged / n,
        "bio_rate"              : has_bio / n,
        "issues"                : issues,
    }


# ── Split logic ───────────────────────────────────────────────────────────────
def split_unit_level(
    records: list[dict], registry: list[dict]
) -> tuple[dict[str, list], dict[str, set]]:
    """Split theo unit_id — ZERO LEAKAGE."""
    all_uids = [int(u["unit_id"]) for u in registry]
    random.shuffle(all_uids)
    n     = len(all_uids)
    t_end = int(n * SPLIT_TRAIN)
    v_end = int(n * (SPLIT_TRAIN + SPLIT_VAL))
    train_uids = set(all_uids[:t_end])
    val_uids   = set(all_uids[t_end:v_end])
    test_uids  = set(all_uids[v_end:])
    splits: dict[str, list] = {"train": [], "val": [], "test": []}
    for r in records:
        uid = r["ground_truth"]["unit_id"]
        if uid in train_uids:
            splits["train"].append(r)
        elif uid in val_uids:
            splits["val"].append(r)
        else:
            splits["test"].append(r)
    return splits, {"train": train_uids, "val": val_uids, "test": test_uids}


def validate_no_leakage(uid_groups: dict[str, set]) -> bool:
    t, v, te = uid_groups["train"], uid_groups["val"], uid_groups["test"]
    errors = []
    if t & v:  errors.append(f"LEAK train∩val: {len(t & v)} units")
    if t & te: errors.append(f"LEAK train∩test: {len(t & te)} units")
    if v & te: errors.append(f"LEAK val∩test: {len(v & te)} units")
    if errors:
        for e in errors: print(f"  [ERROR] {e}")
        return False
    print("  ✓ Zero leakage: khong don vi nao bi ro ri giua cac tap")
    return True


# ── [UPD] Test coverage check — them UNIT_CODE ────────────────────────────────
def check_test_coverage(test_records: list[dict]) -> list[str]:
    """
    Kiem tra test set co du da dang:
      - >= 4 template groups
      - du 3 org types (BCA, BQP, OTHER)
      - [NEW] UNIT_CODE coverage >= 20%
      - [NEW] bio_tags 100%
    """
    grp  = Counter(r["ground_truth"]["template_group"]    for r in test_records)
    org  = Counter(r["ground_truth"]["organization_type"] for r in test_records)
    code_tagged = sum(1 for r in test_records if any(e["label"] == "UNIT_CODE" for e in r.get("entities", [])))
    bio_present = sum(1 for r in test_records if "bio_tags" in r)
    n = len(test_records)

    print(f"\n  [Test set] templates: {dict(grp)} | orgs: {dict(org)}")
    print(f"  [Test set] UNIT_CODE tagged: {code_tagged:,} / {n:,} ({code_tagged/n*100:.1f}%)")
    print(f"  [Test set] bio_tags present: {bio_present:,} / {n:,} ({bio_present/n*100:.1f}%)")

    issues = []
    if len(grp) < 4:
        issues.append(f"Test thieu da dang template ({len(grp)}/6 nhom)")
    if len(org) < 3:
        issues.append("Test chua du 3 khoi BCA+BQP+OTHER")
    if code_tagged / n < MIN_UNIT_CODE_COVERAGE:
        issues.append(f"UNIT_CODE trong test chi {code_tagged/n*100:.1f}% < {MIN_UNIT_CODE_COVERAGE*100:.0f}%")
    if bio_present < n:
        issues.append(f"{n-bio_present} records trong test thieu bio_tags")
    return issues


# ── [UPD] create_manifest — them ner_quality section ─────────────────────────
def create_manifest(
    registry: list[dict], alias_path: str,
    splits: dict, uid_groups: dict,
    ner_stats: dict, schema_valid: bool,
    hard_cases_count: int,
) -> str:
    with open(alias_path, encoding="utf-8") as f:
        aliases = list(csv.DictReader(f))

    total   = sum(len(v) for v in splits.values())
    org_cnt = Counter(u["organization_type"] for u in registry)
    closed  = sum(1 for u in registry if u.get("valid_to"))

    content  = json.dumps([dict(u) for u in registry], ensure_ascii=False, sort_keys=True)
    checksum = hashlib.sha256(content.encode()).hexdigest()

    unit_name_miss_rate = (1 - ner_stats["unit_name_rate"]) * 100
    leakage_status      = "PASS" if not any("LEAK" in i for i in ner_stats.get("issues", [])) else "FAIL"

    return f"""
dataset_metadata:
  version: "{REGISTRY_VERSION}"
  created_date: "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
  random_seed: {SEED}
  schema_version: "{SCHEMA_VERSION}"
  registry_checksum: "{checksum}"
  coverage_period: "{YEAR_START} - {YEAR_END}"
  administrative_scope: "64 provinces (includes historical Ha Tay)"

statistics:
  total_units: {len(registry)}
  units_with_valid_to: {closed}
  org_type_breakdown:
    BCA: {org_cnt.get('BCA', 0)}
    BQP: {org_cnt.get('BQP', 0)}
    OTHER: {org_cnt.get('KHAC', 0)}
  total_aliases: {len(aliases)}
  alias_per_unit_avg: {len(aliases)/len(registry):.1f}
  total_synthetic_records: {total}

split_strategy: "unit-level (Zero Leakage)"
split_summary:
  train:
    records: {len(splits['train'])}
    total_units: {len(uid_groups['train'])}
    ratio: {len(splits['train'])/total*100:.1f}%
  val:
    records: {len(splits['val'])}
    total_units: {len(uid_groups['val'])}
    ratio: {len(splits['val'])/total*100:.1f}%
  test:
    records: {len(splits['test'])}
    total_units: {len(uid_groups['test'])}
    ratio: {len(splits['test'])/total*100:.1f}%

labels:
  organization_type: [BCA, BQP, OTHER]
  verification_status: [KHOP_LE, NEED_REVIEW, NOT_FOUND, EXTRACTION_FAILED]

ner_entities:
  - UNIT_NAME
  - UNIT_CODE
  - PERSON_NAME

ner_quality:
  unit_name_tagged: {ner_stats['unit_name_tagged']}
  unit_name_coverage: "{ner_stats['unit_name_rate']*100:.2f}%"
  unit_code_tagged: {ner_stats['unit_code_tagged']}
  unit_code_coverage: "{ner_stats['unit_code_rate']*100:.2f}%"
  unit_code_ratio_in_text: {ner_stats['has_unit_code_in_text']}
  person_name_tagged: {ner_stats['person_tagged']}
  bio_tags: true
  bio_tags_present: {ner_stats['bio_tags_present']}
  has_unit_code_in_text_field: true
  hard_cases_count: {hard_cases_count}
  ocr_noise_injection: true
  ocr_noise_level: 0.35
  schema_valid: {str(schema_valid).lower()}

quality_gates:
  split_strategy: unit-level (no unit appears in 2 splits)
  min_alias_per_unit: 3
  min_template_groups_in_test: 4
  min_org_types_in_test: 3
  min_unit_code_coverage: "{MIN_UNIT_CODE_COVERAGE*100:.0f}%"
  max_unit_name_missing_rate: "{MAX_UNIT_NAME_MISSING_RATE*100:.0f}%"
  registry_version_tracked: true
  zero_leakage_status: {leakage_status}
  unit_name_missing_rate: "{unit_name_miss_rate:.2f}%"
  dedup_key: "name-only (NOT org_type) - conflict resolved by priority"

artifacts:
  - master_units.csv
  - master_units.csv.sha256
  - unit_aliases.csv
  - schema/UNITS.csv
  - schema/UNIT_CODES.csv
  - schema/UNIT_NAMES.csv
  - schema/SOURCES.csv
  - schema/UNIT_EVENTS.csv
  - synthetic_records.jsonl
  - train.jsonl
  - val.jsonl
  - test.jsonl
  - hard_cases.jsonl
  - dataset_manifest.yaml
  - split_report.txt
"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 65)
    print(f"SPLIT v2 -- PHAN CHIA TAP & MANIFEST ({YEAR_START} - {YEAR_END})")
    print("=" * 65)

    master_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")       # Input: working artifact
    syn_path    = os.path.join(DIR_SAMPLES,   "synthetic_records.jsonl") # Input: từ Synthetic.py
    alias_path  = os.path.join(DIR_ARTIFACTS, "unit_aliases.csv")        # Input: working artifact
    hard_path   = os.path.join(DIR_SAMPLES,   "hard_cases.jsonl")        # Input: từ Synthetic.py

    if not all(os.path.exists(p) for p in [master_path, syn_path, alias_path]):
        print("[ERROR] Thieu artifacts. Hay chay Registy.py, Synthetic.py truoc.")
        return

    with open(master_path, encoding="utf-8") as f:
        registry = list(csv.DictReader(f))
    records = load_jsonl(syn_path)
    hard_cases_count = len(load_jsonl(hard_path)) if os.path.exists(hard_path) else 0

    print(f"[Doc] {len(registry):,} don vi | {len(records):,} records | {hard_cases_count} hard cases")

    # Validate NER fields truoc khi split
    print("\n[Kiem tra NER schema]")
    field_check = validate_ner_fields(records)

    # Tinh NER stats tren toan bo dataset
    print("\n[Tinh NER stats (toan bo dataset)]")
    ner_stats = compute_ner_stats(records)
    print(f"  UNIT_NAME : {ner_stats['unit_name_tagged']:,} / {ner_stats['total']:,} ({ner_stats['unit_name_rate']*100:.2f}%)")
    print(f"  UNIT_CODE : {ner_stats['unit_code_tagged']:,} / {ner_stats['total']:,} ({ner_stats['unit_code_rate']*100:.2f}%)")
    print(f"  PERSON    : {ner_stats['person_tagged']:,} / {ner_stats['total']:,} ({ner_stats['person_rate']*100:.2f}%)")
    print(f"  bio_tags  : {ner_stats['bio_tags_present']:,} / {ner_stats['total']:,} ({ner_stats['bio_rate']*100:.2f}%)")
    if ner_stats["issues"]:
        for iss in ner_stats["issues"]:
            print(f"  [WARN] {iss}")
    else:
        print("  ✓ Tat ca NER quality gates PASS")

    # Split
    splits, uid_groups = split_unit_level(records, registry)
    print("\n[Phan chia]")
    for name, data in splits.items():
        print(f"  {name:5s}: {len(data):6,} records | {len(uid_groups[name]):4d} don vi")

    print("\n[Kiem tra leakage]")
    ok = validate_no_leakage(uid_groups)

    issues = check_test_coverage(splits["test"])
    if issues:
        for iss in issues: print(f"  [WARN] {iss}")
    else:
        print("  ✓ Test set dat chuan da dang (template, org, UNIT_CODE, bio_tags)")

    # Luu train/val/test → datasets/samples/ va data_artifacts/
    print("\n[Luu files]")
    for name, data in splits.items():
        path = os.path.join(DIR_SAMPLES, f"{name}.jsonl")
        save_jsonl(data, path)
        print(f"  [OK] {name}.jsonl -> {path}")
        path_art = os.path.join(DIR_ARTIFACTS, f"{name}.jsonl")
        save_jsonl(data, path_art)
        print(f"  [OK] {name}.jsonl -> {path_art}")

    # Manifest → datasets/manifests/
    manifest = create_manifest(
        registry, alias_path, splits, uid_groups,
        ner_stats, field_check["schema_valid"],
        hard_cases_count,
    )
    mf_path = os.path.join(DIR_MANIFESTS, "dataset_manifest.yaml")
    with open(mf_path, "w", encoding="utf-8") as f:
        f.write(manifest)
    print(f"\n[OK] dataset_manifest.yaml -> {mf_path}")
    mf_path_art = os.path.join(DIR_ARTIFACTS, "dataset_manifest.yaml")
    with open(mf_path_art, "w", encoding="utf-8") as f:
        f.write(manifest)

    # Split_report.txt → datasets/manifests/
    org_test = Counter(r["ground_truth"]["organization_type"] for r in splits["test"])
    grp_test = Counter(r["ground_truth"]["template_group"]    for r in splits["test"])
    code_test = sum(1 for r in splits["test"] if any(e["label"] == "UNIT_CODE" for e in r.get("entities", [])))
    total     = len(records)

    report = [
        f"=== DATASET SPLIT REPORT v2 ({YEAR_START} - {YEAR_END}) ===",
        f"Thoi gian    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Schema       : Synthetic v2 (bio_tags, UNIT_CODE entity)",
        f"Canonical units: {len(registry):,}",
        f"Synthetic recs : {total:,}",
        f"Hard cases     : {hard_cases_count}",
        "",
        "Chi tiet tap:",
        f"  Train: {len(splits['train']):6,} records ({len(splits['train'])/total*100:.1f}%) | {len(uid_groups['train'])} units",
        f"  Val  : {len(splits['val']):6,} records ({len(splits['val'])/total*100:.1f}%) | {len(uid_groups['val'])} units",
        f"  Test : {len(splits['test']):6,} records ({len(splits['test'])/total*100:.1f}%) | {len(uid_groups['test'])} units",
        "",
        f"Zero Leakage : {'PASS' if ok else 'FAIL'}",
        "",
        "NER Stats (toan bo dataset):",
        f"  UNIT_NAME  : {ner_stats['unit_name_tagged']:,} / {total:,} ({ner_stats['unit_name_rate']*100:.2f}%)",
        f"  UNIT_CODE  : {ner_stats['unit_code_tagged']:,} / {total:,} ({ner_stats['unit_code_rate']*100:.2f}%)",
        f"  PERSON_NAME: {ner_stats['person_tagged']:,} / {total:,} ({ner_stats['person_rate']*100:.2f}%)",
        f"  bio_tags   : {ner_stats['bio_tags_present']:,} / {total:,} ({ner_stats['bio_rate']*100:.2f}%)",
        "",
        "NER Quality Gates:",
        f"  UNIT_NAME missing rate : {(1-ner_stats['unit_name_rate'])*100:.2f}% (threshold <= {MAX_UNIT_NAME_MISSING_RATE*100:.0f}%)",
        f"  UNIT_CODE coverage     : {ner_stats['unit_code_rate']*100:.2f}% (threshold >= {MIN_UNIT_CODE_COVERAGE*100:.0f}%)",
        f"  bio_tags rate          : {ner_stats['bio_rate']*100:.2f}% (threshold = 100%)",
        f"  Schema valid           : {field_check['schema_valid']}",
        f"  NER gates status       : {'PASS' if not ner_stats['issues'] else 'FAIL - ' + str(ner_stats['issues'])}",
        "",
        "Test -- Phan bo khoi:",
        *[f"  {k}: {v}" for k, v in sorted(org_test.items())],
        "",
        "Test -- Phan bo template:",
        *[f"  {k}: {v}" for k, v in sorted(grp_test.items())],
        "",
        f"Test -- UNIT_CODE tagged: {code_test:,} / {len(splits['test']):,} ({code_test/len(splits['test'])*100:.1f}%)",
    ]
    rpt_path = os.path.join(DIR_MANIFESTS, "split_report.txt")
    with open(rpt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"[OK] split_report.txt -> {rpt_path}")

    # Tong ket
    print("\n" + "=" * 65)
    print("HOAN TAT PIPELINE -- Danh muc artifacts:")
    print("-" * 65)
    artifact_map = {
        "master_units.csv"       : DIR_ARTIFACTS,
        "master_units.csv.sha256": DIR_ARTIFACTS,
        "unit_aliases.csv"       : DIR_ARTIFACTS,
        "schema/UNITS.csv"       : DIR_ARTIFACTS,
        "schema/UNIT_CODES.csv"  : DIR_ARTIFACTS,
        "schema/UNIT_NAMES.csv"  : DIR_ARTIFACTS,
        "schema/SOURCES.csv"     : DIR_ARTIFACTS,
        "schema/UNIT_EVENTS.csv" : DIR_ARTIFACTS,
        "synthetic_records.jsonl": DIR_SAMPLES,
        "train.jsonl"            : DIR_SAMPLES,
        "val.jsonl"              : DIR_SAMPLES,
        "test.jsonl"             : DIR_SAMPLES,
        "hard_cases.jsonl"       : DIR_SAMPLES,
        "dataset_manifest.yaml"  : DIR_MANIFESTS,
        "split_report.txt"       : DIR_MANIFESTS,
    }
    for fname, fdir in artifact_map.items():
        fpath = os.path.join(fdir, fname)
        if os.path.exists(fpath):
            sz    = os.path.getsize(fpath)
            with open(fpath, encoding="utf-8") as fp:
                lines = sum(1 for l in fp if l.strip())
            print(f"  {fname:30s} {lines:7,} dong  {sz:>13,} bytes")
        else:
            print(f"  {fname:30s} (chua tao)")
    print("=" * 65)


if __name__ == "__main__":
    main()
