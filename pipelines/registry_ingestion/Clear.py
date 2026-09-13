"""
Làm sạch & Chuẩn hóa [2018 – 2026]
=======================================================

Input:  data_raw/raw_ALL_2018_2026.csv  (hoặc raw_2018.csv … raw_2026.csv)
Output:
  data_clean/clean_units.csv        ← đã chuẩn hóa, unit_code nội bộ
  data_clean/duplicates_log.csv     ← nhật ký trùng lặp qua các năm
  data_clean/conflict_log.csv       ← nhật ký xung đột org_type (mới)
  data_clean/clean_report.txt       ← báo cáo thống kê + cảnh báo

"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import os
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import csv
import re
import unicodedata
from collections import Counter
from datetime import date

try:
    from Config import DIR_RAW, DIR_CLEAN, DIR_MANIFESTS, YEAR_START, YEAR_END, ORG_PRIORITY
except ImportError:
    DIR_RAW      = "./data_raw"
    DIR_CLEAN    = "./data_clean"
    DIR_MANIFESTS = "./datasets/manifests"
    YEAR_START   = 2018
    YEAR_END     = 2026
    ORG_PRIORITY = {"BCA": 2, "BQP": 2, "OTHER": 1, "UNKNOWN": 0}

# Import bảng tỉnh/thành để dùng trong infer_unit_level và infer_taxonomy
try:
    from Crawl import PROVINCE_NAME, PROVINCE_LEGACY, infer_unit_level, infer_taxonomy
    _CRAWL_AVAILABLE = True
except ImportError:
    _CRAWL_AVAILABLE = False
    PROVINCE_NAME  = {}
    PROVINCE_LEGACY = {}

os.makedirs(DIR_CLEAN, exist_ok=True)

# ── Ánh xạ ký tự đặc biệt (Typography → ASCII-friendly) ─────────────────────
CHAR_MAP = str.maketrans({
    "\u2019": "'",  "\u2018": "'",   # nháy đơn
    "\u201c": '"',  "\u201d": '"',   # nháy kép
    "\u2013": "-",  "\u2014": "-",   # gạch nối dài
    "\xa0":   " ",                   # non-breaking space
    "\u200b": "",                    # Zero-Width Space — loại bỏ hoàn toàn
    "\u200c": "",                    # Zero-Width Non-Joiner
    "\u200d": "",                    # Zero-Width Joiner
    "\ufeff": "",                    # BOM
})

STOP_WORDS = frozenset([
    "và", "của", "tại", "về", "theo", "số", "với",
    "cho", "trong", "trên", "từ", "đến", "hoặc",
])

# ── Từ quan trọng phải viết hoa chữ đầu (Title-case thông minh) ─────────────
# Danh sách từ KHÔNG viết hoa chữ đầu dù ở giữa cụm
LOWERCASE_PARTICLES = frozenset([
    "và", "của", "về", "tại", "với", "từ", "đến",
    "cho", "trong", "trên", "hoặc", "theo", "số",
])


# ═══════════════════════════════════════════════════════════════════════
# 2.0 — SMART TITLE CASE ( Chuẩn hóa ALL CAPS)
# ═══════════════════════════════════════════════════════════════════════

def smart_title_case(text: str) -> str:
    """
    Chuyển chuỗi ALL CAPS về dạng Title-case cho tiếng Việt.
    - Từ đầu câu/từ quan trọng: viết hoa chữ đầu.
    - Các hư từ (và, của, tại, về…): giữ lowercase nếu không đứng đầu cụm.
    - Từ viết tắt kỹ thuật (BCA, PC08, UBND): GIỮ NGUYÊN.

    Ví dụ:
      "CÔNG AN THÀNH PHỐ HÀ NỘI"   → "Công an Thành phố Hà Nội"
      "BỘ CHỈ HUY QUÂN SỰ TỈNH"   → "Bộ Chỉ huy Quân sự Tỉnh"
      "CATP HCM"                   → "CATP HCM"  (viết tắt, không động)
    """
    if not text:
        return text

    # Nếu chuỗi không phải ALL CAPS (có ít nhất 1 chữ thường) → không xử lý
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio < 0.85:  # dưới 85% chữ hoa → chuỗi đã mixed-case, giữ nguyên
        return text

    words = text.split()
    result = []
    for i, word in enumerate(words):
        # Từ viết tắt kỹ thuật: toàn chữ cái hoặc chữ+số, tất cả hoa, ≤ 6 ký tự
        stripped = re.sub(r"[^A-Za-z0-9]", "", word)
        is_abbr = stripped.isupper() and 1 < len(stripped) <= 6
        if is_abbr:
            result.append(word)  # giữ nguyên
            continue

        word_lower = word.lower()
        if i == 0 or word_lower not in LOWERCASE_PARTICLES:
            # Viết hoa chữ cái đầu (hỗ trợ Unicode tiếng Việt)
            if word_lower:
                result.append(word_lower[0].upper() + word_lower[1:])
            else:
                result.append(word)
        else:
            result.append(word_lower)

    return " ".join(result)


# ═══════════════════════════════════════════════════════════════════════
# 2.1 — NORMALIZE TÊN
# ═══════════════════════════════════════════════════════════════════════

def normalize_name(name: str) -> str:
    """
    Chuẩn hóa tên đơn vị:
    1. Loại ký tự tàng hình (ZWS, BOM) và typography
    2. NFC Unicode
    3. Thu gọn khoảng trắng
    4. Chuẩn hóa khoảng trắng quanh dấu - và /
    5. Bỏ dấu câu cuối dòng
    6. Smart Title-case nếu toàn ALL CAPS
    """
    if not name:
        return ""
    # Bước 1: ánh xạ ký tự đặc biệt (gồm Zero-Width Space) 
    name = name.translate(CHAR_MAP)
    # Bước 2: NFC
    name = unicodedata.normalize("NFC", name.strip())
    # Bước 3: thu gọn khoảng trắng thông thường
    name = re.sub(r"\s+", " ", name)
    # Bước 4: chuẩn hóa khoảng trắng quanh dấu gạch ngang và gạch chéo
    #         "Hà Nội - Hải Phòng" / "số 01/QĐ-BCA" → giữ 1 space mỗi phía
    name = re.sub(r"\s*-\s*", " - ", name)
    name = re.sub(r"\s*/\s*", "/", name)   # dấu / không thêm space
    name = re.sub(r"\s+", " ", name).strip()
    # Bước 5: bỏ dấu câu cuối dòng
    name = name.rstrip(".,;:!?")
    # Bước 6: Smart Title-case nếu cần
    name = smart_title_case(name)
    return name


def normalize_for_dedup(name: str) -> str:
    """
    Chuẩn hóa chỉ dùng để so sánh trùng lặp:
    lowercase + bỏ dấu + bỏ stop word + chỉ giữ chữ cái/số.
    """
    name = normalize_name(name).lower()
    nfkd = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in nfkd if not unicodedata.combining(c))
    name = re.sub(r"[^a-z0-9\s]", "", name)
    tokens = [w for w in name.split() if w not in STOP_WORDS]
    return " ".join(tokens)


# ═══════════════════════════════════════════════════════════════════════
# 2.2 — GÁN UNIT_CODE NỘI BỘ
# ═══════════════════════════════════════════════════════════════════════

_counters: dict[str, int] = {"BCA": 0, "BQP": 0, "OTHER": 0}


def assign_unit_code(record: dict) -> dict:
    raw_code = (record.get("unit_code_raw") or "").strip()
    ot = record.get("organization_type", "OTHER")

    if raw_code and len(raw_code) >= 2:
        record["unit_code"]   = raw_code.upper()
        record["code_source"] = "source"
    else:
        _counters.setdefault(ot, 0)
        _counters[ot] += 1
        record["unit_code"]   = f"{ot}_AUTO_{_counters[ot]:04d}"
        record["code_source"] = "generated"
    return record


# ═══════════════════════════════════════════════════════════════════════
# 2.3 — DEDUPLICATION (Khóa dedup chỉ là dedup_key)
# ═══════════════════════════════════════════════════════════════════════

def deduplicate(
    records: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Loại bỏ bản ghi trùng theo dedup_key và unit_code.

    Xử lý xung đột org_type:
      - Nếu cùng dedup_key có 2 nhãn khác nhau →
        giữ nhãn có ưu tiên cao hơn (BCA/BQP > OTHER).
      - Ghi toàn bộ xung đột vào conflict_log để QA review.

    Theo dõi khoảng năm hoạt động: year_start, year_end (2018-2026).
    Đồng thời liên kết đơn vị đổi tên theo thời gian (ví dụ Thừa Thiên Huế -> Huế)
    để không bị trùng lặp unit_code.

    Trả về: (unique_records, duplicates_log, conflict_log)
    """
    seen: dict[str, dict]          = {}  # dedup_key → record tốt nhất
    code_to_key: dict[str, str]    = {}  # unit_code → dedup_key
    duplicates: list[dict]         = []
    conflict_log: list[dict]       = []

    for r in records:
        key = r["dedup_key"]
        code = r.get("unit_code", "")
        raw_year = str(r.get("year", "")).strip()
        record_year = int(raw_year) if raw_year.isdigit() else YEAR_START

        # Nếu mã đơn vị đã xuất hiện trước đó với tên khác (đơn vị đổi tên theo thời gian)
        if code and code in code_to_key and code_to_key[code] != key:
            existing_key = code_to_key[code]
            existing = seen[existing_key]
            existing["year_start"] = min(existing.get("year_start", record_year), record_year)
            existing["year_end"]   = max(existing.get("year_end",   record_year), record_year)
            # Cập nhật tên mới nhất nếu bản ghi mới hơn
            if record_year >= existing.get("year_end", YEAR_START):
                existing["canonical_name"] = r["canonical_name"]
                existing["unit_name_raw"]  = r["unit_name_raw"]
                existing["dedup_key"]      = key
                del seen[existing_key]
                seen[key] = existing
                code_to_key[code] = key
            duplicates.append({**r, "dup_reason": "unit_code_evolution_renamed"})
            continue

        if key not in seen:
            r["year_start"] = record_year
            r["year_end"]   = record_year
            seen[key] = r
            if code:
                code_to_key[code] = key
        else:
            existing = seen[key]
            # Cập nhật khoảng thời gian hoạt động
            existing["year_start"] = min(
                existing.get("year_start", record_year), record_year)
            existing["year_end"]   = max(
                existing.get("year_end",   record_year), record_year)

            # Kiểm tra xung đột org_type
            r_ot  = r.get("organization_type", "OTHER")
            ex_ot = existing.get("organization_type", "OTHER")
            if r_ot != ex_ot:
                # Ghi nhận xung đột
                conflict_log.append({
                    "dedup_key":         key,
                    "canonical_name":    existing.get("canonical_name", ""),
                    "kept_org_type":     ex_ot,
                    "conflict_org_type": r_ot,
                    "kept_source":       existing.get("source_ref", ""),
                    "conflict_source":   r.get("source_ref", ""),
                    "resolution":        (
                        "kept_existing" if ORG_PRIORITY.get(ex_ot, 0) >= ORG_PRIORITY.get(r_ot, 0)
                        else "replaced_by_higher_priority"
                    ),
                })
                # Thay thế nếu bản ghi mới có nhãn ưu tiên cao hơn
                if ORG_PRIORITY.get(r_ot, 0) > ORG_PRIORITY.get(ex_ot, 0):
                    conflict_log[-1]["resolution"] = "replaced_by_higher_priority"
                    r["year_start"] = existing["year_start"]
                    r["year_end"]   = existing["year_end"]
                    duplicates.append({**existing,
                                       "dup_reason": "conflict_org_type_lower_priority"})
                    seen[key] = r
                    if code:
                        code_to_key[code] = key
                    continue
                else:
                    duplicates.append({**r, "dup_reason": "conflict_org_type_lower_priority"})
                    continue

            # Cùng org_type — ưu tiên bản có mã nguồn hoặc mới hơn
            should_replace = (
                r.get("code_source") == "source"
                and existing.get("code_source") != "source"
            ) or (record_year > existing.get("year_end", YEAR_START))

            if should_replace:
                duplicates.append({**existing, "dup_reason": "replaced_by_newer_or_source_code"})
                r["year_start"] = existing["year_start"]
                r["year_end"]   = existing["year_end"]
                seen[key] = r
                if code:
                    code_to_key[code] = key
            else:
                duplicates.append({**r, "dup_reason": "duplicate_of_existing"})

    return list(seen.values()), duplicates, conflict_log


