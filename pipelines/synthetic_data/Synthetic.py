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
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
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
os.makedirs(DIR_SAMPLES, exist_ok=True)

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
                "unit_uuid":         unit.get("unit_uuid", ""),
                "unit_code":         unit["unit_code"],
                "canonical_name":    unit["canonical_name"],
                "organization_type": unit["organization_type"],
                "admin_level":       unit.get("admin_level", ""),
                "org_nature":        unit.get("org_nature", ""),
                "parent_unit_code":  unit.get("parent_unit_code", ""),
                "successor_unit_code": unit.get("successor_unit_code", ""),
                "alias_used":        variant,
                "template_group":    group,
                "has_unit_code_in_text": has_code,
            },
        })
        rid += 1
    return records


# ── Hard Cases: 56 cases covering 8 Golden Suites (Contract Standard: MATCHED) ──────────
HARD_CASES = [
    # ── Suite 1: Acronyms & Short Forms ──
    {"case_id": "HC001", "suite": "1_acronyms", "case_type": "provincial_police_acronym",
     "text": "CA HN xác nhận đồng chí Nguyễn Anh Tuấn đã hoàn thành xuất sắc nhiệm vụ.",
     "note": "CA HN -> Công an Thành phố Hà Nội", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN", "expected_org": "BCA"},
    {"case_id": "HC002", "suite": "1_acronyms", "case_type": "military_command_acronym",
     "text": "Lệnh điều động của BTL Thủ đô Hà Nội đối với cán bộ Trần Văn Bình.",
     "note": "BTL Thủ đô -> Bộ Tư lệnh Thủ đô Hà Nội", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BTL_TDO", "expected_org": "BQP"},
    {"case_id": "HC003", "suite": "1_acronyms", "case_type": "ministerial_department_code",
     "text": "Hồ sơ bàn giao sang C01 BCA để thụ lý điều tra theo thẩm quyền.",
     "note": "C01 BCA -> Văn phòng Cơ quan Cảnh sát điều tra Bộ Công an", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C01", "expected_org": "BCA"},
    {"case_id": "HC004", "suite": "1_acronyms", "case_type": "provincial_police_dept_acronym",
     "text": "Cán bộ công tác tại PC02 Công an tỉnh Nghệ An được phân công thụ lý hồ sơ.",
     "note": "PC02 Nghệ An -> Phòng Cảnh sát hình sự Công an tỉnh Nghệ An", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_NA_PC02", "expected_org": "BCA"},
    {"case_id": "HC005", "suite": "1_acronyms", "case_type": "police_domain_shorthand",
     "text": "Báo cáo của CSHS Bộ Công an về kết quả phòng chống tội phạm chuyên án mới.",
     "note": "CSHS Bộ Công an -> Cục Cảnh sát hình sự (C02)", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C02", "expected_org": "BCA"},
    {"case_id": "HC006", "suite": "1_acronyms", "case_type": "military_provincial_hq_acronym",
     "text": "BCHQS tỉnh Thái Bình phối hợp cùng lực lượng quân đội trên địa bàn.",
     "note": "BCHQS Thái Bình -> Bộ Chỉ huy Quân sự tỉnh Thái Bình", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BCH_TB", "expected_org": "BQP"},
    {"case_id": "HC007", "suite": "1_acronyms", "case_type": "southern_metropolitan_acronym",
     "text": "Công văn từ CATP HCM gửi đến cơ quan quản lý tư pháp.",
     "note": "CATP HCM -> Công an Thành phố Hồ Chí Minh", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HCM", "expected_org": "BCA"},

    # ── Suite 2: Historical Merges & Successors ──
    {"case_id": "HC008", "suite": "2_historical_merges", "case_type": "dissolved_province_to_successor",
     "text": "Đồng chí Nguyễn Văn An từng công tác tại Công an tỉnh Hà Tây trước khi sáp nhập vào Hà Nội.",
     "note": "Công an tỉnh Hà Tây sáp nhập năm 2008 -> kế thừa BCA_CA_HN", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN", "expected_org": "BCA"},
    {"case_id": "HC009", "suite": "2_historical_merges", "case_type": "military_corps_consolidation",
     "text": "Cán bộ công tác tại Sư đoàn 308, thuộc Quân đoàn 12, đề nghị xác nhận hồ sơ.",
     "note": "Quân đoàn 12 thành lập năm 2023 từ sáp nhập Quân đoàn 1 và Quân đoàn 2", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_QD_12", "expected_org": "BQP"},
    {"case_id": "HC010", "suite": "2_historical_merges", "case_type": "military_historical_merge",
     "text": "Hồ sơ công tác tại BCHQS tỉnh Hà Tây năm 2005 được chuyển giao về Bộ Tư lệnh Thủ đô.",
     "note": "BCHQS tỉnh Hà Tây sáp nhập vào Bộ Tư lệnh Thủ đô Hà Nội", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BTL_TDO", "expected_org": "BQP"},
    {"case_id": "HC011", "suite": "2_historical_merges", "case_type": "historical_period_exact_lookup",
     "text": "BCA_CA_HTAY ban hành quyết định khen thưởng cán bộ xuất sắc nhiệm kỳ năm 2004.",
     "note": "Tra cứu lịch sử trong khoảng thời gian hợp lệ (1991-2008)", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HTAY", "expected_org": "BCA"},
    {"case_id": "HC012", "suite": "2_historical_merges", "case_type": "temporal_invalid_post_dissolution",
     "text": "Cán bộ Trần Văn Minh, đơn vị BCA_CA_HTAY, đề nghị cấp thẻ công tác năm 2024.",
     "note": "Xung đột thời gian: Hà Tây giải thể năm 2008 nhưng hồ sơ tạo năm 2024", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC013", "suite": "2_historical_merges", "case_type": "historical_predecessor_reference",
     "text": "Đồng chí Lê Hoàng Nam nhận nhiệm vụ tại Quân đoàn 1 trước thời điểm hợp nhất.",
     "note": "Đơn vị tiền thân Quân đoàn 1 trước khi hợp nhất thành Quân đoàn 12", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_QD_1", "expected_org": "BQP"},
    {"case_id": "HC014", "suite": "2_historical_merges", "case_type": "sub_unit_historical_merge",
     "text": "Hồ sơ tiếp nhận từ Công an thị xã Sơn Tây cũ sau khi địa giới sáp nhập về Thủ đô.",
     "note": "Đơn vị cấp dưới thời kỳ sáp nhập Hà Tây về Hà Nội", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN", "expected_org": "BCA"},

    # ── Suite 3: OCR Noise & Diacritics Distortion ──
    {"case_id": "HC015", "suite": "3_ocr_noise", "case_type": "ocr_digit_substitution",
     "text": "Đơn vị: BCA_C0B (lỗi nhận dạng ký tự từ C04), thụ lý điều tra ma túy.",
     "note": "OCR nhầm '04' thành '0B', cần kiểm tra đối soát", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC016", "suite": "3_ocr_noise", "case_type": "ocr_stripped_accents_abbrev",
     "text": "DV: Phong CS hinh su - CA TP Ha Noi HT: Tran Thi Mai",
     "note": "Văn bản mất dấu và viết tắt do máy quét OCR", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN_PC02", "expected_org": "BCA"},
    {"case_id": "HC017", "suite": "3_ocr_noise", "case_type": "ocr_mixed_tone_marks",
     "text": "Can bo thuoc Cuc Canh sat đieu tra toi pham ve ma tuy, Bo Cong an.",
     "note": "Mất dấu thanh một phần và lẫn lộn ký tự đ/d", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C04", "expected_org": "BCA"},
    {"case_id": "HC018", "suite": "3_ocr_noise", "case_type": "ocr_font_substitution_severe",
     "text": "BCA_C0l Cuo Canh sat giao thong thong bao bien ban xu ly vi pham.",
     "note": "Ký tự '1' bị nhận nhầm thành chữ 'l', 'Cục' thành 'Cuo'", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC019", "suite": "3_ocr_noise", "case_type": "ocr_military_full_unaccented",
     "text": "Bo Chi huy Quan su tinh Quang Ninh bao cao ket qua cong tac quan su.",
     "note": "Bỏ toàn bộ dấu tiếng Việt của đơn vị quân đội", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BCH_QN", "expected_org": "BQP"},
    {"case_id": "HC020", "suite": "3_ocr_noise", "case_type": "ocr_district_name_distortion",
     "text": "Cong an Quan Ba Đinh - Ha Noi thong bao tiep nhan nhan su moi.",
     "note": "Quận Ba Đình bị mất dấu một phần ('Ba Đinh')", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN_BDG", "expected_org": "BCA"},
    {"case_id": "HC021", "suite": "3_ocr_noise", "case_type": "ocr_leetspeak_corruption",
     "text": "H0 s0 can b0 BCA_A05 Cuc An n1nh mang va ph0ng ch0ng to1 pham.",
     "note": "Lỗi OCR nặng thay nguyên âm bằng chữ số 0, 1", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},

    # ── Suite 4: Mixed-Case & Layout Formats ──
    {"case_id": "HC022", "suite": "4_mixed_case", "case_type": "all_caps_scanned_header",
     "text": "DON VI: CATP HO CHI MINH. HO TEN: TRAN THI MAI. CHUC VU: DAI UY.",
     "note": "Văn bản in hoa toàn bộ từ tiêu đề trích xuất", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HCM", "expected_org": "BCA"},
    {"case_id": "HC023", "suite": "4_mixed_case", "case_type": "all_lowercase_delimited",
     "text": "công an quận hoàn kiếm | trần văn bảo | thượng úy | số hiệu: 231-904",
     "note": "Toàn bộ chữ thường phân cách bởi dấu gạch đứng", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HN_HKM", "expected_org": "BCA"},
    {"case_id": "HC024", "suite": "4_mixed_case", "case_type": "tsv_raw_dump",
     "text": "BCA_C02\tPhạm Quốc Toản\tCục Cảnh sát hình sự\tĐiều tra viên\t1982",
     "note": "Định dạng dòng bảng phân tách bằng tab (\t)", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C02", "expected_org": "BCA"},
    {"case_id": "HC025", "suite": "4_mixed_case", "case_type": "camel_case_mixed",
     "text": "bQP_Btl_tDo | Bộ Tư Lệnh Thủ Đô Hà Nội | Quyết định điều chuyển công tác",
     "note": "Mã và tên đơn vị viết hoa thường xen kẽ không đồng nhất", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BTL_TDO", "expected_org": "BQP"},
    {"case_id": "HC026", "suite": "4_mixed_case", "case_type": "markdown_table_row",
     "text": "| 104 | Vũ Hải Yến | BQP_BCH_DN | Bộ Chỉ huy Quân sự tỉnh Đồng Nai |",
     "note": "Định dạng hàng bảng Markdown có dấu | ở hai đầu", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BCH_DN", "expected_org": "BQP"},
    {"case_id": "HC027", "suite": "4_mixed_case", "case_type": "unspaced_key_value_string",
     "text": "MaDV:BCA_CA_HP-TenDV:CongAnThanhPhoHaiPhong-CB:NguyenVanC",
     "note": "Chuỗi ghép không khoảng trắng dạng tham số key-value", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_HP", "expected_org": "BCA"},
    {"case_id": "HC028", "suite": "4_mixed_case", "case_type": "bracket_colon_mixed",
     "text": "BCA_CA_ĐN_HCH: Công An Quận Hải Châu (Đà Nẵng), cán bộ Đặng Hữu Phước.",
     "note": "Phức hợp dấu hai chấm và ngoặc đơn phân định địa phương", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_ĐN_HCH", "expected_org": "BCA"},

    # ── Suite 5: Name-Code Conflicts ──
    {"case_id": "HC029", "suite": "5_code_name_conflict", "case_type": "traffic_vs_narcotics_code",
     "text": "Cán bộ Vũ Minh, mã đơn vị C08, thuộc Cục Cảnh sát điều tra tội phạm về ma túy.",
     "note": "Mã C08 (CSGT) xung đột trực tiếp với tên C04 (Ma túy)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC030", "suite": "5_code_name_conflict", "case_type": "cyber_vs_traffic_code",
     "text": "Mã DV: BCA_A05 Tên DV: Cục Cảnh sát giao thông Họ tên: Nguyễn Văn An",
     "note": "Mã A05 (An ninh mạng) xung đột với Cục CSGT (C08)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC031", "suite": "5_code_name_conflict", "case_type": "province_mismatch_military",
     "text": "Đơn vị: BQP_BCH_HN (Bộ Chỉ huy Quân sự tỉnh Đồng Nai) ra thông báo.",
     "note": "Mã BCHQS Hà Nội ghép với tên Bộ Chỉ huy Quân sự tỉnh Đồng Nai", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BQP"},
    {"case_id": "HC032", "suite": "5_code_name_conflict", "case_type": "inter_provincial_police_conflict",
     "text": "Mã BCA_CA_HN nhưng mô tả ghi: Công an Thành phố Cần Thơ tiếp nhận điều động.",
     "note": "Mã Công an Hà Nội gán cho Công an Cần Thơ", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC033", "suite": "5_code_name_conflict", "case_type": "cross_sector_police_civil",
     "text": "Đồng chí Hoàng Kiệt, mã BCA_C01, thuộc Viện Kiểm sát Nhân dân Tối cao.",
     "note": "Mã công an (BCA_C01) gán vào cơ quan tư pháp dân sự (VKSNDTC)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC034", "suite": "5_code_name_conflict", "case_type": "regional_geographical_mismatch",
     "text": "Quyết định BCA_CA_SG bổ nhiệm cán bộ tại Công an tỉnh Lạng Sơn.",
     "note": "Tiền tố miền Nam ghép vào tỉnh miền núi phía Bắc", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC035", "suite": "5_code_name_conflict", "case_type": "cross_ministry_army_police",
     "text": "Mã đơn vị BQP_QD_12 kèm quyết định phân công về Cục An ninh mạng BCA.",
     "note": "Mã quân đoàn BQP gán với Cục nghiệp vụ BCA", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},

    # ── Suite 6: Near-Misses & Typos ──
    {"case_id": "HC036", "suite": "6_near_miss", "case_type": "district_word_truncation",
     "text": "Hồ sơ của đồng chí Nguyễn Văn An, Công an Quận Giấy, đề nghị xét duyệt.",
     "note": "'Quận Giấy' thiếu từ 'Cầu' (Quận Cầu Giấy)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC037", "suite": "6_near_miss", "case_type": "department_name_letter_typo",
     "text": "Cục Cảnh sát Hình sựu thông báo kết luận điều tra.",
     "note": "Lỗi chính tả gõ thừa ký tự 'Hình sựu'", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC038", "suite": "6_near_miss", "case_type": "military_command_tone_typo",
     "text": "Bộ Tư lẹnh Thủ đô kiểm tra công tác tuyển quân đầu năm.",
     "note": "Lỗi sai dấu thanh 'lẹnh' thay vì 'lệnh'", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BQP"},
    {"case_id": "HC039", "suite": "6_near_miss", "case_type": "administrative_level_distortion",
     "text": "Quyết định bổ nhiệm tại Công an Thị xã Ba Đình - Hà Nội.",
     "note": "Sai cấp hành chính: 'Thị xã Ba Đình' thay vì 'Quận Ba Đình'", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC040", "suite": "6_near_miss", "case_type": "wrong_district_type_cau_giay",
     "text": "Công an Huyện Cầu Giấy phối hợp tuần tra đêm trên địa bàn.",
     "note": "Sai cấp: Cầu Giấy là Quận, không phải Huyện", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC041", "suite": "6_near_miss", "case_type": "minor_acronym_tone_omission",
     "text": "Văn phòng Cơ quan CSDT Bo Cong An tiep nhan don thu khieu nai.",
     "note": "Viết tắt thiếu dấu CSDT thay cho CSĐT trong ngữ cảnh rõ ràng", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C01", "expected_org": "BCA"},
    {"case_id": "HC042", "suite": "6_near_miss", "case_type": "province_spelling_tilde_typo",
     "text": "Cán bộ thuộc Phòng Cảnh sát kinh tế tỉnh Quãng Ninh báo cáo chuyên án.",
     "note": "Lỗi gõ dấu ngã 'Quãng Ninh' thay vì dấu hỏi", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_CA_QN_PC03", "expected_org": "BCA"},

    # ── Suite 7: Multiple Candidates & Ambiguity ──
    {"case_id": "HC043", "suite": "7_multiple_candidates", "case_type": "multi_ministry_in_single_text",
     "text": "Hồ sơ chuyển từ Công an Hà Nội đến Bộ Tư lệnh Thủ đô để thẩm tra lý lịch.",
     "note": "Chứa hai đơn vị hợp lệ thuộc 2 khối khác nhau (BCA và BQP)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": None},
    {"case_id": "HC044", "suite": "7_multiple_candidates", "case_type": "military_hospital_vs_civil",
     "text": "Đồng chí Lê Văn Khoa, Bệnh viện Trung ương Quân đội 108, đề nghị xác nhận thâm niên.",
     "note": "BV 108 thuộc khối BQP, không nhầm sang y tế dân sự (OTHER)", "expected_status": "KHOP_LE", "expected_unit_code": "BQP_BV_108", "expected_org": "BQP"},
    {"case_id": "HC045", "suite": "7_multiple_candidates", "case_type": "civil_dept_with_security_keyword",
     "text": "Phòng An ninh mạng Sở Thông tin và Truyền thông Hà Nội gửi công văn phúc đáp.",
     "note": "Có từ 'An ninh mạng' nhưng thuộc cơ quan dân sự (OTHER)", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC046", "suite": "7_multiple_candidates", "case_type": "generic_military_command",
     "text": "Ban Chỉ huy Quân sự huyện xác nhận hoàn thành thời hạn phục vụ tại ngũ.",
     "note": "Cụm danh xưng chung không kèm địa danh xác định", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BQP"},
    {"case_id": "HC047", "suite": "7_multiple_candidates", "case_type": "isolated_provincial_dept_code",
     "text": "Phòng PC01 tiếp nhận tin báo tố giác tội phạm từ công dân.",
     "note": "PC01 đứng đơn độc không có tên tỉnh có thể thuộc 63 công an tỉnh", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},
    {"case_id": "HC048", "suite": "7_multiple_candidates", "case_type": "inter_departmental_conference",
     "text": "Cuộc họp liên ngành giữa Cục C01, Cục C02 và Viện Kiểm sát Nhân dân Tối cao.",
     "note": "Chứa 3 đơn vị bình đẳng trong cùng một thông báo", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": None},
    {"case_id": "HC049", "suite": "7_multiple_candidates", "case_type": "inter_district_transfer",
     "text": "Biên bản ghi nhận điều chuyển từ Công an Quận 1 sang Công an Quận Tân Bình TP.HCM.",
     "note": "Hai đơn vị cấp quận trong cùng một địa bàn đô thị", "expected_status": "NEED_REVIEW", "expected_unit_code": None, "expected_org": "BCA"},

    # ── Suite 8: Cold-Start / Out-of-Registry / Temporal Edge Cases ──
    {"case_id": "HC050", "suite": "8_cold_start_temporal", "case_type": "fabricated_province_name",
     "text": "Cán bộ Trần Thị Lan, Phòng Tài chính Kế hoạch tỉnh XYZ.",
     "note": "Tên tỉnh XYZ hoàn toàn không tồn tại trong danh mục", "expected_status": "NOT_FOUND", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC051", "suite": "8_cold_start_temporal", "case_type": "missing_unit_text",
     "text": "Đồng chí Phạm Hoàng đề nghị xét nâng lương, không có thông tin đơn vị công tác.",
     "note": "Văn bản không có thực thể đơn vị nào", "expected_status": "EXTRACTION_FAILED", "expected_unit_code": None, "expected_org": None},
    {"case_id": "HC052", "suite": "8_cold_start_temporal", "case_type": "private_commercial_firm",
     "text": "Nhân viên Công ty TNHH Giải pháp Phần mềm Á Châu nộp hồ sơ đăng ký kinh doanh.",
     "note": "Doanh nghiệp tư nhân nằm ngoài hệ thống cơ quan hành chính nhà nước", "expected_status": "NOT_FOUND", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC053", "suite": "8_cold_start_temporal", "case_type": "code_only_resolution",
     "text": "Mã đơn vị BCA_C08 đề nghị xác nhận hồ sơ cán bộ công tác.",
     "note": "Chỉ có mã đơn vị trong văn bản, tra cứu chính xác ra Cục CSGT", "expected_status": "KHOP_LE", "expected_unit_code": "BCA_C08", "expected_org": "BCA"},
    {"case_id": "HC054", "suite": "8_cold_start_temporal", "case_type": "temporary_taskforce_dissolved",
     "text": "Tổ công tác lâm thời phòng chống dịch COVID-19 thành lập năm 2021 đã giải thể.",
     "note": "Tổ chức lâm thời không thuộc danh mục đơn vị chính thức", "expected_status": "NOT_FOUND", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC055", "suite": "8_cold_start_temporal", "case_type": "foreign_diplomatic_mission",
     "text": "Văn phòng Đại sứ quán Hợp chủng quốc Hoa Kỳ tại Hà Nội gửi công hàm ngoại giao.",
     "note": "Cơ quan đại diện ngoại giao nước ngoài nằm ngoài bộ máy nhà nước VN", "expected_status": "NOT_FOUND", "expected_unit_code": None, "expected_org": "KHAC"},
    {"case_id": "HC056", "suite": "8_cold_start_temporal", "case_type": "future_prospective_agency",
     "text": "Dự thảo thành lập Cục Chuyển đổi số quốc gia áp dụng dự kiến từ năm 2030.",
     "note": "Tổ chức đề xuất tương lai vượt khung thời gian khảo sát 2018-2026", "expected_status": "NOT_FOUND", "expected_unit_code": None, "expected_org": "KHAC"},
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

    syn_path = os.path.join(DIR_SAMPLES, "synthetic_records.jsonl")
    with open(syn_path, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n[OK] synthetic_records.jsonl -> {syn_path}")

    hc_path_samples = os.path.join(DIR_SAMPLES, "hard_cases.jsonl")
    with open(hc_path_samples, "w", encoding="utf-8") as f:
        for hc in HARD_CASES:
            f.write(json.dumps(hc, ensure_ascii=False) + "\n")
    print(f"[OK] hard_cases.jsonl ({len(HARD_CASES)} cases) -> {hc_path_samples}")

    hc_path_artifacts = os.path.join(DIR_ARTIFACTS, "hard_cases.jsonl")
    with open(hc_path_artifacts, "w", encoding="utf-8") as f:
        for hc in HARD_CASES:
            f.write(json.dumps(hc, ensure_ascii=False) + "\n")
    print(f"[OK] hard_cases.jsonl -> {hc_path_artifacts}")

    return all_records


if __name__ == "__main__":
    main()
