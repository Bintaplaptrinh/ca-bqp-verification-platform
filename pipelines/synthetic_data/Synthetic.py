"""
Sinh Synthetic Records + NER Labels (2018 - 2026)
===================================================================
Input:  data_artifacts/master_units.csv
        data_artifacts/unit_aliases.csv
Output: data_artifacts/synthetic_records.jsonl
        data_artifacts/hard_cases.jsonl
"""
import sys
import os
# Project root = 2 levels up (pipelines/xxx/ -> pipelines/ -> root)
import pathlib as _pathlib
_PROJECT_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import csv
import json
import random
import unicodedata
import re
from collections import Counter
from itertools import cycle

try:
    from Config import DIR_ARTIFACTS, DIR_SAMPLES, SEED, RECORDS_PER_UNIT
except ImportError:
    DIR_ARTIFACTS    = "./data_artifacts"
    SEED             = 42
    RECORDS_PER_UNIT = 5
    DIR_SAMPLES = "./datasets/samples"

random.seed(SEED)
os.makedirs(DIR_ARTIFACTS, exist_ok=True)

# ── Du lieu gia lap (Zero PII) ────────────────────────────────────────────────
FAKE_NAMES = [
    "Nguyen Van An", "Tran Thi Mai", "Le Hoang Nam", "Pham Quoc Toan",
    "Do Minh Duc", "Vu Hai Yen", "Hoang Tuan Kiet", "Bui Thanh Hang",
    "Dang Huu Phuoc", "Ngo Thi Lan", "Dinh Van Hung", "Cao Thi Thu",
    "Luong Minh Khoa", "Ha Thi Ngoc", "To Van Cuong", "Duong Thi Hoa",
    "Bach Dinh Trong", "Trinh Xuan Bach", "Mai Phuong Thao", "Vo Hoai Nam",
]
FAKE_NAMES_VI = [
    "Nguyễn Văn An", "Trần Thị Mai", "Lê Hoàng Nam", "Phạm Quốc Toản",
    "Đỗ Minh Đức", "Vũ Hải Yến", "Hoàng Tuấn Kiệt", "Bùi Thanh Hằng",
    "Đặng Hữu Phước", "Ngô Thị Lan", "Đinh Văn Hùng", "Cao Thị Thu",
    "Lương Minh Khoa", "Hà Thị Ngọc", "Tô Văn Cường", "Dương Thị Hoa",
    "Bạch Đình Trọng", "Trịnh Xuân Bách", "Mai Phương Thảo", "Võ Hoài Nam",
]
POSITIONS = [
    "Cán bộ điều tra", "Trợ lý tác chiến", "Chuyên viên nghiệp vụ",
    "Đội phó", "Phó phòng", "Nhân viên văn thư", "Điều tra viên",
    "Chuyên viên chính", "Thượng tá", "Đại úy", "Thiếu tá", "Trung úy",
    "Chỉ huy trưởng", "Phó Trưởng Công an", "Trợ lý quân lực",
]
MONTHS  = list(range(1, 13))
YEARS   = list(range(2018, 2027))
BYYEARS = list(range(1968, 2004))

