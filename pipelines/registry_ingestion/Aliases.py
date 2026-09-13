"""
Sinh từ điển Alias & Biến thể Chuẩn Quản Trị (2018 – 2026)
================================================================
Input:  data_artifacts/master_units.csv
Output: data_artifacts/unit_aliases.csv
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
import unicodedata
import re
import random
from collections import Counter, defaultdict

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

# ── Alias thủ công thực tế sâu (DEEP MANUAL ALIASES) ────────────────
MANUAL_ALIASES: dict[str, list[tuple[str, str]]] = { 
    # BCA — Cơ quan Bộ
    "BCA_C01": [("C01", "viet_tat"), ("C01 BCA", "viet_tat"),
                ("VP CSĐT", "viet_tat"), ("Văn phòng CSĐT", "ten_goi_khac"),
                ("Cơ quan CSĐT BCA", "ten_goi_khac")],
    "BCA_C02": [("C02", "viet_tat"), ("Cục CSHS", "viet_tat"),
                ("Cục Cảnh sát hình sự", "ten_goi_khac"), ("CSHS Bộ", "viet_tat")],
    "BCA_C03": [("C03", "viet_tat"), ("Cục CSKT", "viet_tat"),
                ("Cục Cảnh sát kinh tế", "ten_goi_khac"), ("CSKT Bộ", "viet_tat")],
    "BCA_C04": [("C04", "viet_tat"), ("C04 BCA", "viet_tat"),
                ("Cục ma túy", "ten_goi_khac"), ("Cục CSĐT tội phạm về ma túy", "ten_goi_khac")],
    "BCA_C06": [("C06", "viet_tat"), ("Cục QLHC về TTXH", "viet_tat"),
                ("Cục CSQLHC", "viet_tat"), ("C06 BCA", "viet_tat")],
    "BCA_C08": [("C08", "viet_tat"), ("Cục CSGT", "viet_tat"),
                ("Cục Cảnh sát GT", "ten_goi_khac"), ("CSGT Bộ", "viet_tat")],
    "BCA_C10": [("C10", "viet_tat"), ("Cục Cảnh sát trại giam", "ten_goi_khac")],
    "BCA_C11": [("C11", "viet_tat"), ("Cục CSPCTP CNC", "viet_tat"),
                ("Cục Tội phạm công nghệ cao", "ten_goi_khac"), ("C11 BCA", "viet_tat")],
    "BCA_A01": [("A01", "viet_tat"), ("Văn phòng ANĐT", "ten_goi_khac"),
                ("Cơ quan ANĐT Bộ Công an", "ten_goi_khac")],
    "BCA_A02": [("A02", "viet_tat"), ("Cục An ninh chính trị", "ten_goi_khac"),
                ("ANCTNB", "viet_tat")],
    "BCA_A03": [("A03", "viet_tat"), ("Cục An ninh kinh tế", "ten_goi_khac"),
                ("ANKT", "viet_tat")],
    "BCA_A05": [("A05", "viet_tat"), ("Cục An ninh mạng", "ten_goi_khac"),
                ("ANM BCA", "viet_tat"), ("A05 BCA", "viet_tat")],
    "BCA_K01": [("K01", "viet_tat"), ("BTL Cảnh vệ", "viet_tat"),
                ("Bộ Tư lệnh Cảnh vệ", "ten_goi_khac")],
    "BCA_K02": [("K02", "viet_tat"), ("BTL CSCĐ", "viet_tat"),
                ("CSCĐ", "viet_tat"), ("Cảnh sát cơ động", "ten_goi_khac")],
    # BCA — Công an tỉnh/thành lớn
    "BCA_CA_HN":  [("CATP Hà Nội", "viet_tat"), ("CA TP Hà Nội", "ten_goi_khac"),
                   ("CA Hà Nội", "viet_tat"), ("Cong an Ha Noi", "khong_dau"),
                   ("Công an TP HN", "ten_goi_khac"), ("CATP HN", "viet_tat")],
    "BCA_CA_HCM": [("CATP Hồ Chí Minh", "viet_tat"), ("Công an TP.HCM", "viet_tat"),
                   ("CATP.HCM", "viet_tat"), ("CA TP HCM", "ten_goi_khac"),
                   ("CATP HCM", "viet_tat"), ("Cong an TP Ho Chi Minh", "khong_dau")],
    "BCA_CA_DN":  [("CATP Đà Nẵng", "viet_tat"), ("CA TP Đà Nẵng", "ten_goi_khac"),
                   ("CA Đà Nẵng", "viet_tat"), ("CATP ĐN", "viet_tat")],
    "BCA_CA_HP":  [("CATP Hải Phòng", "viet_tat"), ("CA HP", "viet_tat"),
                   ("CA Hải Phòng", "ten_goi_khac"), ("CATP HP", "viet_tat")],
    "BCA_CA_CT":  [("CATP Cần Thơ", "viet_tat"), ("CA Cần Thơ", "viet_tat"),
                   ("CATP CT", "viet_tat")],
    "BCA_CA_HTAY":[("CA Hà Tây", "viet_tat"), ("Công an Tỉnh Hà Tây", "ten_goi_khac"),
                   ("CATP Hà Tây", "viet_tat")],
    # BCA — Quận/huyện tiêu biểu
    "BCA_CA_HN_BDG": [("CAQ Ba Đình", "viet_tat"), ("Công an Q. Ba Đình", "ten_goi_khac"),
                      ("CA Q Ba Đình", "viet_tat"), ("CA Huyện Ba Đình", "lich_su")],
    "BCA_CA_HN_HK":  [("CAQ Hoàn Kiếm", "viet_tat"), ("Công an Q. Hoàn Kiếm", "ten_goi_khac")],
    "BCA_CA_HN_CG":  [("CAQ Cầu Giấy", "viet_tat"), ("Công an Q. Cầu Giấy", "ten_goi_khac"),
                      ("CA Q Cầu Giấy", "viet_tat")],
    "BCA_CA_HN_GL":  [("CAH Gia Lâm", "viet_tat"), ("Công an H. Gia Lâm", "ten_goi_khac")],
    "BCA_CA_HN_TX":  [("CA Q Thanh Xuân", "viet_tat"), ("CAQ Thanh Xuân", "viet_tat")],
    # BCA — Phòng nghiệp vụ
    "BCA_CA_HN_PC01": [("PC01 HN", "ma_ngan"), ("PC01 CATP Hà Nội", "viet_tat"),
                       ("VP CSĐT CA Hà Nội", "ten_goi_khac")],
    "BCA_CA_HN_PC02": [("PC02 HN", "ma_ngan"), ("PC02 CATP Hà Nội", "viet_tat"),
                       ("Phòng CSHS CA Hà Nội", "ten_goi_khac")],
    "BCA_CA_HN_PC08": [("PC08 HN", "ma_ngan"), ("PC08 CATP Hà Nội", "viet_tat"),
                       ("Phòng CSGT CA Hà Nội", "ten_goi_khac")],
    # BCA — Học viện
    "BCA_T01": [("ANND", "viet_tat"), ("Học viện ANND", "viet_tat"),
                ("HV An ninh", "ten_goi_khac"), ("T01", "ma_ngan")],
    "BCA_T02": [("CSND", "viet_tat"), ("Học viện CSND", "viet_tat"),
                ("HV Cảnh sát", "ten_goi_khac"), ("T02", "ma_ngan")],
    # BQP — Cơ quan Bộ & Chiến lược
    "BQP_BTTM":      [("BTTM", "viet_tat"), ("Bộ Tổng Tham mưu", "ten_goi_khac"),
                      ("BTT Mưu", "loi_danh_may")],
    "BQP_TCCT":      [("TCCT", "viet_tat"), ("Tổng cục Chính trị", "ten_goi_khac")],
    "BQP_BTL_TDHN":  [("BTL Thủ đô", "viet_tat"), ("Bộ TL Thủ đô HN", "ten_goi_khac"),
                      ("Bộ Tư lệnh Thủ đô", "ten_goi_khac")],
    "BQP_BTL_BDBP":  [("BTL Biên phòng", "viet_tat"), ("Bộ Tư lệnh BĐBP", "viet_tat"),
                      ("BTL Bộ đội Biên phòng", "ten_goi_khac")],
    "BQP_BTL_CSB":   [("BTL Cảnh sát biển", "viet_tat"), ("Cảnh sát biển VN", "ten_goi_khac")],
    # BQP — Quân đoàn
    "BQP_QD1":  [("Quân đoàn 1", "ten_goi_khac"), ("QĐ 1", "viet_tat"), ("QD1", "ma_ngan"),
                 ("Binh đoàn Quyết Thắng", "ten_goi_khac")],
    "BQP_QD2":  [("Quân đoàn 2", "ten_goi_khac"), ("QĐ 2", "viet_tat"), ("QD2", "ma_ngan"),
                 ("Binh đoàn Hương Giang", "ten_goi_khac")],
    "BQP_QD12": [("Quân đoàn 12", "ten_goi_khac"), ("QĐ 12", "viet_tat"), ("QD12", "ma_ngan")],
    "BQP_QD3":  [("Quân đoàn 3", "ten_goi_khac"), ("QĐ 3", "viet_tat"),
                 ("Binh đoàn Tây Nguyên", "ten_goi_khac")],
    "BQP_QD4":  [("Quân đoàn 4", "ten_goi_khac"), ("QĐ 4", "viet_tat"),
                 ("Binh đoàn Cửu Long", "ten_goi_khac")],
    # BQP — Sư đoàn / Trung đoàn
    "BQP_F308": [("Sư đoàn 308", "ten_goi_khac"), ("f308", "viet_tat"),
                 ("F308", "ma_ngan"), ("Su doan 308", "khong_dau"), ("Sư 308", "ten_goi_khac")],
    "BQP_F312": [("Sư đoàn 312", "ten_goi_khac"), ("f312", "viet_tat"), ("F312", "ma_ngan"), ("Sư 312", "ten_goi_khac")],
    "BQP_E141": [("Trung đoàn 141", "ten_goi_khac"), ("e141", "viet_tat"),
                 ("e141 f312", "ma_ngan"), ("Trung đoàn 141 Sư 312", "ten_goi_khac")],
    # BQP — Bệnh viện
    "BQP_BV108": [("BV 108", "ten_goi_khac"), ("Viện 108", "ten_goi_khac"),
                  ("BV TƯQĐ 108", "viet_tat"), ("Bệnh viện 108", "ten_goi_khac"),
                  ("Viện TW Quân đội 108", "ten_goi_khac")],
    "BQP_BV103": [("BV Quân y 103", "ten_goi_khac"), ("Viện 103", "ten_goi_khac"), ("BV 103", "ten_goi_khac")],
    "BQP_BV175": [("BV Quân y 175", "ten_goi_khac"), ("Viện 175", "ten_goi_khac"), ("BV 175", "ten_goi_khac")],
    # BQP — Biên phòng
    "BQP_BDBP_LCA": [("BĐBP Lào Cai", "viet_tat"), ("Biên phòng Lào Cai", "ten_goi_khac")],
    "BQP_BDBP_AGI": [("BĐBP An Giang", "viet_tat"), ("Biên phòng An Giang", "ten_goi_khac")],
    # OTHER — Dân sự điển hình
    "OTH_BHXH_VN": [("BHXH Việt Nam", "viet_tat"), ("Bảo hiểm XH VN", "ten_goi_khac")],
    "OTH_DH_BKHN": [("ĐHBK Hà Nội", "viet_tat"), ("Bách Khoa HN", "ten_goi_khac"),
                    ("HUST", "ma_ngan")],
}

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
            pass
        else:
            out.append(ch)
    return "".join(out)


def generate_domain_aliases(name: str, org_type: str) -> list[tuple[str, str]]:
    """Sinh biến thể hành chính theo luật nghiệp vụ thực tế."""
    variants: list[tuple[str, str]] = []

    if org_type == "BCA":
        replacements = [
            ("Công an Thành phố", [("CATP", "viet_tat"), ("CA TP", "ten_goi_khac"), ("CA", "viet_tat")]),
            ("Công an Tỉnh",      [("CA Tỉnh", "ten_goi_khac"), ("CA", "viet_tat")]),
            ("Công an Quận",      [("CAQ", "viet_tat"), ("Công an Q.", "ten_goi_khac")]),
            ("Công an Huyện",     [("CAH", "viet_tat"), ("Công an H.", "ten_goi_khac")]),
            ("Phòng Cảnh sát hình sự",
             [("PC02", "viet_tat"), ("Phòng CSHS", "ten_goi_khac")]),
            ("Phòng Cảnh sát điều tra tội phạm về ma túy",
             [("PC04", "viet_tat"), ("Phòng CS ma túy", "ten_goi_khac")]),
            ("Phòng Cảnh sát giao thông",
             [("PC08", "viet_tat"), ("Phòng CSGT", "ten_goi_khac")]),
            ("Văn phòng Cơ quan Cảnh sát điều tra",
             [("PC01", "viet_tat")]),
            ("Phòng Cảnh sát quản lý hành chính về trật tự xã hội",
             [("PC06", "viet_tat"), ("Phòng CSQLHC", "ten_goi_khac")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    elif org_type == "BQP":
        replacements = [
            ("Bộ Chỉ huy Quân sự",
             [("BCHQS", "viet_tat"), ("Bộ CHQS", "ten_goi_khac"), ("BCH Quân sự", "ten_goi_khac")]),
            ("Ban Chỉ huy Quân sự",
             [("Ban CHQS", "ten_goi_khac"), ("BCHQS", "viet_tat")]),
            ("Bộ Chỉ huy Bộ đội Biên phòng",
             [("BĐBP", "viet_tat"), ("Biên phòng", "ten_goi_khac")]),
            ("Bộ đội Biên phòng",
             [("BĐBP", "viet_tat"), ("Biên phòng", "ten_goi_khac")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    else:  # OTHER
        replacements = [
            ("Ủy ban nhân dân",         [("UBND", "viet_tat"), ("UB", "ten_goi_khac")]),
            ("Bảo hiểm Xã hội",         [("BHXH", "viet_tat")]),
            ("Sở Giáo dục và Đào tạo",  [("Sở GD&ĐT", "ten_goi_khac"), ("SGD&ĐT", "viet_tat")]),
            ("Sở Y tế",                  [("SYT", "viet_tat")]),
            ("Sở Tài chính",             [("STC", "viet_tat")]),
            ("Sở Tư pháp",               [("STP", "viet_tat")]),
            ("Sở Nội vụ",                [("SNV", "viet_tat")]),
            ("Sở Kế hoạch và Đầu tư",   [("SKH&ĐT", "viet_tat"), ("SKHĐT", "viet_tat")]),
            ("Sở Tài nguyên và Môi trường", [("STNMT", "viet_tat")]),
            ("Sở Xây dựng",              [("SXD", "viet_tat")]),
        ]
        for src, targets in replacements:
            if src in name:
                for repl, atype in targets:
                    variants.append((name.replace(src, repl), atype))

    return variants


def build_aliases(registry: list[dict]) -> list[dict]:
    raw_aliases: list[dict] = []
    counter  = 1
    seen_set: set[tuple] = set()

    for unit in registry:
        uid      = int(unit["unit_id"])
        uuid_str = unit.get("unit_uuid", "")
        code     = unit["unit_code"]
        name     = unit["canonical_name"]
        org_type = unit.get("organization_type", "OTHER")
        vf       = unit.get("valid_from", "2018-01-01")
        vt       = unit.get("valid_to", "")

        def add(alias_name: str, alias_type: str, source: str = "auto") -> None:
            nonlocal counter
            clean = alias_name.strip()
            dedup = (code, clean.lower())
            if clean and len(clean) >= 2 and dedup not in seen_set:
                seen_set.add(dedup)
                
                is_approved = source in ("manual_registry", "manual_domain", "domain_rules")
                raw_aliases.append({
                    "alias_id":         counter,
                    "unit_id":          uid,
                    "unit_uuid":        uuid_str,
                    "unit_code":        code,
                    "alias_name":       clean,
                    "alias_type":       alias_type,
                    "generator_source": source,
                    "is_ambiguous":     "KHONG",  # Sẽ được cập nhật ở bước 2
                    "source_id":        "SRC_OFFICIAL_REGISTRY" if is_approved else "SRC_SYNTHETIC_RULES",
                    "valid_from":       vf,
                    "valid_to":         vt,
                    "approved_by":      "Lead_Registrar" if is_approved else "Auto_Pipeline",
                    "alias_status":     "APPROVED" if is_approved else "CANDIDATE",
                })
                counter += 1

        # 1. Canonical
        add(name, "chinh_thuc", "manual_registry")

        # 2. Alias thủ công
        for alias_name, atype in MANUAL_ALIASES.get(code, []):
            add(alias_name, atype, "manual_domain")

        # 3. Luật nghiệp vụ
        for alias_name, atype in generate_domain_aliases(name, org_type):
            add(alias_name, atype, "domain_rules")

        # 4. Bỏ dấu
        no_acc = remove_accents(name)
        if no_acc != name:
            add(no_acc, "khong_dau", "auto_rule")

        # 5. Viết tắt
        abbr = abbreviate(name)
        if len(abbr) >= 2 and abbr != name:
            add(abbr, "viet_tat", "auto_rule")

        # 6. Typo/OCR (2 biến thể)
        for _ in range(2):
            noisy = inject_ocr(name)
            if noisy != name and len(noisy) > 3:
                add(noisy, "loi_danh_may", "noise_injector")

    # ── BƯỚC 2: TỰ ĐỘNG PHÁT HIỆN & GẮN CỜ ALIAS NHẬP NHẰNG (is_ambiguous) ───
    alias_usage = defaultdict(set)
    for a in raw_aliases:
        alias_norm = a["alias_name"].lower().strip()
        alias_usage[alias_norm].add(a["unit_code"])

    ambiguous_count = 0
    for a in raw_aliases:
        alias_norm = a["alias_name"].lower().strip()
        if len(alias_usage[alias_norm]) > 1:
            a["is_ambiguous"] = "CO"
            ambiguous_count += 1

    print(f"[Ambiguity Engine] Phát hiện {ambiguous_count:,d} bản ghi alias trỏ tới nhiều hơn 1 đơn vị → Đã gắn is_ambiguous=TRUE")

    return raw_aliases


def main() -> list[dict]:
    print("=" * 65)
    print("ALIASES — SINH TỪ ĐIỂN ALIAS QUẢN TRỊ 13 TRƯỜNG (2018 – 2026)")
    print("=" * 65)

    master_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")
    if not os.path.exists(master_path):
        print(f"[ERROR] {master_path} không tồn tại. Hãy chạy Registy.py trước.")
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
    print(f"\n[OK] unit_aliases.csv (13 cột quản trị) → {out_path}")
    return aliases


if __name__ == "__main__":
    main()
