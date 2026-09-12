"""
Sinh/Thu thập dữ liệu thô (2018 – 2026)
============================================================
Output: data_raw/raw_{year}.csv  (cho từng năm)
        data_raw/raw_ALL_2018_2026.csv  (tổng hợp)
"""
import csv
import os
import sys
import pathlib as _pathlib
from datetime import datetime
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from Config import DIR_RAW, YEAR_START, YEAR_END, CRAWL_VERSION_STR
except ImportError:
    DIR_RAW = "./data_raw"
    YEAR_START = 2018
    YEAR_END   = 2026
    CRAWL_VERSION_STR = "crawl_2018_2026"

os.makedirs(DIR_RAW, exist_ok=True)

CRAWL_VERSION = "crawl_2018_2026"
CRAWLED_AT    = datetime.now().isoformat()
YEARS         = list(range(YEAR_START, YEAR_END + 1))

# ═══════════════════════════════════════════════════════════════════════
# MASTER: 64 TỈNH/THÀNH (bao gồm Hà Tây lịch sử)
# Đây là nguồn dữ liệu sống — được dùng thực sự trong toàn bộ pipeline.
# Mỗi tuple: (province_code, province_name, is_legacy)
# is_legacy=True → chỉ xuất hiện trong dữ liệu ≤ 2008, giữ lại để map hồ sơ cũ
# ═══════════════════════════════════════════════════════════════════════

PROVINCES: list[tuple[str, str, bool]] = [
    # ── Trung tâm / Đô thị lớn ──────────────────────────────────────────
    ("HN",   "Hà Nội",                          False),
    ("HTAY", "Hà Tây",                          True),   # Sáp nhập vào HN 08/2008
    ("HCM",  "Thành phố Hồ Chí Minh",           False),
    ("DN",   "Đà Nẵng",                         False),
    ("HP",   "Hải Phòng",                       False),
    ("CT",   "Cần Thơ",                         False),
    # ── Đông Nam Bộ ─────────────────────────────────────────────────────
    ("DNAI", "Đồng Nai",                        False),
    ("BD",   "Bình Dương",                      False),
    ("VT",   "Bà Rịa - Vũng Tàu",              False),
    ("TNI",  "Tây Ninh",                        False),
    ("BPC",  "Bình Phước",                      False),
    # ── Đồng bằng sông Cửu Long ────────────────────────────────────────
    ("AGI",  "An Giang",                        False),
    ("KGI",  "Kiên Giang",                      False),
    ("CM",   "Cà Mau",                          False),
    ("HAG",  "Hậu Giang",                       False),
    ("ST",   "Sóc Trăng",                       False),
    ("BL",   "Bạc Liêu",                        False),
    ("TV",   "Trà Vinh",                        False),
    ("VL",   "Vĩnh Long",                       False),
    ("BT",   "Bến Tre",                         False),
    ("TG",   "Tiền Giang",                      False),
    ("DT",   "Đồng Tháp",                       False),
    ("LA",   "Long An",                         False),
    # ── Tây Nguyên ──────────────────────────────────────────────────────
    ("DLA",  "Đắk Lắk",                         False),
    ("GLA",  "Gia Lai",                         False),
    ("LD",   "Lâm Đồng",                        False),
    ("KT",   "Kon Tum",                         False),
    ("DNO",  "Đắk Nông",                        False),
    # ── Duyên hải Nam Trung Bộ ─────────────────────────────────────────
    ("KHA",  "Khánh Hòa",                       False),
    ("BTN",  "Bình Thuận",                      False),
    ("NTN",  "Ninh Thuận",                      False),
    ("PY",   "Phú Yên",                         False),
    ("BDH",  "Bình Định",                       False),
    ("QNG",  "Quảng Ngãi",                      False),
    ("QNA",  "Quảng Nam",                       False),
    ("TTH",  "Thừa Thiên Huế",                  False),
    # ── Bắc Trung Bộ ────────────────────────────────────────────────────
    ("QTR",  "Quảng Trị",                       False),
    ("QBI",  "Quảng Bình",                      False),
    ("HT",   "Hà Tĩnh",                         False),
    ("NA",   "Nghệ An",                         False),
    ("TH",   "Thanh Hóa",                       False),
    # ── Đồng bằng sông Hồng ────────────────────────────────────────────
    ("QNH",  "Quảng Ninh",                      False),
    ("HD",   "Hải Dương",                       False),
    ("HY",   "Hưng Yên",                        False),
    ("TBI",  "Thái Bình",                       False),
    ("NDI",  "Nam Định",                        False),
    ("HNA",  "Hà Nam",                          False),
    ("NB",   "Ninh Bình",                       False),
    ("VP",   "Vĩnh Phúc",                       False),
    ("BNI",  "Bắc Ninh",                        False),
    ("BGI",  "Bắc Giang",                       False),
    # ── Trung du & miền núi phía Bắc ───────────────────────────────────
    ("PTH",  "Phú Thọ",                         False),
    ("TNG",  "Thái Nguyên",                     False),
    ("YBI",  "Yên Bái",                         False),
    ("TQ",   "Tuyên Quang",                     False),
    ("HGI",  "Hà Giang",                        False),
    ("CBG",  "Cao Bằng",                        False),
    ("LSO",  "Lạng Sơn",                        False),
    ("BKN",  "Bắc Kạn",                         False),
    ("SLA",  "Sơn La",                          False),
    ("DB",   "Điện Biên",                       False),
    ("LCH",  "Lai Châu",                        False),
    ("LCA",  "Lào Cai",                         False),
]

