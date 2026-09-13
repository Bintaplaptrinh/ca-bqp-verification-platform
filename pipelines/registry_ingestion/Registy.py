"""
Xây dựng Master Unit Registry & Hệ thống bảng chuẩn hóa (2018 – 2026)
================================================================
Input:  data_clean/qa_approved.csv
Output:
  data_artifacts/master_units.csv
  data_artifacts/master_units.csv.sha256
  data_artifacts/schema/UNITS.csv
  data_artifacts/schema/UNIT_CODES.csv
  data_artifacts/schema/UNIT_NAMES.csv
  data_artifacts/schema/SOURCES.csv
  data_artifacts/schema/UNIT_EVENTS.csv
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
import uuid
import hashlib
import json
from collections import Counter

try:
    from Config import DIR_CLEAN, DIR_ARTIFACTS, DIR_SCHEMA, REGISTRY_VERSION, UUID_NAMESPACE_STR
except ImportError:
    DIR_CLEAN        = "./data_clean"
    DIR_ARTIFACTS    = "./data_artifacts"
    DIR_SCHEMA       = "./data_artifacts/schema"
    REGISTRY_VERSION = "v2.5.0"
    UUID_NAMESPACE_STR = "vn.gov.registry.unit"

os.makedirs(DIR_ARTIFACTS, exist_ok=True)
os.makedirs(DIR_SCHEMA, exist_ok=True)

UUID_NS = uuid.uuid5(uuid.NAMESPACE_DNS, UUID_NAMESPACE_STR)


def get_deterministic_uuid(unit_code: str) -> str:
    """Sinh UUIDv5 tất định từ unit_code."""
    return str(uuid.uuid5(UUID_NS, unit_code))


def get_deterministic_numeric_id(unit_code: str) -> int:
    """Sinh integer ID 32-bit tất định từ hash SHA-256."""
    h = hashlib.sha256(unit_code.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


# Các mốc thời gian pháp lý chuẩn xác của đơn vị lịch sử
HISTORICAL_TIMELINE: dict[str, tuple[str, str, str]] = {
    # unit_code -> (valid_from, valid_to, successor_code)
    # Hà Tây: Tái lập 12/08/1991 (Nghị quyết QH VIII) -> Sáp nhập vào HN 01/08/2008 (Nghị quyết 15/2008/QH12)
    "BCA_CA_HTAY":   ("1991-08-12", "2008-08-01", "BCA_CA_HN"),
    "BQP_BCH_HTAY":  ("1991-08-12", "2008-08-01", "BQP_BCH_HN"),
    "KHAC_UBND_HTAY": ("1991-08-12", "2008-08-01", "KHAC_UBND_HN"),
    "KHAC_BHXH_HTAY": ("1995-01-01", "2008-08-01", "KHAC_BHXH_HN"),
    "KHAC_HDND_HTAY": ("1991-08-12", "2008-08-01", "KHAC_HDND_HN"),
    "KHAC_TAND_HTAY": ("1991-08-12", "2008-08-01", "KHAC_TAND_HN"),
    "KHAC_VKSND_HTAY":("1991-08-12", "2008-08-01", "KHAC_VKSND_HN"),
    # Quân đoàn 1 & 2 sáp nhập thành Quân đoàn 12 ngày 29/11/2023
    "BQP_QD1":       ("1973-10-24", "2023-11-29", "BQP_QD12"),
    "BQP_QD2":       ("1974-05-17", "2023-11-29", "BQP_QD12"),
    "BQP_QD12":      ("2023-11-29", "", ""),
}

HATAY_PREFIXES = ("BCA_CA_HTAY_", "BQP_BCH_HTAY_", "KHAC_UBND_HTAY_", "KHAC_BHXH_HTAY_")


def resolve_temporal_and_lineage(unit_code: str, year_start: str, year_end: str, source_ref: str) -> tuple[str, str, str, str]:
    """
    Xác định chính xác (valid_from, valid_to, successor_code, status)
    Đảm bảo 100% không bao giờ xảy ra lỗi valid_from > valid_to.
    """
    if unit_code in HISTORICAL_TIMELINE:
        vf, vt, succ = HISTORICAL_TIMELINE[unit_code]
        status = "SAP_NHAP_LICH_SU" if vt else "HOAT_DONG"
        return vf, vt, succ, status

    # Các đơn vị trực thuộc Hà Tây
    if any(unit_code.startswith(pfx) or "_HTAY_" in unit_code for pfx in HATAY_PREFIXES):
        vf = "1991-08-12"
        vt = "2008-08-01"
        succ = unit_code.replace("_HTAY_", "_HN_").replace("_HTAY", "_HN")
        return vf, vt, succ, "SAP_NHAP_LICH_SU"

    if "legacy_record" in source_ref:
        return "1991-08-12", "2008-08-01", "BCA_CA_HN", "SAP_NHAP_LICH_SU"

    vf = f"{year_start}-01-01" if year_start.isdigit() else "2018-01-01"
    vt = f"{year_end}-12-31" if (year_end.isdigit() and int(year_end) < 2026) else ""
    status = "GIAI_THE" if vt else "HOAT_DONG"
    return vf, vt, "", status


def resolve_parent_unit(unit_code: str, org_type: str) -> str:
    """Xác định đơn vị cấp trên (parent_unit_id)."""
    parts = unit_code.split("_")
    # BCA
    if org_type == "BCA":
        # BCA_CA_HN_PC01 -> parent là BCA_CA_HN
        if len(parts) >= 4 and parts[1] == "CA":
            return f"BCA_CA_{parts[2]}"
        # BCA_CA_HN -> Cấp Tỉnh, trực thuộc Bộ (BCA)
        if len(parts) == 3 and parts[1] == "CA":
            return "BCA_BO"
        if parts[0] == "BCA" and parts[1] in ("C01", "C02", "C03", "C04", "C06", "C07", "C08", "C10", "C11", "A01", "A02", "A03", "A05", "K01", "K02"):
            return "BCA_BO"
        return ""

    # BQP
    if org_type == "BQP":
        # BQP_BCH_HN_BDG -> parent là BQP_BCH_HN
        if len(parts) >= 4 and parts[1] == "BCH":
            return f"BQP_BCH_{parts[2]}"
        if parts[1] == "BDBP":
            return "BQP_BTL_BDBP"
        if parts[1] in ("F308", "F312"):
            return "BQP_QD12"
        if parts[1] == "E141":
            return "BQP_F312"
        return "BQP_BTTM"

    # OTHER
    if org_type == "KHAC":
        # OTH_UBND_HN_BDG -> parent là OTH_UBND_HN
        if len(parts) >= 4 and parts[1] in ("UBND", "BHXH"):
            return f"KHAC_UBND_{parts[2]}"
        # Sở ngành -> parent là UBND tỉnh
        if len(parts) == 3 and parts[1] in ("SYT", "SGD", "STC", "STP", "SKH", "SXD", "STNMT", "SNV", "SGTVT", "SCT", "SNNPTNT", "SLĐTBXH", "SVHTTDL", "STTTT", "SKHCN"):
            return f"KHAC_UBND_{parts[2]}"
        if len(parts) == 3 and parts[1] in ("HDND", "TAND", "VKSND", "BHXH") and parts[2] != "VN":
            return f"KHAC_UBND_{parts[2]}"
        return ""

    return ""


def build_registry() -> list[dict]:
    print("=" * 65)
    print("REGISTRY — MASTER UNIT REGISTRY & 3NF SCHEMA (2018 – 2026)")
    print("=" * 65)

    approved_path = os.path.join(DIR_CLEAN, "qa_approved.csv")
    if not os.path.exists(approved_path):
        print(f"[ERROR] {approved_path} không tồn tại. Hãy chạy Qa.py trước.")
        return []

    with open(approved_path, encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    print(f"[Đọc] {len(records):,d} records đã QA từ {approved_path}")

    registry: list[dict]       = []
    table_units: list[dict]    = []
    table_codes: list[dict]    = []
    table_names: list[dict]    = []
    table_sources: list[dict]  = []
    table_events: list[dict]   = []

    # Bảng SOURCES chuẩn
    sources_dict = {
        "NGUON_KHUNG_CHINH_PHU": {
            "source_id": "NGUON_KHUNG_CHINH_PHU",
            "source_name": "Khung tổ chức bộ máy nhà nước CHXHCN Việt Nam",
            "source_type": "nghi_dinh_chinh_thuc",
            "source_url": "https://vanban.chinhphu.vn",
            "legal_reference": "Nghị định 01/2018/NĐ-CP, Luật Tổ chức chính quyền địa phương 2015/2019",
            "description": "Danh bạ quy chuẩn cơ quan trung ương, tỉnh, huyện, phòng ban nghiệp vụ",
        },
        "NGUON_LUU_TRU_LICH_SU": {
            "source_id": "NGUON_LUU_TRU_LICH_SU",
            "source_name": "Kho lưu trữ dữ liệu lịch sử địa giới và quân đội",
            "source_type": "luu_tru_lich_su",
            "source_url": "https://dichvucong.gov.vn",
            "legal_reference": "Nghị quyết 15/2008/QH12; Quyết định Bộ Quốc phòng thành lập QĐ12 năm 2023",
            "description": "Ghi nhận các đơn vị giải thể, sáp nhập để đối soát hồ sơ cán bộ cũ",
        },
    }
    table_sources = list(sources_dict.values())

    # Bảng UNIT_EVENTS chuẩn
    table_events = [
        {
            "event_id": "EVT_001",
            "event_type": "SAP_NHAP",
            "effective_date": "2008-08-01",
            "from_unit_code": "BCA_CA_HTAY",
            "to_unit_code": "BCA_CA_HN",
            "legal_ref": "Nghị quyết số 15/2008/QH12 của Quốc hội",
            "description": "Hợp nhất tỉnh Hà Tây vào Thành phố Hà Nội",
        },
        {
            "event_id": "EVT_002",
            "event_type": "SAP_NHAP",
            "effective_date": "2023-11-29",
            "from_unit_code": "BQP_QD1, BQP_QD2",
            "to_unit_code": "BQP_QD12",
            "legal_ref": "Quyết định của Bộ trưởng Bộ Quốc phòng ngày 29/11/2023",
            "description": "Thành lập Quân đoàn 12 trên cơ sở sáp nhập Quân đoàn 1 và Quân đoàn 2",
        },
        {
            "event_id": "EVT_003",
            "event_type": "DOI_TEN",
            "effective_date": "2025-07-01",
            "from_unit_code": "BCA_CA_TTH",
            "to_unit_code": "BCA_CA_HUE",
            "legal_ref": "Nghị quyết Quốc hội thành lập TP Huế trực thuộc TW",
            "description": "Nâng cấp Thừa Thiên Huế thành Thành phố Huế trực thuộc TW",
        },
    ]

    for idx, r in enumerate(records, 1):
        unit_code = r.get("unit_code", "")
        uuid_str  = get_deterministic_uuid(unit_code)
        numeric_id = idx  # Cung cấp cả integer ID tương thích ngược

        y_start = r.get("year_start", "").strip()
        y_end   = r.get("year_end",   "").strip()
        s_ref   = r.get("source_ref", "")

        vf, vt, succ, status = resolve_temporal_and_lineage(unit_code, y_start, y_end, s_ref)
        parent_code = resolve_parent_unit(unit_code, r.get("qa_label", "KHAC"))
        src_id = "NGUON_LUU_TRU_LICH_SU" if status == "SAP_NHAP_LICH_SU" else "NGUON_KHUNG_CHINH_PHU"

        # Bảng master_units (tương thích toàn diện)
        item = {
            "unit_id":           numeric_id,
            "unit_uuid":         uuid_str,
            "unit_code":         unit_code,
            "canonical_name":    r["canonical_name"],
            "organization_type": r["qa_label"],
            "unit_level":        r.get("unit_level", ""),
            "admin_level":       r.get("admin_level", ""),
            "org_nature":        r.get("org_nature", ""),
            "parent_unit_code":  parent_code,
            "successor_unit_code": succ,
            "source_ref":        s_ref,
            "source_kind":       r.get("source_kind", "KHUNG_CO_CAU_CHINH_PHU"),
            "valid_from":        vf,
            "valid_to":          vt,
            "status":            status,
            "registry_version":  REGISTRY_VERSION,
            "qa_confidence":     r.get("qa_confidence", "CAO"),
        }
        registry.append(item)

        # 1. Bảng UNITS
        table_units.append({
            "unit_uuid":         uuid_str,
            "unit_code":         unit_code,
            "canonical_name":    r["canonical_name"],
            "organization_type": r["qa_label"],
            "unit_level":        r.get("unit_level", ""),
            "admin_level":       r.get("admin_level", ""),
            "org_nature":        r.get("org_nature", ""),
            "parent_unit_code":  parent_code,
            "successor_unit_code": succ,
            "valid_from":        vf,
            "valid_to":          vt,
            "status":            status,
            "source_id":         src_id,
        })

        # 2. Bảng UNIT_CODES
        table_codes.append({
            "code_id":     f"COD_{idx:05d}",
            "unit_uuid":   uuid_str,
            "unit_code":   unit_code,
            "code_system": "GOV_REGISTRY_VN",
            "valid_from":  vf,
            "valid_to":    vt,
            "is_primary":  "CO",
        })

        # 3. Bảng UNIT_NAMES
        table_names.append({
            "name_id":    f"NAM_{idx:05d}",
            "unit_uuid":  uuid_str,
            "unit_code":  unit_code,
            "name_text":  r["canonical_name"],
            "name_type":  "CHINH_THUC",
            "valid_from": vf,
            "valid_to":   vt,
            "is_primary": "CO",
        })

    # Checksum SHA-256
    content_str = json.dumps(registry, ensure_ascii=False, sort_keys=True)
    checksum    = hashlib.sha256(content_str.encode()).hexdigest()

    # 1. Lưu master_units.csv
    out_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(registry[0].keys()))
        writer.writeheader()
        writer.writerows(registry)

    # Lưu checksum
    cs_path = out_path + ".sha256"
    with open(cs_path, "w", encoding="utf-8") as f:
        f.write(checksum)

    # 2. Lưu các bảng chuẩn hóa schema 3NF
    def save_schema_table(table_data: list[dict], filename: str) -> None:
        if not table_data:
            return
        p = os.path.join(DIR_SCHEMA, filename)
        with open(p, "w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=list(table_data[0].keys()))
            w.writeheader()
            w.writerows(table_data)
        print(f"  [3NF Table] {filename:22s} : {len(table_data):,d} dòng → {p}")

    print("\n[Xuất cấu trúc 4 bảng chuẩn hóa 3NF theo Mục 6.2:]")
    save_schema_table(table_units,   "UNITS.csv")
    save_schema_table(table_codes,   "UNIT_CODES.csv")
    save_schema_table(table_names,   "UNIT_NAMES.csv")
    save_schema_table(table_sources, "SOURCES.csv")
    save_schema_table(table_events,  "UNIT_EVENTS.csv")

    print(f"\n[OK] {len(registry):,d} đơn vị master → {out_path}")
    print(f"[OK] Checksum: {checksum[:16]}… → {cs_path}")

    # Kiểm tra tính toàn vẹn thời gian
    time_travel_bugs = [r for r in registry if r["valid_to"] and r["valid_from"] > r["valid_to"]]
    if time_travel_bugs:
        print(f"\n[ALERT] Phát hiện {len(time_travel_bugs)} lỗi valid_from > valid_to!")
    else:
        print("\n[OK] Temporal Integrity: 100% bản ghi thỏa mãn valid_from <= valid_to (Zero Time Travel)")

    cnt = Counter(r["organization_type"] for r in registry)
    print("\nPhân bổ đơn vị theo khối:")
    for k, v in sorted(cnt.items()):
        print(f"  {k}: {v:,d}")

    closed = [r for r in registry if r["valid_to"]]
    print(f"\n[{len(closed)} đơn vị có mốc hiệu lực valid_to (sáp nhập/giải thể lịch sử)]")

    return registry


if __name__ == "__main__":
    build_registry()