# ═══════════════════════════════════════════════════════════════════════
# 2.4 — VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def validate_records(records: list[dict]) -> list[str]:
    warnings = []
    codes = [r["unit_code"] for r in records]
    dup_codes = [c for c, n in Counter(codes).items() if n > 1]
    if dup_codes:
        warnings.append(f"[WARN] {len(dup_codes)} unit_code bị trùng: {dup_codes[:10]}")
    for r in records:
        if len(r.get("canonical_name", "")) < 4:
            warnings.append(
                f"[WARN] Tên quá ngắn: {r['unit_code']} = '{r.get('canonical_name')}'")
        if r.get("organization_type") not in ("BCA", "BQP", "OTHER"):
            warnings.append(
                f"[WARN] org_type không hợp lệ: {r['unit_code']} ({r.get('organization_type')})")
    return warnings


# ═══════════════════════════════════════════════════════════════════════
# 2.5 — ĐỌC DỮ LIỆU THÔ
# ═══════════════════════════════════════════════════════════════════════

def load_raw_data() -> list[dict]:
    records: list[dict] = []

    combined = os.path.join(DIR_RAW, f"raw_ALL_{YEAR_START}_{YEAR_END}.csv")
    fallback  = os.path.join(DIR_RAW, "raw_ALL.csv")

    if os.path.exists(combined):
        print(f"[Đọc] File tổng hợp: {combined}")
        with open(combined, encoding="utf-8") as f:
            records = list(csv.DictReader(f))
    elif os.path.exists(fallback):
        print(f"[Đọc] Fallback: {fallback}")
        with open(fallback, encoding="utf-8") as f:
            records = list(csv.DictReader(f))
    else:
        print(f"[Đọc] Quét file theo từng năm {YEAR_START}–{YEAR_END} ...")
        for yr in range(YEAR_START, YEAR_END + 1):
            yr_file = os.path.join(DIR_RAW, f"raw_{yr}.csv")
            if os.path.exists(yr_file):
                with open(yr_file, encoding="utf-8") as f:
                    yr_recs = list(csv.DictReader(f))
                for r in yr_recs:
                    r.setdefault("year", yr)
                records.extend(yr_recs)
                print(f"  + raw_{yr}.csv: {len(yr_recs)} records")
    return records


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main() -> list[dict]:
    print("=" * 65)
    print(f"CLEAR — LÀM SẠCH & CHUẨN HÓA (GIAI ĐOẠN {YEAR_START} – {YEAR_END})")
    print("=" * 65)

    raw_records = load_raw_data()
    if not raw_records:
        print(f"[ERROR] Không tìm thấy dữ liệu thô trong {DIR_RAW}. Hãy chạy Crawl.py trước.")
        return []

    print(f"\n[Tổng nạp] {len(raw_records):,d} raw records giai đoạn {YEAR_START}–{YEAR_END}")

    # Pipeline làm sạch
    processed: list[dict] = []
    for r in raw_records:
        r["canonical_name"] = normalize_name(r.get("unit_name_raw", ""))
        r["dedup_key"]      = normalize_for_dedup(r.get("unit_name_raw", ""))
        r = assign_unit_code(r)

        # Tính lại unit_level và taxonomy 2 trục từ tên đã chuẩn hóa
        p_code = ""
        if _CRAWL_AVAILABLE:
            uc = r.get("unit_code", "")
            # Trích province_code từ unit_code (ví dụ BCA_CA_HN → HN)
            parts = uc.split("_")
            if len(parts) >= 3:
                p_code = parts[2]
            r["unit_level"] = infer_unit_level(r["canonical_name"], r.get("organization_type", "OTHER"), p_code)
            r["admin_level"], r["org_nature"] = infer_taxonomy(r["canonical_name"], r.get("organization_type", "OTHER"), p_code)
        else:
            r["unit_level"]   = r.get("unit_level", "other")
            r["admin_level"]  = r.get("admin_level", "other")
            r["org_nature"]   = r.get("org_nature", "other")

        r["source_kind"] = r.get("source_kind", "GOV_OFFICIAL_FRAMEWORK")
        processed.append(r)

    print(f"[Normalize] {len(processed):,d} records đã chuẩn hóa (incl. ALL CAPS, ZWS, dấu)")

    # Dedup theo dedup_key và unit_code
    unique, dups, conflicts = deduplicate(processed)
    print(f"[Dedup]     {len(unique):,d} unique | {len(dups):,d} trùng | {len(conflicts):,d} xung đột org_type")

    # Validation
    warnings = validate_records(unique)
    for w in warnings[:10]:
        print(f"  {w}")
    if len(warnings) > 10:
        print(f"  ... và {len(warnings) - 10} cảnh báo khác.")
    if not warnings:
        print("  Dữ liệu sạch, không phát hiện lỗi cấu trúc")

    # Chuẩn bị cột đầu ra
    out_fields = [
        "unit_code", "canonical_name", "organization_type",
        "unit_level", "admin_level", "org_nature", "year_start", "year_end",
        "source_ref", "source_url", "source_type", "source_kind",
        "code_source", "crawled_at", "crawl_version",
        "unit_name_raw", "unit_code_raw", "dedup_key",
        # Cột QA — để trống, người QA sẽ điền ở Bước 3
        "qa_label", "qa_annotator", "qa_confidence", "qa_note", "qa_date",
    ]
    for r in unique:
        for col in ["qa_label", "qa_annotator", "qa_confidence", "qa_note", "qa_date"]:
            r.setdefault(col, "")

    # Lưu clean_units.csv
    clean_path = os.path.join(DIR_CLEAN, "clean_units.csv")
    with open(clean_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(unique)
    print(f"\n[OK] clean_units.csv        → {clean_path}")

    # Lưu duplicates_log.csv
    if dups:
        dup_path = os.path.join(DIR_CLEAN, "duplicates_log.csv")
        with open(dup_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(dups[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(dups)
        print(f"[OK] duplicates_log.csv     → {dup_path}")

    # Lưu conflict_log.csv (★ mới)
    if conflicts:
        conflict_path = os.path.join(DIR_CLEAN, "conflict_log.csv")
        with open(conflict_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(conflicts[0].keys()))
            writer.writeheader()
            writer.writerows(conflicts)
        print(f"[OK] conflict_log.csv       → {conflict_path}  ← cần QA review!")
    else:
        print("[OK] Không phát hiện xung đột org_type")

    # Báo cáo
    cnt   = Counter(r["organization_type"] for r in unique)
    l_cnt = Counter(r["unit_level"] for r in unique)
    report_lines = [
        f"=== CLEAN REPORT ({YEAR_START} – {YEAR_END}) ===",
        f"Giai đoạn           : {YEAR_START} – {YEAR_END}",
        f"Tổng raw records    : {len(raw_records):,}",
        f"Unique canonical    : {len(unique):,}",
        f"Duplicates loại bỏ : {len(dups):,}",
        f"Xung đột org_type  : {len(conflicts):,}",
        "",
        "Phân bổ org_type:",
    ] + [f"  {k}: {v}" for k, v in sorted(cnt.items())] + [
        "",
        "Phân bổ unit_level (top 10):",
    ] + [f"  {k}: {v}" for k, v in sorted(l_cnt.items(), key=lambda x: -x[1])[:10]]

    if warnings:
        report_lines += ["", "Cảnh báo:"] + [f"  {w}" for w in warnings[:15]]

    rpt_path = os.path.join(DIR_MANIFESTS, "clean_report.txt")
    with open(rpt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"[OK] clean_report.txt       → {rpt_path}")
    print("\n" + "\n".join(report_lines))
    return unique


if __name__ == "__main__":
    main()