# Index nhanh để tra cứu tên từ mã
PROVINCE_NAME: dict[str, str] = {code: name for code, name, _ in PROVINCES}
PROVINCE_LEGACY: dict[str, bool] = {code: legacy for code, _, legacy in PROVINCES}

# Các tỉnh có mặt nước/biên giới đất liền → cần Biên phòng
COASTAL_PROVINCES = {
    "HN", "HCM", "DN", "HP", "CT", "DNAI", "BD", "QNH", "TTH", "KHA",
    "AGI", "KGI", "CM", "HAG", "ST", "BL", "TV", "VL", "BT", "TG", "DT", "LA",
    "QNA", "QNG", "BDH", "PY", "BTN", "NTN", "VT", "TNI", "QBI", "QTR",
    "HT", "NA", "TH", "LCA", "CBG", "LSO", "HGI", "DB", "LCH",
}

# ── Mẫu quận/huyện đại diện (để tạo đơn vị cấp quận) ──────────────────────
DISTRICTS_SAMPLE: list[tuple[str, list[tuple[str, str]]]] = [
    ("HN",   [("BDG", "Ba Đình"), ("HK", "Hoàn Kiếm"), ("CG", "Cầu Giấy"),
              ("DD",  "Đống Đa"),  ("TX", "Thanh Xuân"), ("GL", "Gia Lâm"),
              ("SOC", "Sóc Sơn"), ("DDA", "Đông Anh")]),
    ("HTAY", [("HDO", "Hà Đông"), ("ST", "Sơn Tây"), ("BV", "Ba Vì"), ("CT", "Chương Mỹ")]),
    ("HCM",  [("Q1",  "Quận 1"),  ("Q3",  "Quận 3"),  ("Q7",  "Quận 7"),
              ("BT",  "Bình Thạnh"), ("TB", "Tân Bình"), ("GV", "Gò Vấp"),
              ("BC",  "Bình Chánh"), ("HM", "Hóc Môn")]),
    ("DN",   [("HC",  "Hải Châu"), ("TK", "Thanh Khê"), ("NHS", "Ngũ Hành Sơn"), ("CL", "Cẩm Lệ")]),
    ("HP",   [("HB",  "Hồng Bàng"), ("NG", "Ngô Quyền"), ("LC", "Lê Chân"), ("AD", "An Dương")]),
    ("DNAI", [("BH",  "Biên Hòa"), ("LK", "Long Khánh"), ("LT", "Long Thành"), ("TRB", "Trảng Bom")]),
    ("BD",   [("TDM", "Thủ Dầu Một"), ("DA", "Dĩ An"), ("TA", "Thuận An"), ("BCT", "Bến Cát")]),
]

