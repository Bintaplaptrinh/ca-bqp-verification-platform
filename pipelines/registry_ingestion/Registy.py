"""
Xây dựng Master Unit Registry (2018 – 2026)
================================================================
Input:  data_clean/qa_approved.csv
Output:
  data_artifacts/master_units.csv
  data_artifacts/master_units.csv.sha256

"""
import sys
import os
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import csv
import hashlib
import json
from collections import Counter

try:
    from Config import DIR_CLEAN, DIR_ARTIFACTS, REGISTRY_VERSION
except ImportError:
    DIR_CLEAN        = "./data_clean"
    DIR_ARTIFACTS    = "./data_artifacts"
    REGISTRY_VERSION = "v2.0.0"

os.makedirs(DIR_ARTIFACTS, exist_ok=True)

# Các đơn vị có valid_to cố định (mốc sáp nhập / giải thể lịch sử)
FIXED_VALID_TO: dict[str, str] = {
    # Hà Tây sáp nhập vào Hà Nội
    "BCA_CA_HTAY":  "2008-08-01",
    "BQP_BCH_HTAY": "2008-08-01",
    "OTH_UBND_HTAY":"2008-08-01",
    # Quân đoàn 1 & 2 sáp nhập thành QĐ 12 cuối 2023
    "BQP_QD1":      "2023-12-31",
    "BQP_QD2":      "2023-12-31",
}

# Prefix của đơn vị Hà Tây (con) — tất cả đều kết thúc 2008
HATAY_PREFIXES = ("BCA_CA_HTAY_", "BQP_BCH_HTAY_", "OTH_UBND_HTAY_", "OTH_BHXH_HTAY_")


def build_registry() -> list[dict]:
    print("=" * 65)
    print("REGISTRY — MASTER UNIT REGISTRY (2018 – 2026)")
    print("=" * 65)

    approved_path = os.path.join(DIR_CLEAN, "qa_approved.csv")
    if not os.path.exists(approved_path):
        print(f"[ERROR] {approved_path} không tồn tại. Hãy chạy qa.py trước.")
        return []

    with open(approved_path, encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    print(f"[Đọc] {len(records):,d} records đã QA từ {approved_path}")

    registry: list[dict] = []
    for idx, r in enumerate(records, 1):
        unit_code = r.get("unit_code", "")

        y_start = r.get("year_start", "").strip()
        y_end   = r.get("year_end",   "").strip()
        valid_from = f"{y_start}-01-01" if y_start.isdigit() else "2018-01-01"

        # Xác định valid_to
        if unit_code in FIXED_VALID_TO:
            valid_to = FIXED_VALID_TO[unit_code]
        elif any(unit_code.startswith(pfx) for pfx in HATAY_PREFIXES):
            valid_to = "2008-08-01"
        elif y_end.isdigit() and int(y_end) < 2026:
            valid_to = f"{y_end}-12-31"
        elif "legacy_record" in r.get("source_ref", ""):
            valid_to = "2008-08-01"
        else:
            valid_to = ""  # đang hoạt động

        registry.append({
            "unit_id":           idx,
            "unit_code":         unit_code,
            "canonical_name":    r["canonical_name"],
            "organization_type": r["qa_label"],
            "unit_level":        r.get("unit_level", ""),
            "source_ref":        r.get("source_ref", ""),
            "valid_from":        valid_from,
            "valid_to":          valid_to,
            "registry_version":  REGISTRY_VERSION,
            "qa_confidence":     r.get("qa_confidence", "HIGH"),
        })

    # Checksum SHA-256
    content_str = json.dumps(registry, ensure_ascii=False, sort_keys=True)
    checksum    = hashlib.sha256(content_str.encode()).hexdigest()

    # Lưu master_units.csv
    out_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(registry[0].keys()))
        writer.writeheader()
        writer.writerows(registry)

    # Lưu checksum
    cs_path = out_path + ".sha256"
    with open(cs_path, "w", encoding="utf-8") as f:
        f.write(checksum)

    print(f"\n[OK] {len(registry):,d} đơn vị → {out_path}")
    print(f"[OK] Checksum: {checksum[:16]}… → {cs_path}")

    cnt = Counter(r["organization_type"] for r in registry)
    print("\nPhân bổ đơn vị theo khối:")
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v:,d}")

    # Cảnh báo đơn vị có valid_to
    closed = [r for r in registry if r["valid_to"]]
    if closed:
        print(f"\n  [{len(closed)} đơn vị có valid_to (đã giải thể/sáp nhập)]")

    return registry


if __name__ == "__main__":
    build_registry()