# ── Templates chinh (khong co unit_code) ─────────────────────────────────────
TEMPLATES: dict[str, list[str]] = {
    "decision": [
        "Căn cứ Quyết định điều động số {doc_no}, đồng chí {name} hiện đang công tác tại {unit_variant}.",
        "Theo Lệnh điều động số {doc_no}/{year}/QĐ-BCA, cán bộ {name} được phân công về {unit_variant} kể từ ngày 01/{month}/{year}.",
        "Quyết định số {doc_no} của {unit_variant}: điều chuyển đồng chí {name}, chức vụ {position}, sang đơn vị mới.",
        "Trên cơ sở đề nghị của {unit_variant}, {name} (chức vụ: {position}) được phê duyệt điều động theo QĐ số {doc_no}.",
        "Quyết định {doc_no}/{year}/QĐ-BCH: {unit_variant} quyết định bổ nhiệm đồng chí {name} giữ chức vụ {position}.",
    ],
    "profile": [
        "Họ tên: {name} | Đơn vị: {unit_variant} | Số hiệu: {id_num} | Chức vụ: {position}",
        "Đồng chí {name}, sinh năm {birth_year}, thuộc biên chế {unit_variant}, đang giữ chức vụ {position}.",
        "Hồ sơ đề nghị trợ cấp: {name} — đơn vị {unit_variant} — mã số {id_num}.",
        "BIÊN BẢN XÁC NHẬN: Cán bộ {name} (mã: {id_num}), {position} tại {unit_variant}, đã hoàn thành nhiệm kỳ.",
        "Thông tin: [{id_num}] {name} / {unit_variant} / năm sinh {birth_year} / chức vụ: {position}",
    ],
    "letter": [
        "Kính gửi: {unit_variant}. Về việc xác nhận thâm niên công tác của ông/bà {name}.",
        "Văn phòng {unit_variant} kính chuyển hồ sơ liên quan đến đồng chí {name} (ID: {id_num}).",
        "{unit_variant} thông báo tiếp nhận hồ sơ của {name} kể từ tháng {month}/{year}.",
        "Kính đề nghị {unit_variant} phối hợp xác minh thông tin của cán bộ {name}, chức vụ {position}.",
        "Biên bản bàn giao giữa {unit_variant} và cán bộ {name}: hoàn thành ngày {date}.",
    ],
    "table_row": [
        "{id_num}\t{name}\t{unit_variant}\t{position}\t{birth_year}",
        "STT: 001 | Họ tên: {name} | Đơn vị: {unit_variant} | Chức vụ: {position}",
        "{name},{unit_variant},{id_num},{position},{birth_year},{date}",
        "| {name} | {unit_variant} | {position} | {birth_year} | {id_num} |",
        "TT.{id_num} Ten:{name} DV:{unit_variant} CV:{position} NS:{birth_year}",
    ],
    "free_text": [
        "Theo thông tin từ {unit_variant}, đồng chí {name} đã hoàn thành nhiệm vụ được giao trong tháng {month}/{year}.",
        "Phòng {position} của {unit_variant} thông báo thay đổi nhân sự tháng {month}/{year}: {name} được điều động.",
        "Liên quan đến hồ sơ của {name}, đề nghị {unit_variant} phối hợp cung cấp tài liệu.",
        "Cơ quan {unit_variant} xác nhận đồng chí {name} (sinh {birth_year}) có thâm niên từ năm 2010.",
        "{name}, hiện công tác tại {unit_variant} với chức danh {position}, đề nghị xét nâng lương.",
    ],
    "ocr_table": [
        "{name}  {unit_variant}  {id_num}  {date}",
        "Ho ten: {name}  Don vi: {unit_variant}  Ma so: {id_num}",
        "[ {id_num} ] {name} - {unit_variant} - {position} - nam {birth_year}",
        "TEN: {name} || DV: {unit_variant} || CV: {position} || NS: {birth_year}",
        "{id_num} | {name} | {unit_variant} | {date}",
    ],
}

# Templates co UNIT_CODE (se duoc su dung cho ~25% records)
TEMPLATES_WITH_CODE: dict[str, list[str]] = {
    "decision": [
        "Theo QĐ {doc_no}/{year}, cán bộ {name} (đơn vị {unit_code}) thuộc {unit_variant} được điều động kể từ {date}.",
        "Lệnh số {doc_no}/QĐ-BCA: cán bộ {name}, mã đơn vị {unit_code} — {unit_variant}, bổ nhiệm {position}.",
    ],
    "profile": [
        "Họ tên: {name} | Mã đơn vị: {unit_code} ({unit_variant}) | Chức vụ: {position} | Năm sinh: {birth_year}",
        "Hồ sơ [{unit_code}] — {name}, {position} tại {unit_variant}, năm sinh {birth_year}.",
    ],
    "table_row": [
        "{unit_code}\t{name}\t{unit_variant}\t{position}\t{id_num}",
        "{id_num},{name},{unit_code},{unit_variant},{position},{birth_year}",
    ],
    "ocr_table": [
        "Ma DV: {unit_code}  Ten DV: {unit_variant}  Ho ten: {name}  CV: {position}",
        "[ {unit_code} ] {unit_variant} | {name} | {position} | {birth_year}",
    ],
    "free_text": [
        "Đơn vị {unit_code} ({unit_variant}) xác nhận đồng chí {name} hoàn thành nhiệm vụ tháng {month}/{year}.",
        "Theo báo cáo của {unit_variant} (mã: {unit_code}), {name} giữ chức vụ {position} từ {date}.",
    ],
    "letter": [
        "Kính gửi đơn vị {unit_code} — {unit_variant}. Về hồ sơ cán bộ {name}, chức vụ {position}.",
    ],
}