# ── Phòng nghiệp vụ Công an tỉnh/thành ────────────────────────────────────
BCA_DEPT_PROV: list[tuple[str, str]] = [
    ("PC01", "Văn phòng Cơ quan Cảnh sát điều tra"),
    ("PC02", "Phòng Cảnh sát hình sự"),
    ("PC03", "Phòng Cảnh sát kinh tế"),
    ("PC04", "Phòng Cảnh sát điều tra tội phạm về ma túy"),
    ("PC06", "Phòng Cảnh sát quản lý hành chính về trật tự xã hội"),
    ("PC07", "Phòng Cảnh sát Phòng cháy chữa cháy và Cứu nạn cứu hộ"),
    ("PC08", "Phòng Cảnh sát giao thông"),
    ("PA01", "Phòng An ninh đối ngoại"),
    ("PA02", "Phòng An ninh nội địa"),
    ("PA03", "Phòng An ninh chính trị nội bộ"),
    ("PA05", "Phòng An ninh mạng và phòng chống tội phạm công nghệ cao"),
]

# ── Sở ngành dân sự ────────────────────────────────────────────────────────
CIVIL_DEPTS: list[tuple[str, str]] = [
    ("SYT",    "Sở Y tế"),
    ("SGD",    "Sở Giáo dục và Đào tạo"),
    ("STC",    "Sở Tài chính"),
    ("STP",    "Sở Tư pháp"),
    ("SKH",    "Sở Kế hoạch và Đầu tư"),
    ("SXD",    "Sở Xây dựng"),
    ("STNMT",  "Sở Tài nguyên và Môi trường"),
    ("SNV",    "Sở Nội vụ"),
    ("SGTVT",  "Sở Giao thông vận tải"),
    ("SCT",    "Sở Công Thương"),
    ("SNNPTNT","Sở Nông nghiệp và Phát triển nông thôn"),
    ("SLĐTBXH","Sở Lao động - Thương binh và Xã hội"),
    ("SVHTTDL","Sở Văn hóa Thể thao và Du lịch"),
    ("STTTT",  "Sở Thông tin và Truyền thông"),
    ("SKHCN",  "Sở Khoa học và Công nghệ"),
]


# ═══════════════════════════════════════════════════════════════════════
# HÀM TIỆN ÍCH
# ═══════════════════════════════════════════════════════════════════════

def _ref(label: str, year: int, legacy: bool = False) -> str:
    """Tạo source_ref chuẩn."""
    if legacy:
        return f"legacy_record_{label}"
    return f"{label}_{year}"


def _source_url(year: int) -> str:
    return f"https://dichvucong.gov.vn/archive/{year}"


