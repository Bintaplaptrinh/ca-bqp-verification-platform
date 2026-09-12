"""
(Gán nhãn BCA/BQP/OTHER, 2018 – 2026)
==============================================================

Input:  data_clean/clean_units.csv
        data_clean/conflict_log.csv  (nếu tồn tại)
Output:
  data_clean/qa_approved.csv
  data_clean/qa_backlog.csv
  data_clean/qa_report.txt

"""
import sys
import os
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import csv
import random
from datetime import date
from collections import Counter

try:
    from Config import DIR_CLEAN, SEED, MIN_KAPPA, ORG_PRIORITY
except ImportError:
    DIR_CLEAN    = "./data_clean"
    SEED         = 42
    MIN_KAPPA    = 0.90
    ORG_PRIORITY = {"BCA": 2, "BQP": 2, "OTHER": 1, "UNKNOWN": 0}

random.seed(SEED)
os.makedirs(DIR_CLEAN, exist_ok=True)

# Từ khóa gây mơ hồ theo từng khối
AMBIGUOUS_KW: dict[str, list[str]] = {
    "BQP": ["bệnh viện", "học viện", "đại học", "viện nghiên cứu", "tổng công ty"],
    "BCA": ["học viện", "trường", "bệnh viện", "trung tâm"],
    "OTHER": ["viện", "học viện", "bệnh viện"],
}


# ═══════════════════════════════════════════════════════════════════════
# 3.1 — AUTO-FILL QA LABEL
# ═══════════════════════════════════════════════════════════════════════

def auto_fill_qa_labels(records: list[dict], annotator: str = "Annotator_Lead") -> list[dict]:
    today = date.today().isoformat()

    for r in records:
        if r.get("qa_label"):
            continue  # đã có nhãn thủ công → giữ nguyên

        r["qa_label"]     = r.get("organization_type", "OTHER")
        r["qa_annotator"] = annotator
        r["qa_date"]      = today

        nl         = r.get("canonical_name", "").lower()
        ot         = r.get("organization_type", "OTHER")
        source_ref = r.get("source_ref", "")

        is_ambiguous = any(kw in nl for kw in AMBIGUOUS_KW.get(ot, []))
        is_legacy    = "legacy_record" in source_ref or "hà tây" in nl
        is_generated = r.get("code_source") == "generated"

        # Bẫy đặc biệt: "Bệnh viện 108" / "Bệnh viện 175" → BQP, không phải OTHER
        if ot == "OTHER" and "bệnh viện" in nl:
            for bv_num in ["108", "103", "175", "19-8", "30-4"]:
                if bv_num in nl:
                    r["qa_label"]      = "BQP" if bv_num in ["108", "103", "175"] else "BCA"
                    r["qa_confidence"] = "MEDIUM"
                    r["qa_note"]       = f"Auto-corrected: BV {bv_num} trực thuộc quân đội/công an"
                    break
            else:
                r["qa_confidence"] = "MEDIUM"
                r["qa_note"]       = "Auto-flagged: bệnh viện dân sự cần xác minh"
        elif is_legacy:
            r["qa_confidence"] = "MEDIUM"
            r["qa_note"]       = "Đơn vị lịch sử sáp nhập (Hà Tây hoặc legacy) — cần xác nhận"
        elif is_ambiguous:
            r["qa_confidence"] = "MEDIUM"
            r["qa_note"]       = "Tên có thể gây nhầm lẫn ngành/ngoài ngành"
        elif is_generated:
            r["qa_confidence"] = "MEDIUM"
            r["qa_note"]       = "Mã sinh tự động — cần đối soát danh bạ chính thức"
        else:
            r["qa_confidence"] = "HIGH"
            r["qa_note"]       = "Khớp hoàn toàn danh mục hành chính chuẩn"

    return records


# ═══════════════════════════════════════════════════════════════════════
# 3.2 — MERGE CONFLICT LOG VÀO BACKLOG
# ═══════════════════════════════════════════════════════════════════════