# Ty le records co unit_code trong text
CODE_RECORD_RATIO = 0.25   # 25% records


# ── OCR Noise Injection ────────────────────────────────────────────────────────
def _strip_accents(text: str) -> str:
    """Bo dau tieng Viet."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

NOISE_OCR_SUBS = [
    (r"đ", "d"), (r"Đ", "D"),
    (r"ươ", "uo"), (r"ườ", "uo"),
    (r"ă", "a"), (r"â", "a"), (r"ê", "e"), (r"ô", "o"),
]

def inject_ocr_noise(text: str, level: float = 0.4) -> tuple[str, bool]:
    """
    Voi xac suat `level`, ap dung bo dau toan bo vao text.
    Chi dung cho template ocr_table va table_row.
    Tra ve (noised_text, noise_applied).
    """
    if random.random() > level:
        return text, False
    return _strip_accents(text), True


# ── BIO Tag generation ─────────────────────────────────────────────────────────
def make_bio_tags(text: str, entities: list[dict]) -> list[dict]:
    """
    Tao token-level BIO tags.
    Tokenize theo khoang trang (word-level, phu hop voi PhoBERT tokenizer).
    Tra ve list {"token": str, "bio": str, "char_start": int, "char_end": int}.
    """
    tokens = []
    i = 0
    while i < len(text):
        # Bo qua khoang trang
        if text[i].isspace():
            i += 1
            continue
        # Tim ket thuc token
        j = i
        while j < len(text) and not text[j].isspace():
            j += 1
        tokens.append({"token": text[i:j], "char_start": i, "char_end": j, "bio": "O"})
        i = j

    # Gan nhan BIO
    for ent in entities:
        es, ee, label = ent["start"], ent["end"], ent["label"]
        first = True
        for tok in tokens:
            ts, te = tok["char_start"], tok["char_end"]
            if te <= es or ts >= ee:
                continue
            tok["bio"] = f"B-{label}" if first else f"I-{label}"
            first = False

    return tokens


# ── Helpers ───────────────────────────────────────────────────────────────────
def fake_ctx(unit_code: str = "") -> dict:
    month = random.choice(MONTHS)
    year  = random.choice(YEARS)
    return {
        "name":       random.choice(FAKE_NAMES_VI),
        "id_num":     f"{random.randint(100,999)}-{random.randint(100,999)}",
        "position":   random.choice(POSITIONS),
        "birth_year": str(random.choice(BYYEARS)),
        "doc_no":     f"{random.randint(10,99)}/QĐ-BCT",
        "date":       f"{random.randint(1,28):02d}/{month:02d}/{year}",
        "month":      str(month),
        "year":       str(year),
        "unit_code":  unit_code,
    }


def compute_spans(text: str, variant: str, name: str, unit_code: str,
                  noised_variant: str = "") -> list[dict]:
    """
    Tim span cua entity trong text.
    - variant      : alias goc (tieng Viet co dau)
    - noised_variant: alias da bo dau neu OCR noise duoc ap dung
    - unit_code    : ma don vi (e.g. BCA_C01)
    Su dung regex \b hoac word-boundary an toan de tranh false match
    (vi du: 'C01' khong match ben trong 'BCA_C01').
    """
    import re as _re
    entities: list[dict] = []

    def add_span_exact(value: str, label: str) -> None:
        """Tim exact match co word-boundary an toan."""
        if not value:
            return
        # Escape de dung trong regex
        escaped = _re.escape(value)
        # Them word-boundary neu value bat dau/ket thuc bang word char
        lb = r"\b" if value[0].isalnum() or value[0] == "_" else ""
        rb = r"\b" if value[-1].isalnum() or value[-1] == "_" else ""
        pattern = lb + escaped + rb
        m = _re.search(pattern, text)
        if m:
            entities.append({
                "start": m.start(), "end": m.end(),
                "label": label, "value": text[m.start():m.end()]
            })

    # Uu tien tim alias da bo dau neu OCR noise duoc ap dung
    search_variant = noised_variant if noised_variant else variant
    add_span_exact(search_variant, "UNIT_NAME")
    add_span_exact(name,           "PERSON_NAME")
    if unit_code and unit_code in text:
        add_span_exact(unit_code,  "UNIT_CODE")

    # Loai bo overlap — uu tien span dai hon
    valid: list[dict] = []
    for ent in sorted(entities, key=lambda e: e["end"] - e["start"], reverse=True):
        if not any(e["start"] < ent["end"] and ent["start"] < e["end"] for e in valid):
            valid.append(ent)
    return sorted(valid, key=lambda e: e["start"])


# ── Round-robin pool generation ─────────────────────────────────────────
def build_pool(n: int, use_code: bool) -> list[tuple[str, str, bool]]:
    """
    Tao pool (group, template, has_code) dam bao phan phoi deu theo group.
    Round-robin qua cac group, random.shuffle truoc de template ngau nhien.
    """
    groups = list(TEMPLATES.keys())

    # Tap hop template cho moi group
    grp_tmpls: dict[str, list[tuple[str, bool]]] = {}
    for g in groups:
        normal = [(t, False) for t in TEMPLATES[g]]
        coded  = [(t, True)  for t in TEMPLATES_WITH_CODE.get(g, [])]
        pool_g = normal + coded
        random.shuffle(pool_g)
        grp_tmpls[g] = pool_g

    # So records co code
    n_code   = max(1, int(n * CODE_RECORD_RATIO)) if use_code else 0
    n_normal = n - n_code

    result: list[tuple[str, str, bool]] = []
    cyc = cycle(groups)
    code_quota = {g: n_code // len(groups) for g in groups}
    # Phan bo phan du
    for g in list(groups)[:n_code % len(groups)]:
        code_quota[g] += 1

    used_code_cnt: dict[str, int] = {g: 0 for g in groups}
    normal_cnt:    dict[str, int] = {g: 0 for g in groups}

    while len(result) < n:
        g = next(cyc)
        want_code = used_code_cnt[g] < code_quota[g]

        tmpl_pool = [(t, hc) for t, hc in grp_tmpls[g]]
        coded_pool  = [(t, True)  for t, hc in tmpl_pool if hc]
        normal_pool = [(t, False) for t, hc in tmpl_pool if not hc]

        if want_code and coded_pool:
            tmpl, has_code = random.choice(coded_pool)
            used_code_cnt[g] += 1
        elif normal_pool:
            tmpl, has_code = random.choice(normal_pool)
        else:
            tmpl, has_code = random.choice(tmpl_pool)

        result.append((g, tmpl, has_code))
        if len(result) >= n:
            break

    random.shuffle(result)
    return result[:n]


def generate_for_unit(unit: dict, aliases: list[str], n: int, rid_start: int) -> list[dict]:
    records: list[dict] = []
    rid = rid_start
    use_code = bool(unit.get("unit_code"))

    pool = build_pool(n, use_code)

    for group, tmpl, has_code in pool:
        ctx     = fake_ctx(unit["unit_code"] if has_code else "")
        variant = random.choice(aliases)
        ctx["unit_variant"] = variant

        try:
            text = tmpl.format(**ctx)
        except KeyError:
            continue

        # Inject OCR noise cho ocr_table/table_row
        noised_variant = ""
        if group in ("ocr_table", "table_row"):
            text, noise_applied = inject_ocr_noise(text, level=0.35)
            if noise_applied:
                noised_variant = _strip_accents(variant)
        else:
            noise_applied = False

        spans    = compute_spans(text, variant, ctx["name"], ctx.get("unit_code", ""),
                                 noised_variant=noised_variant)
        bio_tags = make_bio_tags(text, spans)

        records.append({
            "record_id": rid,
            "text":      text,
            "entities":  spans,
            "bio_tags":  bio_tags,
            "ground_truth": {
                "unit_id":           int(unit["unit_id"]),
                "unit_code":         unit["unit_code"],
                "canonical_name":    unit["canonical_name"],
                "organization_type": unit["organization_type"],
                "alias_used":        variant,
                "template_group":    group,
                "has_unit_code_in_text": has_code,
            },
        })
        rid += 1
    return records


# ── Hard cases (giu nguyen + them 4 cases moi) ────────────────────────────────
HARD_CASES = [
    {"case_id": "HC001", "case_type": "near_miss_name",
     "text": "Ho so cua dong chi Nguyen Van An, Cong an Quan Giay, de nghi xet duyet.",
     "note": "'Quan Giay' vs 'Quan Cau Giay'", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC002", "case_type": "not_found",
     "text": "Can bo Tran Thi Lan, Phong Tai chinh Ke hoach tinh XYZ.",
     "note": "Don vi khong co trong registry", "expected_status": "NOT_FOUND"},
    {"case_id": "HC003", "case_type": "ocr_noise",
     "text": "Don vi: BCA_C0B (loi OCR tu C04), can bo Nguyen Van An.",
     "note": "OCR 4->B", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC004", "case_type": "bqp_hospital_ambiguity",
     "text": "Dong chi Le Van Khoa, Benh vien 108, de nghi xac nhan tham nien.",
     "note": "BV 108 la BQP, de nham OTHER", "expected_status": "VERIFIED", "expected_org": "BQP"},
    {"case_id": "HC005", "case_type": "code_name_conflict",
     "text": "Can bo Vu Minh, ma don vi C08, thuoc Cuc Canh sat dieu tra ma tuy.",
     "note": "C08=CSGT nhung ten la ma tuy (C04)", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC006", "case_type": "other_similar_to_bca",
     "text": "Phong An ninh mang So Thong tin Truyen thong Ha Noi xac nhan ho so.",
     "note": "'An ninh mang' thuoc So dan su (OTHER)", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC007", "case_type": "missing_unit_info",
     "text": "Dong chi Pham Hoang de nghi xet nang luong, khong co thong tin don vi.",
     "note": "Khong trich xuat duoc UNIT_NAME", "expected_status": "EXTRACTION_FAILED"},
    {"case_id": "HC008", "case_type": "multiple_candidates",
     "text": "Ho so chuyen tu Cong an Ha Noi den Bo Tu lenh Thu do.",
     "note": "2 don vi trong 1 van ban", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC009", "case_type": "abbreviation_ambiguity",
     "text": "CA HN xac nhan dong chi Nguyen Anh Tuan da hoan thanh nhiem vu.",
     "note": "'CA HN' -> CATP Ha Noi (BCA)", "expected_status": "VERIFIED", "expected_org": "BCA"},
    {"case_id": "HC010", "case_type": "legacy_hatay",
     "text": "Dong chi Nguyen Van An tung cong tac tai Cong an tinh Ha Tay truoc khi hop nhat.",
     "note": "Don vi lich su sap nhap", "expected_status": "VERIFIED", "expected_org": "BCA"},
    {"case_id": "HC011", "case_type": "post_merge_quandoan",
     "text": "Su doan 308, thuoc Quan doan 12, de nghi xac nhan ho so can bo Tran Minh.",
     "note": "QD 12 chi ton tai tu 2024", "expected_status": "VERIFIED", "expected_org": "BQP"},
    {"case_id": "HC012", "case_type": "all_caps_input",
     "text": "DON VI: CATP HO CHI MINH. HO TEN: TRAN THI MAI. CHUC VU: DAI UY.",
     "note": "Input toan chu hoa (scan OCR)", "expected_status": "VERIFIED", "expected_org": "BCA"},
    # [ADD] 4 cases moi
    {"case_id": "HC013", "case_type": "unit_code_only",
     "text": "Ma don vi BCA_C08 de nghi xac nhan ho so can bo.",
     "note": "Chi co unit_code, khong co ten day du", "expected_status": "VERIFIED", "expected_org": "BCA"},
    {"case_id": "HC014", "case_type": "mixed_code_name_mismatch",
     "text": "Ma DV: BCA_A05 Ten DV: Cuc Canh sat giao thong Ho ten: Nguyen Van An",
     "note": "unit_code (A05=An ninh mang) khong khop ten (CSGT=C08)", "expected_status": "NEED_REVIEW"},
    {"case_id": "HC015", "case_type": "partial_name_ocr",
     "text": "DV: Phong CS hinh su - CA TP Ha Noi HT: Tran Thi Mai",
     "note": "Ten bi viet tat va bo dau do OCR", "expected_status": "VERIFIED", "expected_org": "BCA"},
    {"case_id": "HC016", "case_type": "year_out_of_range",
     "text": "Can bo Tran Van Minh, BCA_CA_HTAY, de nghi xac nhan ho so nam 2020.",
     "note": "HTAY da sap nhap 2008 nhung ho so ghi nam 2020", "expected_status": "NEED_REVIEW"},
]


def main() -> list[dict]:
    print("=" * 65)
    print("SYNTHETIC v2 — SINH RECORDS + NER LABELS (2018 – 2026)")
    print("=" * 65)
    print(f"[Config] RECORDS_PER_UNIT = {RECORDS_PER_UNIT}")
    print(f"[Config] CODE_RECORD_RATIO = {CODE_RECORD_RATIO:.0%}")

    master_path = os.path.join(DIR_ARTIFACTS, "master_units.csv")
    alias_path  = os.path.join(DIR_ARTIFACTS, "unit_aliases.csv")

    if not os.path.exists(master_path) or not os.path.exists(alias_path):
        print("[ERROR] Thieu artifacts. Hay chay Registy.py va Aliases.py truoc.")
        return []

    with open(master_path, encoding="utf-8") as f:
        registry = list(csv.DictReader(f))
    with open(alias_path, encoding="utf-8") as f:
        alias_rows = list(csv.DictReader(f))

    print(f"[Doc] {len(registry):,d} don vi | {len(alias_rows):,d} aliases")

    aliases_by_uid: dict[int, list[str]] = {}
    for a in alias_rows:
        uid = int(a["unit_id"])
        aliases_by_uid.setdefault(uid, []).append(a["alias_name"])

    all_records: list[dict] = []
    rid = 1
    total = len(registry)

    for idx, unit in enumerate(registry, 1):
        uid = int(unit["unit_id"])
        als = aliases_by_uid.get(uid, [unit["canonical_name"]])
        recs = generate_for_unit(unit, als, RECORDS_PER_UNIT, rid)
        all_records.extend(recs)
        rid += len(recs)
        if idx % 300 == 0 or idx == total:
            print(f"  [{idx:4d}/{total}] -> {len(all_records):6,d} records tich luy")

    print(f"\n[OK] Tong: {len(all_records):,d} synthetic records")

    grp_cnt  = Counter(r["ground_truth"]["template_group"] for r in all_records)
    code_cnt = sum(1 for r in all_records if r["ground_truth"].get("has_unit_code_in_text"))
    print("\nPhan bo template:")
    for k, v in sorted(grp_cnt.items()):
        print(f"  {k:12s}: {v:5,d} ({v/len(all_records)*100:.1f}%)")
    print(f"\nRecords co UNIT_CODE trong text: {code_cnt:,d} ({code_cnt/len(all_records)*100:.1f}%)")

    no_unit = [r for r in all_records if not any(e["label"] == "UNIT_NAME" for e in r["entities"])]
    ratio   = len(no_unit) / len(all_records) * 100
    print(f"\nKiem tra NER UNIT_NAME: {len(no_unit):,d} thieu ({ratio:.2f}%)")
    code_tagged = [r for r in all_records if any(e["label"] == "UNIT_CODE" for e in r["entities"])]
    print(f"Kiem tra NER UNIT_CODE: {len(code_tagged):,d} records co tag ({len(code_tagged)/len(all_records)*100:.1f}%)")
    if ratio < 1.0:
        print("  ✓ Chat luong NER UNIT_NAME dat chuan (< 1% loi)")

    syn_path = os.path.join(DIR_ARTIFACTS, "synthetic_records.jsonl")
    with open(syn_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n[OK] synthetic_records.jsonl -> {syn_path}")

    hc_path = os.path.join(DIR_ARTIFACTS, "hard_cases.jsonl")
    with open(hc_path, "w", encoding="utf-8") as f:
        for hc in HARD_CASES:
            f.write(json.dumps(hc, ensure_ascii=False) + "\n")
    print(f"[OK] hard_cases.jsonl ({len(HARD_CASES)} cases) -> {hc_path}")
    return all_records


if __name__ == "__main__":
    main()
