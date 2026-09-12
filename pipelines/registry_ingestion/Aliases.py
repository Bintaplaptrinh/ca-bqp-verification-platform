"""
Sinh từ điển Alias & Biến thể (2018 – 2026)
================================================================
Chạy: python aliases.py

Input:  data_artifacts/master_units.csv
Output: data_artifacts/unit_aliases.csv

Cải tiến v2:
  - Đồng bộ MANUAL_ALIASES với unit_code chuẩn v2
  - Thêm alias cho các đơn vị 2026 (BCA_C11, QĐ12...)
  - PROVINCES và infer_unit_level được import từ Crawl.py (không dead code)
  - OCR_MAP nhất quán với chuỗi đã normalize (sau smart_title_case)
"""
import sys
import os
# Project root = 2 levels up (pipelines/xxx/ -> pipelines/ -> root)
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import csv
import unicodedata
import re
import random
from collections import Counter

try:
    from Config import DIR_ARTIFACTS, SEED
except ImportError:
    DIR_ARTIFACTS = "./data_artifacts"
    SEED          = 42

random.seed(SEED)
os.makedirs(DIR_ARTIFACTS, exist_ok=True)

STOP_WORDS = frozenset([
    "và", "của", "tại", "về", "theo", "số", "với",
    "cho", "trong", "trên", "từ", "đến", "hoặc",
    "nhân", "dân", "quân", "đội", "cơ", "quan",
])