def infer_unit_level(name: str, org_type: str, province_code: str = "") -> str:
    """
    Phỏng đoán cấp đơn vị từ tên + mã tỉnh.
      ministry / central / province / district / commune / department
      division / brigade / regiment / corps / school / hospital / other
    PROVINCES được dùng để nhận diện cấp tỉnh ngay cả khi tên không chứa
    chữ "tỉnh"/"thành phố" (vd: "Công an Đà Nẵng", "BCHQS Nghệ An").
    """
    nl = name.lower()

    if org_type == "BCA":
        # Cấp Bộ: Cục, Tổng cục, Bộ Tư lệnh trực thuộc BCA
        if any(k in nl for k in ["cục ", "tổng cục", "bộ tư lệnh", "văn phòng cơ quan"]):
            return "ministry"
        if "học viện" in nl or "trường" in nl:
            return "school"
        if "bệnh viện" in nl:
            return "hospital"
        if any(k in nl for k in ["công an thành phố", "công an tỉnh"]):
            return "province"
        # Nhận diện cấp tỉnh qua tên tỉnh trực tiếp (không cần từ "tỉnh")
        if province_code and province_code not in ("", "HTAY"):
            p_name = PROVINCE_NAME.get(province_code, "").lower()
            if p_name and p_name in nl:
                return "province"
        if any(k in nl for k in ["công an quận", "công an huyện",
                                  "công an thị xã", "công an thị trấn"]):
            return "district"
        if any(k in nl for k in ["công an xã", "công an phường"]):
            return "commune"
        if any(k in nl for k in ["phòng cảnh sát", "phòng an ninh"]):
            return "department"
        return "other"

    if org_type == "BQP":
        # Cấp chiến lược: Bộ Tổng Tham mưu, Tổng cục, Bộ Tư lệnh QK/BĐBP/CSB
        if any(k in nl for k in ["bộ tổng tham mưu", "tổng cục",
                                  "bộ tư lệnh quân khu", "bộ tư lệnh thủ đô",
                                  "bộ tư lệnh bộ đội biên phòng",
                                  "bộ tư lệnh cảnh sát biển",
                                  "quân chủng"]):
            return "central"
        if "quân đoàn" in nl or "binh đoàn" in nl:
            return "corps"
        if any(k in nl for k in ["sư đoàn", "bộ chỉ huy quân sự"]):
            return "division"
        if "lữ đoàn" in nl:
            return "brigade"
        if any(k in nl for k in ["trung đoàn", "ban chỉ huy quân sự"]):
            return "regiment"
        if "tiểu đoàn" in nl:
            return "battalion"
        if "học viện" in nl or "trường" in nl:
            return "school"
        if "bệnh viện" in nl:
            return "hospital"
        if "bộ đội biên phòng" in nl or "biên phòng" in nl:
            if province_code:
                return "province"
        return "other"

    # OTHER (dân sự)
    if any(k in nl for k in ["tổng cục", "tòa án nhân dân tối cao",
                              "viện kiểm sát nhân dân tối cao",
                              "kho bạc nhà nước"]):
        return "central"
    if any(k in nl for k in ["ủy ban nhân dân", "hội đồng nhân dân",
                              "tòa án nhân dân", "viện kiểm sát nhân dân",
                              "sở y tế", "sở giáo dục", "sở tài chính",
                              "sở ", "bảo hiểm xã hội"]):
        return "province"
    if "bệnh viện" in nl:
        return "hospital"
    if "đại học" in nl or "trường" in nl:
        return "school"
    return "other"


# ═══════════════════════════════════════════════════════════════════════
# BỘ SINH RECORDS TỪNG NĂM
# ═══════════════════════════════════════════════════════════════════════