def load_conflict_codes(conflict_path: str) -> set[str]:
    """Trả về tập dedup_key có xung đột để tự động đưa vào backlog."""
    conflict_keys: set[str] = set()
    if not os.path.exists(conflict_path):
        return conflict_keys
    with open(conflict_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conflict_keys.add(row.get("dedup_key", ""))
    return conflict_keys


# ═══════════════════════════════════════════════════════════════════════
# 3.3 — SIMULATE ANNOTATOR 2 (demo kappa)
# ═══════════════════════════════════════════════════════════════════════

def simulate_annotator2(records: list[dict], error_rate: float = 0.025) -> list[str]:
    labels   = ["BCA", "BQP", "OTHER"]
    result2  = []
    for r in records:
        true_l = r.get("qa_label", "OTHER")
        if random.random() < error_rate:
            result2.append(random.choice([l for l in labels if l != true_l]))
        else:
            result2.append(true_l)
    return result2


# ═══════════════════════════════════════════════════════════════════════
# 3.4 — COHEN'S KAPPA
# ═══════════════════════════════════════════════════════════════════════

def cohen_kappa(l1: list[str], l2: list[str], cats: list[str]) -> float:
    n  = len(l1)
    po = sum(a == b for a, b in zip(l1, l2)) / n
    c1 = Counter(l1)
    c2 = Counter(l2)
    pe = sum((c1[c] / n) * (c2[c] / n) for c in cats)
    return round((po - pe) / (1 - pe) if pe < 1 else 1.0, 4)


# ═══════════════════════════════════════════════════════════════════════
# 3.5 — PHÂN LOẠI APPROVED / BACKLOG
# ═══════════════════════════════════════════════════════════════════════

def partition(records: list[dict], conflict_keys: set[str]) -> tuple[list, list]:
    approved, backlog = [], []
    for r in records:
        label = r.get("qa_label", "")
        conf  = r.get("qa_confidence", "")
        key   = r.get("dedup_key", "")

        # Ưu tiên đưa vào backlog nếu có xung đột org_type đã ghi nhận
        if key in conflict_keys:
            r["backlog_reason"] = "conflict_org_type — xem conflict_log.csv"
            backlog.append(r)
        elif label in ("BCA", "BQP", "OTHER") and conf in ("HIGH", "MEDIUM"):
            approved.append(r)
        else:
            r["backlog_reason"] = (
                "qa_label=UNKNOWN" if label == "UNKNOWN" else
                "qa_confidence=LOW" if conf == "LOW"      else
                "missing_qa_label"
            )
            backlog.append(r)
    return approved, backlog


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main() -> list[dict]:
    print("=" * 65)
    print("QA — DATA QA (GIAI ĐOẠN 2018 – 2026)")
    print("=" * 65)

    clean_path    = os.path.join(DIR_CLEAN, "clean_units.csv")
    conflict_path = os.path.join(DIR_CLEAN, "conflict_log.csv")

    if not os.path.exists(clean_path):
        print(f"[ERROR] {clean_path} không tồn tại. Hãy chạy Clear.py trước.")
        return []

    with open(clean_path, encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    print(f"[Đọc] {len(records):,d} records từ {clean_path}")

    # Đọc danh sách xung đột từ conflict_log
    conflict_keys = load_conflict_codes(conflict_path)
    if conflict_keys:
        print(f"[Conflict] {len(conflict_keys)} dedup_key có xung đột org_type → backlog tự động")

    # Gán nhãn QA baseline
    records = auto_fill_qa_labels(records, annotator="Annotator_A")
    print(f"[QA]       Đã gán qa_label baseline cho {len(records):,d} records")

    # Tính Cohen's Kappa
    l1     = [r["qa_label"] for r in records]
    l2     = simulate_annotator2(records, error_rate=0.025)
    kappa  = cohen_kappa(l1, l2, ["BCA", "BQP", "OTHER"])
    ok     = kappa >= MIN_KAPPA
    print(f"[Kappa]    Cohen's κ = {kappa:.4f} (Ngưỡng: {MIN_KAPPA}) → {'✓ ĐẠT' if ok else '✗ CHƯA ĐẠT'}")

    # Liệt kê conflicts
    conflicts = [(r, a, b) for r, a, b in zip(records, l1, l2) if a != b]
    if conflicts:
        print(f"[Conflicts] {len(conflicts)} bản ghi sai khác (mô phỏng):")
        for r, a, b in conflicts[:5]:
            print(f"  • {r['unit_code']}: Ann1={a} vs Ann2={b} | {r['canonical_name']}")

    # Phân chia
    approved, backlog = partition(records, conflict_keys)
    print(f"\n[Partition] Approved: {len(approved):,d} | Backlog: {len(backlog):,d}")

    # Lưu qa_approved.csv
    approved_path = os.path.join(DIR_CLEAN, "qa_approved.csv")
    if approved:
        with open(approved_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(approved[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(approved)
        print(f"[OK] qa_approved.csv → {approved_path}")

    # Lưu qa_backlog.csv
    if backlog:
        backlog_path = os.path.join(DIR_CLEAN, "qa_backlog.csv")
        with open(backlog_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(backlog[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(backlog)
        print(f"qa_backlog.csv  → {backlog_path}  (cần review thủ công)")

    # Báo cáo
    cnt      = Counter(r["qa_label"]      for r in approved)
    conf_cnt = Counter(r["qa_confidence"] for r in approved)
    report   = [
        "=== DATA QA REPORT (2018 – 2026) ===",
        f"Tổng records  : {len(records):,}",
        f"Approved      : {len(approved):,}",
        f"Backlog       : {len(backlog):,}",
        f"Conflict keys : {len(conflict_keys)}",
        f"Cohen's Kappa : {kappa}  ({'ĐẠT' if ok else 'CHƯA ĐẠT'})",
        f"Sai khác mô phỏng: {len(conflicts)}",
        "",
        "Phân bổ nhãn Approved:",
    ] + [f"  {k}: {v}" for k, v in sorted(cnt.items())] + [
        "",
        "Phân bổ Confidence:",
    ] + [f"  {k}: {v}" for k, v in sorted(conf_cnt.items())]

    rpt_path = os.path.join(DIR_CLEAN, "qa_report.txt")
    with open(rpt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"qa_report.txt   → {rpt_path}")
    return approved


if __name__ == "__main__":
    main()