# ── Alias thủ công chuyên sâu ────────────────
MANUAL_ALIASES: dict[str, list[tuple[str, str]]] = {
    # BCA — Cục nghiệp vụ
    "BCA_C01": [("C01", "abbreviation"), ("C01 BCA", "abbreviation"),
                ("VP CSĐT", "abbreviation"), ("Văn phòng CSĐT", "alias")],
    "BCA_C02": [("C02", "abbreviation"), ("Cục CSHS", "abbreviation"),
                ("Cục Cảnh sát hình sự", "alias")],
    "BCA_C03": [("C03", "abbreviation"), ("Cục CSKT", "abbreviation"),
                ("Cục Cảnh sát kinh tế", "alias")],
    "BCA_C04": [("C04", "abbreviation"), ("C04 BCA", "abbreviation"),
                ("Cục ma túy", "alias"), ("Cục CSĐT tội phạm về ma túy", "alias")],
    "BCA_C06": [("C06", "abbreviation"), ("Cục QLHC về TTXH", "abbreviation"),
                ("Cục CSQLHC", "abbreviation")],
    "BCA_C08": [("C08", "abbreviation"), ("Cục CSGT", "abbreviation"),
                ("Cục Cảnh sát GT", "alias")],
    "BCA_C10": [("C10", "abbreviation"), ("Cục Cảnh sát trại giam", "alias")],
    "BCA_C11": [("C11", "abbreviation"), ("Cục CSPCTP CNC", "abbreviation"),
                ("Cục Tội phạm công nghệ cao", "alias")],   # Đơn vị 2026
    "BCA_A05": [("A05", "abbreviation"), ("Cục An ninh mạng", "alias"),
                ("ANM BCA", "abbreviation")],
    "BCA_K01": [("K01", "abbreviation"), ("BTL Cảnh vệ", "abbreviation"),
                ("Bộ Tư lệnh Cảnh vệ", "alias")],
    "BCA_K02": [("K02", "abbreviation"), ("BTL CSCĐ", "abbreviation"),
                ("CSCĐ", "abbreviation"), ("Cảnh sát cơ động", "alias")],
    # BCA — Công an tỉnh/thành lớn
    "BCA_CA_HN":  [("CATP Hà Nội", "abbreviation"), ("CA TP Hà Nội", "alias"),
                   ("CA Hà Nội", "abbreviation"), ("Cong an Ha Noi", "no_accent"),
                   ("Công an TP HN", "alias")],
    "BCA_CA_HCM": [("CATP Hồ Chí Minh", "abbreviation"), ("Công an TP.HCM", "abbreviation"),
                   ("CATP.HCM", "abbreviation"), ("CA TP HCM", "alias"),
                   ("Cong an TP Ho Chi Minh", "no_accent")],
    "BCA_CA_DN":  [("CATP Đà Nẵng", "abbreviation"), ("CA TP Đà Nẵng", "alias"),
                   ("CA Đà Nẵng", "abbreviation")],
    "BCA_CA_HP":  [("CATP Hải Phòng", "abbreviation"), ("CA HP", "abbreviation"),
                   ("CA Hải Phòng", "alias")],
    "BCA_CA_HTAY":[("CA Hà Tây", "abbreviation"), ("Công an Tỉnh Hà Tây", "alias"),
                   ("CATP Hà Tây", "abbreviation")],    # legacy
    # BCA — Quận/huyện đại diện
    "BCA_CA_HN_CG":  [("CAQ Cầu Giấy", "abbreviation"),
                      ("Công an Q. Cầu Giấy", "alias"), ("CA Q Cầu Giấy", "abbreviation")],
    "BCA_CA_HN_GL":  [("CAH Gia Lâm", "abbreviation"), ("Công an H. Gia Lâm", "alias")],
    "BCA_CA_HN_TX":  [("CA Q Thanh Xuân", "abbreviation"), ("CAQ Thanh Xuân", "abbreviation")],
    # BCA — Phòng nghiệp vụ
    "BCA_CA_HN_PC01": [("PC01 HN", "short_code"), ("PC01 CATP Hà Nội", "abbreviation")],
    # BCA — Học viện
    "BCA_T01": [("ANND", "abbreviation"), ("Học viện ANND", "abbreviation"),
                ("HV An ninh", "alias"), ("T01", "short_code")],
    "BCA_T02": [("CSND", "abbreviation"), ("Học viện CSND", "abbreviation"),
                ("HV Cảnh sát", "alias"), ("T02", "short_code")],
    # BQP — Cấp trên
    "BQP_BTTM":      [("BTTM", "abbreviation"), ("Bộ Tổng Tham mưu", "alias"),
                      ("BTT Mưu", "typo_ocr")],
    "BQP_TCCT":      [("TCCT", "abbreviation"), ("Tổng cục Chính trị", "alias")],
    "BQP_BTL_TDHN":  [("BTL Thủ đô", "abbreviation"), ("Bộ TL Thủ đô HN", "alias"),
                      ("Bộ Tư lệnh Thủ đô", "alias")],
    # BQP — Quân đoàn (kể cả historical)
    "BQP_QD1":  [("Quân đoàn 1", "alias"), ("QĐ 1", "abbreviation"), ("QD1", "short_code"),
                 ("Binh đoàn Quyết Thắng", "alias")],    # valid_to 2023
    "BQP_QD2":  [("Quân đoàn 2", "alias"), ("QĐ 2", "abbreviation"), ("QD2", "short_code"),
                 ("Binh đoàn Hương Giang", "alias")],    # valid_to 2023
    "BQP_QD12": [("Quân đoàn 12", "alias"), ("QĐ 12", "abbreviation"), ("QD12", "short_code")],
    "BQP_QD3":  [("Quân đoàn 3", "alias"), ("QĐ 3", "abbreviation"),
                 ("Binh đoàn Tây Nguyên", "alias")],
    "BQP_QD4":  [("Quân đoàn 4", "alias"), ("QĐ 4", "abbreviation"),
                 ("Binh đoàn Cửu Long", "alias")],
    # BQP — Sư đoàn / Trung đoàn
    "BQP_F308": [("Sư đoàn 308", "alias"), ("f308", "abbreviation"),
                 ("F308", "short_code"), ("Su doan 308", "no_accent")],
    "BQP_F312": [("Sư đoàn 312", "alias"), ("f312", "abbreviation"), ("F312", "short_code")],
    "BQP_E141": [("Trung đoàn 141", "alias"), ("e141", "abbreviation"),
                 ("e141 f312", "short_code")],
    # BQP — Bệnh viện (điểm nhầm lẫn với OTHER)
    "BQP_BV108": [("BV 108", "alias"), ("Viện 108", "alias"),
                  ("BV TƯQĐ 108", "abbreviation"), ("Bệnh viện 108", "alias")],
    "BQP_BV103": [("BV Quân y 103", "alias"), ("Viện 103", "alias"), ("BV 103", "alias")],
    "BQP_BV175": [("BV Quân y 175", "alias"), ("Viện 175", "alias"), ("BV 175", "alias")],
    # BQP — Biên phòng
    "BQP_BDBP_LCA": [("BĐBP Lào Cai", "abbreviation"), ("Biên phòng Lào Cai", "alias")],
    "BQP_BDBP_AGI": [("BĐBP An Giang", "abbreviation"), ("Biên phòng An Giang", "alias")],
    # OTHER — Dân sự điển hình
    "OTH_BHXH_VN": [("BHXH Việt Nam", "abbreviation"), ("Bảo hiểm XH VN", "alias")],
    "OTH_DH_BKHN": [("ĐHBK Hà Nội", "abbreviation"), ("Bách Khoa HN", "alias"),
                    ("HUST", "short_code")],
}