def build_records_for_year(year: int) -> list[dict]:
    records: list[dict] = []

    def add(code: str, name: str, org_type: str, ref: str,
            province_code: str = "") -> None:
        records.append({
            "unit_code_raw":      code,
            "unit_name_raw":      name,
            "organization_type":  org_type,
            "unit_level":         infer_unit_level(name, org_type, province_code),
            "year":               year,
            "source_url":         _source_url(year),
            "source_type":        "generated_catalog",
            "source_ref":         ref,
            "crawled_at":         CRAWLED_AT,
            "crawl_version":      CRAWL_VERSION,
        })

    # ── A. KHỐI BỘ CÔNG AN (BCA) ────────────────────────────────────────────

    # Cục nghiệp vụ trực thuộc Bộ
    bca_bo_units = [
        ("BCA_C01", "Văn phòng Cơ quan Cảnh sát điều tra Bộ Công an"),
        ("BCA_C02", "Cục Cảnh sát hình sự"),
        ("BCA_C03", "Cục Cảnh sát điều tra tội phạm về tham nhũng, kinh tế, buôn lậu"),
        ("BCA_C04", "Cục Cảnh sát điều tra tội phạm về ma túy"),
        ("BCA_C06", "Cục Cảnh sát quản lý hành chính về trật tự xã hội"),
        ("BCA_C07", "Cục Cảnh sát Phòng cháy chữa cháy và Cứu nạn cứu hộ"),
        ("BCA_C08", "Cục Cảnh sát giao thông"),
        ("BCA_C10", "Cục Cảnh sát quản lý trại giam, cơ sở giáo dục bắt buộc"),
        ("BCA_A01", "Văn phòng Cơ quan An ninh điều tra Bộ Công an"),
        ("BCA_A02", "Cục An ninh chính trị nội bộ"),
        ("BCA_A03", "Cục An ninh kinh tế"),
        ("BCA_A05", "Cục An ninh mạng và phòng chống tội phạm công nghệ cao"),
        ("BCA_K01", "Bộ Tư lệnh Cảnh vệ"),
        ("BCA_K02", "Bộ Tư lệnh Cảnh sát cơ động"),
    ]
    for code, name in bca_bo_units:
        add(code, name, "BCA", _ref("nd_bca", year))

    # Học viện / Trường / Bệnh viện CAND
    add("BCA_T01",   "Học viện An ninh nhân dân",               "BCA", _ref("catalog", year))
    add("BCA_T02",   "Học viện Cảnh sát nhân dân",              "BCA", _ref("catalog", year))
    add("BCA_T03",   "Học viện Chính trị Công an nhân dân",     "BCA", _ref("catalog", year))
    add("BCA_BV198", "Bệnh viện 19-8 Bộ Công an",              "BCA", _ref("catalog", year))
    add("BCA_BV304", "Bệnh viện 30-4 Bộ Công an",              "BCA", _ref("catalog", year))

    # Công an 64 tỉnh/thành và phòng nghiệp vụ
    for p_code, p_name, is_legacy in PROVINCES:
        ref = _ref("dvc", year, legacy=is_legacy)
        ca_code = f"BCA_CA_{p_code}"

        # Tên đơn vị cấp tỉnh — lưu ý: một số tỉnh dùng "Thành phố", một số dùng "Tỉnh"
        # TTH (Thừa Thiên Huế) → "Thành phố Huế" từ 2025 (theo nghị quyết 931)
        city_provinces = {"HN", "HCM", "DN", "HP", "CT"}
        if year >= 2025:
            city_provinces = city_provinces | {"TTH"}   # TP Huế TW từ 1/7/2025
        prefix_ca = "Công an Thành phố" if p_code in city_provinces else "Công an Tỉnh"
        if p_code == "HTAY":
            prefix_ca = "Công an Tỉnh"  # Hà Tây là tỉnh lịch sử
        # Tên tỉnh hiển thị: TTH từ 2025 dùng tên mới "Huế"
        p_display = "Huế" if (p_code == "TTH" and year >= 2025) else p_name

        ca_name = f"{prefix_ca} {p_display}"
        add(ca_code, ca_name, "BCA", ref, province_code=p_code)

        # Phòng nghiệp vụ trực thuộc Công an tỉnh
        for dept_code, dept_name in BCA_DEPT_PROV:
            add(
                f"{ca_code}_{dept_code}",
                f"{dept_name} - {ca_name}",
                "BCA", ref, province_code=p_code,
            )

    # Công an quận/huyện đại diện
    for p_code, dist_list in DISTRICTS_SAMPLE:
        p_name = PROVINCE_NAME.get(p_code, "")
        is_legacy = PROVINCE_LEGACY.get(p_code, False)
        ref = _ref("dvc", year, legacy=is_legacy)
        for d_code, d_name in dist_list:
            prefix = (
                "Công an Quận"   if "Quận" in d_name    else
                "Công an Thị xã" if "Thị xã" in d_name  else
                "Công an Huyện"
            )
            add(
                f"BCA_CA_{p_code}_{d_code}",
                f"{prefix} {d_name} - {p_name}",
                "BCA", ref, province_code=p_code,
            )

    # Sự kiện đặc biệt theo năm — BCA
    if year >= 2021:
        add("BCA_CA_HCM_THUDUC",
            "Công an Thành phố Thủ Đức - Thành phố Hồ Chí Minh",
            "BCA", _ref("nq_1111", year), province_code="HCM")

    # Thừa Thiên Huế → TP Huế (TP TW từ 1/7/2025)
    if year >= 2025:
        add("BCA_CA_HUE",
            "Công an Thành phố Huế",
            "BCA", _ref("nq_hue_2025", year), province_code="TTH")

    # Đơn vị mới 2026 (tái cơ cấu đầu 2026)
    if year >= 2026:
        add("BCA_C11", "Cục Cảnh sát phòng chống tội phạm công nghệ cao",
            "BCA", _ref("nd_bca_2026", year))
        # PC11 tại các Công an tỉnh/thành từ 2026
        for p_code, p_name, is_legacy in PROVINCES:
            if is_legacy:
                continue
            ca_code = f"BCA_CA_{p_code}"
            # TTH cũng là TP từ 2026 (vẫn là TP TW)
            city_prov_2026 = {"HN", "HCM", "DN", "HP", "CT", "TTH"}
            ca_name = (
                f"Công an Thành phố {p_name}"
                if p_code in city_prov_2026
                else f"Công an Tỉnh {p_name}"
            )
            add(
                f"{ca_code}_PC11",
                f"Phòng Cảnh sát phòng chống tội phạm công nghệ cao - {ca_name}",
                "BCA", _ref("nd_bca_2026", year), province_code=p_code,
            )

    # ── B. KHỐI BỘ QUỐC PHÒNG (BQP) ────────────────────────────────────────

    bqp_bo_units = [
        ("BQP_BTTM",    "Bộ Tổng Tham mưu Quân đội nhân dân Việt Nam"),
        ("BQP_TCCT",    "Tổng cục Chính trị Quân đội nhân dân Việt Nam"),
        ("BQP_TCHQ",    "Tổng cục Hậu cần"),
        ("BQP_TCKT",    "Tổng cục Kỹ thuật"),
        ("BQP_TCCNQP",  "Tổng cục Công nghiệp Quốc phòng"),
    ]
    for code, name in bqp_bo_units:
        add(code, name, "BQP", _ref("catalog", year))

    for qk in [1, 2, 3, 4, 5, 7, 9]:
        add(f"BQP_BTL_QK{qk}", f"Bộ Tư lệnh Quân khu {qk}",
            "BQP", _ref("catalog", year))

    add("BQP_BTL_TDHN",  "Bộ Tư lệnh Thủ đô Hà Nội",             "BQP", _ref("catalog", year))
    add("BQP_BTL_BDBP",  "Bộ Tư lệnh Bộ đội Biên phòng",          "BQP", _ref("catalog", year))
    add("BQP_BTL_CSB",   "Bộ Tư lệnh Cảnh sát biển Việt Nam",     "BQP", _ref("catalog", year))
    add("BQP_HQ",        "Quân chủng Hải quân",                    "BQP", _ref("catalog", year))
    add("BQP_PKKQ",      "Quân chủng Phòng không - Không quân",    "BQP", _ref("catalog", year))

    # Quân đoàn — sáp nhập QĐ1+QĐ2 → QĐ12 từ cuối 2023
    if year <= 2023:
        add("BQP_QD1", "Quân đoàn 1 (Binh đoàn Quyết Thắng)", "BQP", _ref("catalog", year))
        add("BQP_QD2", "Quân đoàn 2 (Binh đoàn Hương Giang)",  "BQP", _ref("catalog", year))
    else:
        add("BQP_QD12", "Quân đoàn 12", "BQP", _ref("catalog", year))

    add("BQP_QD3", "Quân đoàn 3 (Binh đoàn Tây Nguyên)", "BQP", _ref("catalog", year))
    add("BQP_QD4", "Quân đoàn 4 (Binh đoàn Cửu Long)",   "BQP", _ref("catalog", year))

    # Sư đoàn / Trung đoàn
    # Tên đơn vị chuẩn (không gắn tên quân đoàn cha vào tên),
    add("BQP_F308", "Sư đoàn 308", "BQP", _ref("catalog", year))
    add("BQP_F312", "Sư đoàn 312", "BQP", _ref("catalog", year))
    add("BQP_F320", "Sư đoàn 320", "BQP", _ref("catalog", year))
    add("BQP_F330", "Sư đoàn 330", "BQP", _ref("catalog", year))
    add("BQP_F9",   "Sư đoàn 9",   "BQP", _ref("catalog", year))
    add("BQP_E141", "Trung đoàn 141", "BQP", _ref("catalog", year))

    # Học viện / Bệnh viện Quân đội
    add("BQP_HVQP",   "Học viện Quốc phòng",              "BQP", _ref("catalog", year))
    add("BQP_HVKTQS", "Học viện Kỹ thuật Quân sự",        "BQP", _ref("catalog", year))
    add("BQP_HVQY",   "Học viện Quân y",                   "BQP", _ref("catalog", year))
    add("BQP_BV108",  "Bệnh viện Trung ương Quân đội 108", "BQP", _ref("catalog", year))
    add("BQP_BV103",  "Bệnh viện Quân y 103",              "BQP", _ref("catalog", year))
    add("BQP_BV105",  "Bệnh viện Quân y 105",              "BQP", _ref("catalog", year))
    add("BQP_BV175",  "Bệnh viện Quân y 175",              "BQP", _ref("catalog", year))
    add("BQP_BV354",  "Bệnh viện Quân y 354",              "BQP", _ref("catalog", year))

    # BCHQS tỉnh và Biên phòng — dùng PROVINCES trực tiếp
    for p_code, p_name, is_legacy in PROVINCES:
        ref = _ref("dvc", year, legacy=is_legacy)
        add(f"BQP_BCH_{p_code}",
            f"Bộ Chỉ huy Quân sự {p_name}",
            "BQP", ref, province_code=p_code)

        # Biên phòng chỉ sinh cho tỉnh có biển/biên giới
        if p_code in COASTAL_PROVINCES:
            add(f"BQP_BDBP_{p_code}",
                f"Bộ Chỉ huy Bộ đội Biên phòng {p_name}",
                "BQP", ref, province_code=p_code)

    # Ban CHQS quận/huyện đại diện
    for p_code, dist_list in DISTRICTS_SAMPLE:
        p_name = PROVINCE_NAME.get(p_code, "")
        is_legacy = PROVINCE_LEGACY.get(p_code, False)
        ref = _ref("dvc", year, legacy=is_legacy)
        for d_code, d_name in dist_list:
            add(
                f"BQP_BCH_{p_code}_{d_code}",
                f"Ban Chỉ huy Quân sự {d_name} - {p_name}",
                "BQP", ref, province_code=p_code,
            )

    if year >= 2021:
        add("BQP_BCH_HCM_THUDUC",
            "Ban Chỉ huy Quân sự Thành phố Thủ Đức - Thành phố Hồ Chí Minh",
            "BQP", _ref("nq_1111", year), province_code="HCM")

    # Bộ Chỉ huy QS Thành phố Huế từ 2025
    if year >= 2025:
        add("BQP_BCH_HUE",
            "Bộ Chỉ huy Quân sự Thành phố Huế",
            "BQP", _ref("nq_hue_2025", year), province_code="TTH")

    # ── C. KHỐI DÂN SỰ (OTHER) ─────────────────────────────────────────────

    other_central = [
        ("OTH_BHXH_VN",  "Bảo hiểm Xã hội Việt Nam"),
        ("OTH_TCHQ_VN",  "Tổng cục Hải quan"),
        ("OTH_TCT_VN",   "Tổng cục Thuế"),
        ("OTH_KBNN_VN",  "Kho bạc Nhà nước"),
        ("OTH_TANDTC",   "Tòa án nhân dân tối cao"),
        ("OTH_VKSNDTC",  "Viện kiểm sát nhân dân tối cao"),
        ("OTH_BV_BM",    "Bệnh viện Bạch Mai"),
        ("OTH_BV_CR",    "Bệnh viện Chợ Rẫy"),
        ("OTH_BV_K",     "Bệnh viện K"),
        ("OTH_DH_BKHN",  "Đại học Bách khoa Hà Nội"),
        ("OTH_DH_QGHN",  "Đại học Quốc gia Hà Nội"),
        ("OTH_DH_QGHCM", "Đại học Quốc gia Thành phố Hồ Chí Minh"),
    ]
    for code, name in other_central:
        add(code, name, "OTHER", _ref("catalog", year))

    # UBND, BHXH và Sở ngành 64 tỉnh/thành — dùng PROVINCES trực tiếp
    for p_code, p_name, is_legacy in PROVINCES:
        ref = _ref("dvc", year, legacy=is_legacy)
        add(f"OTH_UBND_{p_code}",  f"Ủy ban nhân dân {p_name}", "OTHER", ref)
        add(f"OTH_BHXH_{p_code}",  f"Bảo hiểm Xã hội {p_name}", "OTHER", ref)
        for s_code, s_name in CIVIL_DEPTS:
            add(f"OTH_{s_code}_{p_code}", f"{s_name} {p_name}", "OTHER", ref)

    # UBND quận/huyện đại diện
    for p_code, dist_list in DISTRICTS_SAMPLE:
        p_name = PROVINCE_NAME.get(p_code, "")
        is_legacy = PROVINCE_LEGACY.get(p_code, False)
        ref = _ref("dvc", year, legacy=is_legacy)
        for d_code, d_name in dist_list:
            add(f"OTH_UBND_{p_code}_{d_code}", f"Ủy ban nhân dân {d_name} - {p_name}", "OTHER", ref)
            add(f"OTH_BHXH_{p_code}_{d_code}", f"Bảo hiểm Xã hội {d_name} - {p_name}", "OTHER", ref)

    if year >= 2021:
        add("OTH_UBND_HCM_THUDUC",
            "Ủy ban nhân dân Thành phố Thủ Đức - Thành phố Hồ Chí Minh",
            "OTHER", _ref("nq_1111", year))

    # HĐND, TAND, VKSND cấp tỉnh
    for p_code, p_name, is_legacy in PROVINCES:
        ref = _ref("dvc", year, legacy=is_legacy)
        p_display = "Huế" if (p_code == "TTH" and year >= 2025) else p_name
        add(f"OTH_HDND_{p_code}",  f"Hội đồng nhân dân {p_display}",         "OTHER", ref)
        add(f"OTH_TAND_{p_code}",  f"Tòa án nhân dân {p_display}",            "OTHER", ref)
        add(f"OTH_VKSND_{p_code}", f"Viện kiểm sát nhân dân {p_display}",     "OTHER", ref)

    return records