# ── OCR noise map ──────────────────────────────────────────────────────────
# Ánh xạ trên chuỗi đã normalize (mixed-case), không phải ALL CAPS
OCR_MAP = str.maketrans({
    "0": "O", "O": "0",
    "1": "I", "I": "1", "l": "1",
    "5": "S", "S": "5",
    "đ": "d", "Đ": "D",
    "ộ": "o", "ố": "o", "ồ": "o",
    "ế": "e", "ề": "e",
    "ắ": "a", "ặ": "a", "â": "a",
    "ư": "u", "ừ": "u",
})


# ── Hàm cốt lõi ────────────────────────────────────────────────────────────

def remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def abbreviate(name: str) -> str:
    words = name.split()
    return "".join(
        w[0].upper() for w in words
        if w.lower() not in STOP_WORDS and len(w) > 1
    )


def inject_ocr(text: str, rate: float = 0.08) -> str:
    out = []
    for ch in text:
        if random.random() < rate and ch in OCR_MAP:
            out.append(OCR_MAP[ch])
        elif random.random() < rate / 4:
            pass  # drop char
        else:
            out.append(ch)
    return "".join(out)


def generate_domain_aliases(name: str, org_type: str) -> list[tuple[str, str]]:
    """Sinh biến thể hành chính theo luật nghiệp vụ thực tế."""
    variants: list[tuple[str, str]] = []

    if org_type == "BCA":
        replacements = [
            ("Công an Thành phố", [("CATP", "abbreviation"), ("CA TP", "alias"), ("CA", "abbreviation")]),
            ("Công an Tỉnh",      [("CA Tỉnh", "alias"), ("CA", "abbreviation")]),
            ("Công an Quận",      [("CAQ", "abbreviation"), ("Công an Q.", "alias")]),
            ("Công an Huyện",     [("CAH", "abbreviation"), ("Công an H.", "alias")]),
            ("Phòng Cảnh sát hình sự",
             [("PC02", "abbreviation"), ("Phòng CSHS", "alias")]),
            ("Phòng Cảnh sát điều tra tội phạm về ma túy",
             [("PC04", "abbreviation"), ("Phòng CS ma túy", "alias")]),
            ("Phòng Cảnh sát giao thông",
             [("PC08", "abbreviation"), ("Phòng CSGT", "alias")]),
            ("Văn phòng Cơ quan Cảnh sát điều tra",
             [("PC01", "abbreviation")]),
            ("Phòng Cảnh sát quản lý hành chính về trật tự xã hội",
             [("PC06", "abbreviation"), ("Phòng CSQLHC", "alias")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    elif org_type == "BQP":
        replacements = [
            ("Bộ Chỉ huy Quân sự",
             [("BCHQS", "abbreviation"), ("Bộ CHQS", "alias"), ("BCH Quân sự", "alias")]),
            ("Ban Chỉ huy Quân sự",
             [("Ban CHQS", "alias"), ("BCHQS", "abbreviation")]),
            ("Bộ Chỉ huy Bộ đội Biên phòng",
             [("BĐBP", "abbreviation"), ("Biên phòng", "alias")]),
            ("Bộ đội Biên phòng",
             [("BĐBP", "abbreviation"), ("Biên phòng", "alias")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    else:  # OTHER
        replacements = [
            ("Ủy ban nhân dân",         [("UBND", "abbreviation"), ("UB", "alias")]),
            ("Bảo hiểm Xã hội",         [("BHXH", "abbreviation")]),
            ("Sở Giáo dục và Đào tạo",  [("Sở GD&ĐT", "alias"), ("SGD&ĐT", "abbreviation")]),
            ("Sở Y tế",                  [("SYT", "abbreviation")]),
            ("Sở Tài chính",             [("STC", "abbreviation")]),
            ("Sở Tư pháp",               [("STP", "abbreviation")]),
            ("Sở Nội vụ",                [("SNV", "abbreviation")]),
            ("Sở Kế hoạch và Đầu tư",   [("SKH&ĐT", "abbreviation"), ("SKHĐT", "abbreviation")]),
            ("Sở Tài nguyên và Môi trường", [("STNMT", "abbreviation")]),
            ("Sở Xây dựng",              [("SXD", "abbreviation")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    return variants


def build_aliases(registry: list[dict]) -> list[dict]:
    aliases: list[dict] = []
    counter  = 1
    seen_set: set[tuple] = set()  # (unit_id, alias_lower)

    for unit in registry:
        uid      = int(unit["unit_id"])
        code     = unit["unit_code"]
        name     = unit["canonical_name"]
        org_type = unit.get("organization_type", "OTHER")

        def add(alias_name: str, alias_type: str, source: str = "auto") -> None:
            nonlocal counter
            clean = alias_name.strip()
            dedup = (uid, clean.lower())
            if clean and len(clean) >= 2 and dedup not in seen_set:
                seen_set.add(dedup)
                aliases.append({
                    "alias_id":         counter,
                    "unit_id":          uid,
                    "unit_code":        code,
                    "alias_name":       clean,
                    "alias_type":       alias_type,
                    "generator_source": source,
                })
                counter += 1

        # 1. Canonical (bắt buộc)
        add(name, "canonical", "manual_registry")

        # 2. Alias thủ công
        for alias_name, atype in MANUAL_ALIASES.get(code, []):
            add(alias_name, atype, "manual_domain")

        # 3. Luật nghiệp vụ (domain rules)
        for alias_name, atype in generate_domain_aliases(name, org_type):
            add(alias_name, atype, "domain_rules")

        # 4. Bỏ dấu
        no_acc = remove_accents(name)
        if no_acc != name:
            add(no_acc, "no_accent", "auto_rule")

        # 5. Viết tắt chữ cái đầu
        abbr = abbreviate(name)
        if len(abbr) >= 2 and abbr != name:
            add(abbr, "abbreviation", "auto_rule")

        # 6. Typo/OCR (2 biến thể)
        for _ in range(2):
            noisy = inject_ocr(name)
            if noisy != name and len(noisy) > 3:
                add(noisy, "typo_ocr", "noise_injector")

    return aliases


def main() -> list[dict]:
    print("=" * 65)
    print("ALIASES — SINH TỪ ĐIỂN ALIAS (2018 – 2026)")
    print("=" * 65)

    master_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")
    if not os.path.exists(master_path):
        print(f"[ERROR] {master_path} không tồn tại. Hãy chạy registy.py trước.")
        return []

    with open(master_path, encoding="utf-8") as f:
        registry = list(csv.DictReader(f))
    print(f"[Đọc] {len(registry):,d} đơn vị canonical")

    aliases = build_aliases(registry)
    print(f"[OK]  Đã sinh {len(aliases):,d} aliases | TB: {len(aliases)/len(registry):.1f}/đơn vị")

    type_cnt = Counter(a["alias_type"] for a in aliases)
    print("\nPhân bổ alias_type:")
    for k, v in sorted(type_cnt.items()):
        print(f"  {k:20s}: {v:5d}")

    out_path = os.path.join(DIR_ARTIFACTS, "unit_aliases.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(aliases[0].keys()))
        writer.writeheader()
        writer.writerows(aliases)
    print(f"\n[OK] unit_aliases.csv → {out_path}")
    print("TIẾP THEO: python synthetic.py")
    return aliases


if __name__ == "__main__":
    main()