# ═══════════════════════════════════════════════════════════════════════
# I/O HELPERS
# ═══════════════════════════════════════════════════════════════════════

def save_csv(records: list[dict], filepath: str) -> None:
    if not records:
        return
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main() -> list[dict]:
    print("=" * 65)
    print(f"CRAWL v2 — XUẤT DỮ LIỆU ĐƠN VỊ 64 TỈNH THÀNH ({YEAR_START} – {YEAR_END})")
    print("=" * 65)

    all_records: list[dict] = []

    for yr in YEARS:
        recs = build_records_for_year(yr)
        all_records.extend(recs)

        out_path = os.path.join(DIR_RAW, f"raw_{yr}.csv")
        save_csv(recs, out_path)

        bca_c = sum(1 for r in recs if r["organization_type"] == "BCA")
        bqp_c = sum(1 for r in recs if r["organization_type"] == "BQP")
        oth_c = sum(1 for r in recs if r["organization_type"] == "OTHER")
        print(f"  [{yr}] {len(recs):5d} records  |  BCA: {bca_c:4d}  BQP: {bqp_c:4d}  OTHER: {oth_c:4d}  → {out_path}")

    combined_path = os.path.join(DIR_RAW, f"raw_ALL_{YEAR_START}_{YEAR_END}.csv")
    save_csv(all_records, combined_path)

    # Thống kê unit_level
    from collections import Counter
    level_cnt = Counter(r["unit_level"] for r in all_records)
    print("\nPhân bổ unit_level:")
    for lvl, cnt in sorted(level_cnt.items()):
        print(f"  {lvl:20s}: {cnt:6,d}")

    print("\n" + "=" * 65)
    print(f"HOÀN THÀNH: {len(YEARS)} file năm + 1 file tổng hợp")
    print(f"TỔNG CỘNG : {len(all_records):,d} records → {combined_path}")
    print("=" * 65)
    return all_records


if __name__ == "__main__":
    main()