from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean

from rapidfuzz import fuzz

from cabqp.shared.normalization import ascii_key

# Fuzzy matching is intentionally limited to field labels. It must never be used to
# "repair" a person's name, unit, code, or other extracted value.
_LABEL_FUZZY_THRESHOLD = 75

# Rule priors describe how much structural evidence a generic extraction rule carries.
# They are deliberately conservative and are exposed in evidence so they can later be
# calibrated against a real labelled validation set instead of tuned to fixture values.
_RULE_PRIOR = {
    "structured_input": 0.99,
    "table_inline_cell": 0.97,
    "table_right_cell": 0.95,
    "table_below_cell": 0.90,
    "inline_same_box": 0.97,
    "right_same_line": 0.94,
    "below_left_aligned": 0.88,
    "cccd_12_digit_template": 0.94,
    "cccd_name_below_label": 0.90,
    "label_same_line": 0.92,
    "narrative_name": 0.78,
    "bare_name_query": 0.98,
    "regex_code": 0.78,
    "regex_position": 0.76,
    "current_marker": 0.90,
    "single_unit_mention": 0.62,
}


def _label_score(candidate_key: str, aliases: list[str]) -> float:
    if not candidate_key:
        return 0.0
    return max((fuzz.ratio(candidate_key, ascii_key(alias)) for alias in aliases), default=0.0)


CURRENT_MARKERS = [
    "hiện công tác tại",
    "hiện đang công tác tại",
    "đang công tác tại",
    "đơn vị công tác hiện tại",
    "hiện thuộc",
    "đang làm việc tại",
]
FORMER_MARKERS = ["trước đây công tác tại", "từng công tác tại", "nguyên công tác tại", "trước công tác tại"]
UNIT_PREFIXES = r"(?:Công an|Cục|Bộ Tư lệnh|Bộ Chỉ huy|Ban Chỉ huy|Học viện|Trường|Bệnh viện|Viện|Trung tâm|Quân khu|Quân đoàn|Sư đoàn|Lữ đoàn|Trung đoàn|Tiểu đoàn|Tổng cục|Binh chủng|Quân chủng)"
UNIT_NAME_BODY = r"[^.;\n,]{2,120}?(?=\s+(?:và|,)\s|[.;\n,]|$)"

# Lowercase is valid for a name-only query, but short lowercase role/unit phrases
# are equally word-shaped. These domain markers prove the input is not a bare name;
# longer prose still belongs to the narrative extractors and resolver abstention.
_BARE_NAME_NON_PERSON_PHRASES = (
    "đồng chí", "công tác", "đơn vị", "chức vụ", "cấp bậc", "sĩ quan",
    "hạ sĩ quan", "chiến sĩ", "công an", "quân nhân", "quân đội", "cán bộ",
    "không còn", "không phải", "trước đây", "từng là", "hiện tại", "hiện nay",
)

LABELS = {
    "subject_name": ["họ và tên", "họ tên", "ho va ten", "ho ten"],
    # "Mã số cán bộ" is what the entry form calls this field and what it writes into
    # the text it composes, so it has to be recognized here or the platform cannot
    # read back a dossier it wrote itself.
    "subject_code": [
        "cccd", "cmnd", "số hiệu", "so hieu", "mã cá nhân", "ma ca nhan",
        "mã số cán bộ", "ma so can bo", "mã cán bộ", "ma can bo", "mã số", "ma so",
    ],
    # Not a field of `Extraction` — it has no column — but a labelled year is still a
    # fact the document carries, and `PersonResolver` narrows a bare-name lookup on
    # it. `extract()` reads it out of `labelled` into `fields["birth_year"]`.
    "birth_year": ["năm sinh", "nam sinh", "ngày sinh", "ngay sinh", "sinh năm", "sinh nam"],
    "position": ["chức vụ", "chuc vu", "cấp bậc", "cap bac"],
    "unit_name": ["đơn vị công tác", "don vi cong tac", "cơ quan công tác", "co quan cong tac"],
    # A historical-unit label must be recognized in its own right. It is listed after
    # "unit_name" so an exact current-unit label still wins the equal-score tie, but a
    # qualifier such as "cũ" / "trước đây" scores 100 here against ~91 there and is no
    # longer read as CURRENT_WORK_UNIT — the invariant a fuzzy threshold of 75 broke.
    "former_unit_name": [
        "đơn vị công tác cũ",
        "don vi cong tac cu",
        "đơn vị công tác trước đây",
        "don vi cong tac truoc day",
        "cơ quan công tác cũ",
        "co quan cong tac cu",
        "nguyên đơn vị công tác",
        "nguyen don vi cong tac",
    ],
    "subject_group": ["nhóm đối tượng", "nhom doi tuong"],
}


@dataclass
class Extraction:
    subject_name: str | None
    subject_code: str | None
    position: str | None
    current_unit: str | None
    former_units: list[str]
    extraction_confidence: float
    relation_confidence: float
    fields: dict
    unit_code: str | None = None


UNIT_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}(?:-[A-Z0-9]{1,10}){0,2}$")


def _looks_like_unit_code(value: str) -> bool:
    text = (value or "").strip()
    if not text or " " in text:
        return False
    return bool(UNIT_CODE_RE.fullmatch(text)) and any(c.isdigit() or c == "-" for c in text)


def _bare_person_name(text: str) -> str | None:
    """Recognize an intentional name-only lookup without guessing from prose.

    This path is deliberately narrow: one line, 2-6 alphabetic words, no
    digits/labels, and no organizational prefix. Case is not evidence of whether a
    value is a person's name: operators commonly type the lookup entirely in lower
    or upper case, and PersonResolver owns the actual identity decision.
    """
    value = (text or "").strip().strip(".,;:")
    if not value or "\n" in value or "\r" in value or any(ch.isdigit() for ch in value):
        return None
    words = value.split()
    if not 2 <= len(words) <= 6:
        return None
    if re.match(rf"^(?:{UNIT_PREFIXES})\b", value, flags=re.I):
        return None
    folded = ascii_key(value)
    if any(ascii_key(phrase) in folded for phrase in _BARE_NAME_NON_PERSON_PHRASES):
        return None
    for word in words:
        clean = word.strip("'-")
        if not clean or not all(ch.isalpha() or ch in "'-" for ch in word):
            return None
    return value


def _inline_label_value(text: str) -> tuple[str | None, str | None, float]:
    """Split a combined line even when punctuation or label spaces are lost."""
    raw = (text or "").strip()
    if not raw:
        return None, None, 0.0

    # A complete label cell/line (for example "Đơn vị công tác") must not be
    # mis-split into label="Đơn vị công" and value="tác" merely because labels may
    # occasionally arrive merged with values in OCR. Prefer the whole-cell label test.
    whole_key = ascii_key(raw.strip(" :-\t"))
    whole_label_score = max((_label_score(whole_key, aliases) for aliases in LABELS.values()), default=0.0)
    if ":" not in raw and "\t" not in raw and whole_label_score >= 90:
        return None, None, whole_label_score

    candidates: list[tuple[str, str]] = []
    if ":" in raw:
        label, _, value = raw.partition(":")
        candidates.append((label, value))
    elif "\t" in raw:
        label, _, value = raw.partition("\t")
        candidates.append((label, value))
    else:
        tokens = raw.split()
        for split_at in range(1, min(5, len(tokens))):
            candidates.append((" ".join(tokens[:split_at]), " ".join(tokens[split_at:])))

    best_field: str | None = None
    best_value: str | None = None
    best_score = 0.0
    for label, value in candidates:
        value = value.strip(" :-\t")
        if not value:
            continue
        label_key = ascii_key(label.strip(" :-\t"))
        for field_name, aliases in LABELS.items():
            score = _label_score(label_key, aliases)
            if score > best_score:
                best_field, best_value, best_score = field_name, value, score
    if best_score < _LABEL_FUZZY_THRESHOLD:
        return None, None, best_score
    return best_field, best_value, best_score


def _labelled_list_segments(line: str) -> list[str] | None:
    """Split a line that is itself a comma-separated list of labelled fields.

    One line can carry a whole dossier — "Họ và tên: A, Năm sinh: B, Chức vụ: C" is
    what an operator types and what the web client composes from the entry form.
    Read as a single label/value pair it yields one field whose value is every field
    after it, so the name ends up holding the entire line.

    Splitting is refused unless at least two of the comma-separated pieces carry a
    label of their own. That is the difference between a list of fields and a single
    value that merely contains a comma: "Đơn vị công tác: Cục An ninh mạng, Bộ Công
    an" is one unit designation and must not be cut in half.
    """
    pieces = [piece.strip() for piece in line.split(",")]
    if len(pieces) < 2:
        return None
    labelled = sum(1 for piece in pieces if _inline_label_value(piece)[0] is not None)
    return pieces if labelled >= 2 else None


def label_values_with_evidence(text: str) -> tuple[dict[str, str], dict[str, dict]]:
    """Read line-scoped label/value pairs and retain label-match evidence."""
    found: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    lines: list[tuple[int, str]] = []
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        lines.extend(
            (line_no, piece) for piece in (_labelled_list_segments(raw_line) or [raw_line])
        )
    for line_no, raw_line in lines:
        best_field, value, score = _inline_label_value(raw_line)
        if best_field is not None and best_field not in found and value:
            found[best_field] = value
            evidence[best_field] = {
                "rule": "label_same_line",
                "line": line_no,
                "label_score": round(score / 100.0, 4),
                "conf": 1.0,
            }
    return found, evidence


def label_values(text: str) -> dict[str, str]:
    return label_values_with_evidence(text)[0]


def _clean_unit(v: str) -> str:
    v = re.split(r"[.;\n]", v)[0]
    return re.sub(r"\s+", " ", v).strip(" ,:-")[:500]


def _word_spans(value: str) -> list[tuple[str, int, int]]:
    """Return ASCII-folded words while retaining offsets into the raw value."""
    return [
        (ascii_key(match.group(0)), match.start(), match.end())
        for match in re.finditer(r"[^\W_]+", value or "", flags=re.UNICODE)
    ]


def _marker_spans(value: str, markers: list[str]) -> list[tuple[int, int, str]]:
    """Find markers accent/case-insensitively without losing raw-text offsets.

    Structure detection uses ASCII-folded tokens, but returned offsets always point
    into the original text. Extraction can therefore keep the operator's raw wording
    as evidence instead of storing the normalized copy.
    """
    words = _word_spans(value)
    found: list[tuple[int, int, str]] = []
    for marker in markers:
        marker_words = ascii_key(marker).split()
        if not marker_words:
            continue
        width = len(marker_words)
        for index in range(len(words) - width + 1):
            if [word for word, _start, _end in words[index:index + width]] == marker_words:
                found.append((words[index][1], words[index + width - 1][2], marker))
    return found


def _cut_at_markers(value: str, markers: list[str]) -> str:
    """Stop a narrative unit value at the next employment-history marker.

    ``_clean_unit`` only cuts on punctuation. A scan that lost the sentence break
    therefore turned "trước đây công tác tại Cục A hiện đang công tác tại Cục B"
    into one former unit spanning both clauses; the marker itself is the boundary
    that survives OCR, so cut there as well.
    """
    cut = min((start for start, _end, _marker in _marker_spans(value, markers)), default=len(value))
    return value[:cut]


def _earliest_marker(value: str, markers: list[str]) -> tuple[int, int, str] | None:
    """Find the first marker mentioned, preferring the longest one at that position.

    Several markers overlap ("hiện đang công tác tại" contains "đang công tác tại"),
    so scanning in list order could cut the value in the middle of the longer marker
    and leave its tail as part of the unit name.
    """
    found = _marker_spans(value, markers)
    if not found:
        return None
    # At the same starting position prefer the longest raw span. This preserves the
    # old overlap rule for "hiện đang công tác tại" / "đang công tác tại".
    return min(found, key=lambda item: (item[0], -(item[1] - item[0])))


def _line(d: dict):
    try:
        b = d.get("bbox") or [0, 0, 0, 0]
        return {
            "text": str(d.get("text") or "").strip(),
            "conf": float(d.get("conf", 0.0)),
            "bbox": tuple(float(x) for x in b),
            "page": int(d.get("page", 1)),
            "engine": d.get("engine", "unknown"),
        }
    except Exception:
        return None


def _is_label(text: str) -> bool:
    inline_field, _, _ = _inline_label_value(text)
    if inline_field is not None:
        return True
    label_part = text.split(":", 1)[0]
    k = ascii_key(label_part).rstrip(":")
    return any(_label_score(k, aliases) >= _LABEL_FUZZY_THRESHOLD for aliases in LABELS.values())


def spatial_key_values(ocr_lines: list[dict]) -> tuple[dict, dict]:
    lines = [x for x in (_line(d) for d in ocr_lines) if x and x["text"]]
    values: dict = {}
    evidence: dict = {}
    for field, aliases in LABELS.items():
        for lab in lines:
            inline_field, inline_value, inline_score = _inline_label_value(lab["text"])
            if inline_field == field and inline_value:
                values[field] = inline_value
                evidence[field] = {
                    "page": lab["page"],
                    "bbox": lab["bbox"],
                    "label_bbox": lab["bbox"],
                    "engine": lab["engine"],
                    "conf": lab["conf"],
                    "label": lab["text"],
                    "label_score": round(inline_score / 100.0, 4),
                    "geometry_score": 1.0,
                    "rule": "inline_same_box",
                }
                break

            label_part = lab["text"].split(":", 1)[0]
            lk = ascii_key(label_part).rstrip(":")
            label_score = _label_score(lk, aliases)
            if label_score < _LABEL_FUZZY_THRESHOLD:
                continue

            lx0, ly0, lx1, ly1 = lab["bbox"]
            lh = max(1.0, ly1 - ly0)
            same = []
            below = []
            for cand in lines:
                if cand is lab or cand["page"] != lab["page"]:
                    continue
                x0, y0, x1, y1 = cand["bbox"]
                overlap = max(0.0, min(ly1, y1) - max(ly0, y0)) / max(1.0, min(lh, y1 - y0 if y1 > y0 else lh))
                if x0 >= lx1 and overlap > 0.5:
                    same.append((x0 - lx1, cand, overlap))
                elif y0 >= ly1 and abs(x0 - lx0) <= max(40.0, lh * 2.5):
                    distance = y0 - ly1 + abs(x0 - lx0) * 0.1
                    below.append((distance, cand, max(0.0, 1.0 - distance / max(120.0, lh * 8.0))))
            candidates = sorted(same, key=lambda x: x[0]) or sorted(below, key=lambda x: x[0])
            if not candidates:
                continue
            distance, cand, geometry_score = candidates[0]
            if _is_label(cand["text"]):
                continue
            values[field] = cand["text"]
            evidence[field] = {
                "page": cand["page"],
                "bbox": cand["bbox"],
                "label_bbox": lab["bbox"],
                "engine": cand["engine"],
                "conf": cand["conf"],
                "label": lab["text"],
                "label_score": round(label_score / 100.0, 4),
                "geometry_score": round(max(0.0, min(1.0, geometry_score)), 4),
                "distance": round(float(distance), 3),
                "rule": "right_same_line" if same else "below_left_aligned",
            }
            break
    return values, evidence


def table_key_values(tables: list) -> tuple[dict, dict]:
    """Extract generic label/value pairs from parser-produced table cells.

    No value is corrected or synthesized. Only known field labels are fuzzy-matched;
    the adjacent cell text is returned verbatim as the candidate value.
    """
    values: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    for table_idx, table in enumerate(tables or []):
        if not isinstance(table, list):
            continue
        rows = [row if isinstance(row, list) else [] for row in table]
        for row_idx, row in enumerate(rows):
            for col_idx, raw_cell in enumerate(row):
                cell = str(raw_cell or "").strip()
                if not cell:
                    continue
                inline_field, inline_value, inline_score = _inline_label_value(cell)
                if inline_field and inline_value and inline_field not in values:
                    values[inline_field] = inline_value
                    evidence[inline_field] = {
                        "table": table_idx,
                        "row": row_idx,
                        "column": col_idx,
                        "label": cell,
                        "label_score": round(inline_score / 100.0, 4),
                        "conf": 1.0,
                        "rule": "table_inline_cell",
                    }
                    continue

                key = ascii_key(cell.strip(" :-\t"))
                best_field = None
                best_score = 0.0
                for field_name, aliases in LABELS.items():
                    score = _label_score(key, aliases)
                    if score > best_score:
                        best_field, best_score = field_name, score
                if best_field is None or best_score < _LABEL_FUZZY_THRESHOLD or best_field in values:
                    continue

                candidate = None
                candidate_pos = None
                rule = None
                for next_col in range(col_idx + 1, len(row)):
                    value = str(row[next_col] or "").strip()
                    if value and not _is_label(value):
                        candidate, candidate_pos, rule = value, (row_idx, next_col), "table_right_cell"
                        break
                if candidate is None and row_idx + 1 < len(rows) and col_idx < len(rows[row_idx + 1]):
                    value = str(rows[row_idx + 1][col_idx] or "").strip()
                    if value and not _is_label(value):
                        candidate, candidate_pos, rule = value, (row_idx + 1, col_idx), "table_below_cell"
                if candidate is None:
                    continue
                values[best_field] = candidate
                evidence[best_field] = {
                    "table": table_idx,
                    "row": candidate_pos[0],
                    "column": candidate_pos[1],
                    "label_row": row_idx,
                    "label_column": col_idx,
                    "label": cell,
                    "label_score": round(best_score / 100.0, 4),
                    "conf": 1.0,
                    "rule": rule,
                }
    return values, evidence


def cccd_template_values(ocr_lines: list[dict]) -> tuple[dict, dict]:
    """Fixed-layout helper for ID-card style documents; never overrides explicit fields."""
    lines = [x for x in (_line(d) for d in ocr_lines) if x and x["text"]]
    if not lines:
        return {}, {}
    page_text = " ".join(ascii_key(x["text"]) for x in lines)
    if not any(marker in page_text for marker in ("can cuoc", "citizen identity", "identity card", "cccd")):
        return {}, {}
    values: dict = {}
    evidence: dict = {}
    for line in sorted(lines, key=lambda x: (x["page"], x["bbox"][1], x["bbox"][0])):
        m = re.search(r"(?<!\d)(\d{12})(?!\d)", line["text"])
        if m:
            values["subject_code"] = m.group(1)
            evidence["subject_code"] = {
                "page": line["page"], "bbox": line["bbox"], "engine": line["engine"],
                "conf": line["conf"], "geometry_score": 1.0, "rule": "cccd_12_digit_template",
            }
            break
    name_labels = [x for x in lines if any(k in ascii_key(x["text"]) for k in ("ho va ten", "full name"))]
    if name_labels:
        lab = name_labels[0]
        lx0, ly0, lx1, ly1 = lab["bbox"]
        candidates = []
        for cand in lines:
            if cand is lab or cand["page"] != lab["page"] or _is_label(cand["text"]):
                continue
            x0, y0, _, _ = cand["bbox"]
            if y0 >= ly1 and y0 - ly1 <= 120 and abs(x0 - lx0) <= 180:
                distance = y0 - ly1 + abs(x0 - lx0) * 0.1
                candidates.append((distance, cand))
        if candidates:
            distance, cand = min(candidates, key=lambda x: x[0])
            if 2 <= len(re.findall(r"[A-Za-zÀ-ỹĐđ]+", cand["text"])) <= 7:
                values["subject_name"] = cand["text"]
                evidence["subject_name"] = {
                    "page": cand["page"], "bbox": cand["bbox"], "label_bbox": lab["bbox"],
                    "engine": cand["engine"], "conf": cand["conf"],
                    "geometry_score": round(max(0.0, 1.0 - distance / 120.0), 4),
                    "distance": round(float(distance), 3), "rule": "cccd_name_below_label",
                }
    return values, evidence


def _parse_quality_factor(structured: dict, source: str, page: int | None = None) -> tuple[float, dict]:
    """Return a conservative quality multiplier for OCR-derived fields."""
    if source not in {"spatial", "template", "labelled_ocr"}:
        return 1.0, {"quality_factor": 1.0}

    quality = structured.get("_parse_quality") or {}
    evidence = structured.get("_parse_evidence") or {}
    factor = 1.0
    reasons: list[str] = []

    def apply_ocr_evidence(ev: dict):
        nonlocal factor
        if ev.get("critical_disagreement"):
            factor = 0.0
            reasons.append("ocr_engine_critical_disagreement")
        elif ev.get("fallback_ran"):
            # Agreement after a fallback is useful evidence, but still carries more
            # uncertainty than a clean primary pass until calibrated on ground truth.
            factor *= 0.95
            reasons.append("ocr_fallback_used")

    if isinstance(evidence.get("ocr"), dict):
        apply_ocr_evidence(evidence["ocr"])
    page_ev = evidence.get("ocr_page_evidence") or {}
    if page is not None and isinstance(page_ev.get(str(page)), dict):
        apply_ocr_evidence(page_ev[str(page)])

    metrics = quality.get("metrics") or {}
    page_quality = (evidence.get("ocr_page_quality") or {}).get(str(page)) if page is not None else None
    page_metrics = (page_quality or {}).get("metrics") or {}
    for metric_name in ("image_blur_variance", "image_contrast_std"):
        metric = page_metrics.get(metric_name) or metrics.get(metric_name) or {}
        if str(metric.get("state", "")).upper() == "FAIL":
            factor *= 0.75
            reasons.append(metric.get("reason") or metric_name)
    if str(quality.get("gate_result", "")).upper() == "FAIL":
        factor = min(factor, 0.5)
        reasons.append("parse_gate_failed")

    return max(0.0, min(1.0, factor)), {"quality_factor": round(max(0.0, min(1.0, factor)), 4), "quality_reasons": reasons}


def _field_score(source: str, evidence: dict | None, structured: dict) -> tuple[float, dict]:
    ev = dict(evidence or {})
    rule = str(ev.get("rule") or ("structured_input" if source == "structured" else ""))
    prior = _RULE_PRIOR.get(rule, 0.80)
    line_conf = max(0.0, min(1.0, float(ev.get("conf", 1.0) or 0.0)))
    label_score = max(0.0, min(1.0, float(ev.get("label_score", 1.0) or 0.0)))
    geometry_score = max(0.0, min(1.0, float(ev.get("geometry_score", 1.0) or 0.0)))
    quality_factor, quality_ev = _parse_quality_factor(structured, source, ev.get("page"))
    score = prior * line_conf * label_score * geometry_score * quality_factor
    components = {
        "source": source,
        "rule": rule,
        "rule_prior": prior,
        "ocr_confidence": line_conf if source in {"spatial", "template", "labelled_ocr"} else None,
        "label_score": label_score,
        "geometry_score": geometry_score,
        **quality_ev,
        "score": round(max(0.0, min(0.99, score)), 4),
    }
    return max(0.0, min(0.99, score)), components


def _pick(candidates: list[tuple[str, str | None, dict | None]]) -> tuple[str | None, str | None, dict]:
    for source, value, evidence in candidates:
        if value is not None and str(value).strip():
            return str(value).strip(), source, dict(evidence or {})
    return None, None, {}


def _overall_extraction_confidence(field_scores: dict[str, float], values: dict[str, str | None]) -> float:
    # Overall confidence must represent both correctness and completeness. A single
    # high-confidence field can therefore never yield a near-1.0 document score.
    expected = ("subject_name", "subject_code", "position", "current_unit")
    present_scores = [field_scores[k] for k in expected if values.get(k)]
    if not present_scores:
        return 0.0
    coverage = len(present_scores) / len(expected)
    completeness_factor = 0.60 + 0.40 * coverage
    return round(max(0.0, min(0.99, mean(present_scores) * completeness_factor)), 4)


def extract(text: str, structured: dict | None = None) -> Extraction:
    """Pull dossier fields out of parsed text and structure deterministically."""
    structured = structured or {}
    ocr_lines = structured.get("_ocr_lines") or []
    tables = structured.get("_parsed_tables") or []
    spatial, spatial_evidence = spatial_key_values(ocr_lines) if ocr_lines else ({}, {})
    template, template_evidence = cccd_template_values(ocr_lines) if ocr_lines else ({}, {})
    table_values, table_evidence = table_key_values(tables)
    labelled, labelled_evidence = label_values_with_evidence(text)
    parse_method = str(structured.get("_parse_method") or "")
    labelled_source = "labelled_ocr" if parse_method in {"OCR", "PADDLE_OCR", "PDF_HYBRID"} else "labelled_text"

    chosen_evidence: dict[str, dict] = {}
    field_scores: dict[str, float] = {}

    current, current_source, current_ev = _pick([
        ("structured", structured.get("unit_name"), {"rule": "structured_input"}),
        ("table", table_values.get("unit_name"), table_evidence.get("unit_name")),
        ("spatial", spatial.get("unit_name"), spatial_evidence.get("unit_name")),
        ("template", template.get("unit_name"), template_evidence.get("unit_name")),
        (labelled_source, labelled.get("unit_name"), labelled_evidence.get("unit_name")),
    ])
    unit_code = structured.get("unit_code")
    if not unit_code and current and _looks_like_unit_code(current):
        unit_code, current = current.strip(), None
        current_source, current_ev = None, {}

    relation_conf = 0.0
    if current:
        unit_score, components = _field_score(current_source or "unknown", current_ev, structured)
        field_scores["current_unit"] = unit_score
        chosen_evidence["current_unit"] = {**current_ev, **components}
        relation_conf = min(0.99, unit_score)

    if not current:
        found_marker = _earliest_marker(text, CURRENT_MARKERS)
        if found_marker is not None:
            pos, marker_end, marker = found_marker
            after = text[marker_end:]
            # A later "trước đây công tác tại ..." clause is a former unit, not part of
            # this one's name; without the cut it is swallowed whole whenever OCR drops
            # the sentence punctuation _clean_unit relies on.
            marker_evidence = {
                "source": "narrative_text", "rule": "current_marker", "marker": marker,
            }
            current = _clean_unit(_cut_at_markers(after, FORMER_MARKERS))
            relation_conf = _RULE_PRIOR["current_marker"]
            field_scores["current_unit"] = relation_conf
            chosen_evidence["current_unit"] = {**marker_evidence, "score": relation_conf}

    former: list[str] = []
    # An explicitly labelled historical unit ("Đơn vị công tác cũ: ...") is the
    # strongest former-unit evidence there is, and it must never reach `current`.
    labelled_former, _, _ = _pick([
        ("structured", structured.get("former_unit_name"), {"rule": "structured_input"}),
        ("table", table_values.get("former_unit_name"), table_evidence.get("former_unit_name")),
        ("spatial", spatial.get("former_unit_name"), spatial_evidence.get("former_unit_name")),
        (labelled_source, labelled.get("former_unit_name"), labelled_evidence.get("former_unit_name")),
    ])
    if labelled_former:
        # A labelled historical unit gets the same cut the narrative branch below
        # already applies: "Nguyên đơn vị công tác: Cục A, hiện công tác tại Cục B"
        # on one line otherwise takes the rest of the line, current-unit clause and
        # all, and files Cục B as part of a former unit's name.
        former.append(_clean_unit(_cut_at_markers(labelled_former, CURRENT_MARKERS)))
    for marker in FORMER_MARKERS:
        found_marker = _earliest_marker(text, [marker])
        if found_marker is not None:
            pos, marker_end, _ = found_marker
            # Symmetrically: stop at whichever marker comes next, so a current-unit
            # clause running on from this one is not absorbed into the former unit.
            value = _clean_unit(
                _cut_at_markers(text[marker_end:], CURRENT_MARKERS + FORMER_MARKERS)
            )
            if value and value not in former:
                former.append(value)

    if not current:
        matches = re.findall(UNIT_PREFIXES + UNIT_NAME_BODY, text, flags=re.I)
        if len(matches) == 1:
            current = _clean_unit(matches[0])
            relation_conf = _RULE_PRIOR["single_unit_mention"]
            field_scores["current_unit"] = relation_conf
            chosen_evidence["current_unit"] = {
                "source": "narrative_text", "rule": "single_unit_mention", "score": relation_conf,
            }
        elif len(matches) > 1:
            relation_conf = 0.25

    name, name_source, name_ev = _pick([
        ("structured", structured.get("subject_name"), {"rule": "structured_input"}),
        ("table", table_values.get("subject_name"), table_evidence.get("subject_name")),
        ("template", template.get("subject_name"), template_evidence.get("subject_name")),
        ("spatial", spatial.get("subject_name"), spatial_evidence.get("subject_name")),
        (labelled_source, labelled.get("subject_name"), labelled_evidence.get("subject_name")),
    ])
    if not name:
        # ASCII-folded structure detection handles lowercase/unaccented narrative
        # input while slicing the value from the untouched raw text. A current/former
        # unit marker gives the otherwise ambiguous end boundary of the person's name.
        subject_marker = _earliest_marker(text, ["đồng chí"])
        unit_marker = _earliest_marker(text, CURRENT_MARKERS + FORMER_MARKERS)
        if subject_marker and unit_marker and subject_marker[1] <= unit_marker[0]:
            candidate = text[subject_marker[1]:unit_marker[0]].strip(" \t,:;-–—.")
            name = _bare_person_name(candidate)
            if name:
                name_source, name_ev = "narrative_text", {
                    "rule": "narrative_name", "conf": 1.0, "marker": subject_marker[2]
                }
    if not name:
        m = re.search(r"(?i:đồng chí)[^\S\n]*[:\-]?[^\S\n]*([A-ZÀ-ỸĐ][\wÀ-ỹđ]+(?:[^\S\n]+[A-ZÀ-ỸĐ][\wÀ-ỹđ]*){1,5})", text)
        if m:
            name = m.group(1).strip()
            name_source, name_ev = "narrative_text", {"rule": "narrative_name", "conf": 1.0}
    if not name:
        bare_name = _bare_person_name(text)
        if bare_name:
            name = bare_name
            name_source, name_ev = "direct_query", {"rule": "bare_name_query", "conf": 1.0}
    if name:
        score, components = _field_score(name_source or "unknown", name_ev, structured)
        field_scores["subject_name"] = score
        chosen_evidence["subject_name"] = {**name_ev, **components}

    code, code_source, code_ev = _pick([
        ("structured", structured.get("subject_code"), {"rule": "structured_input"}),
        ("table", table_values.get("subject_code"), table_evidence.get("subject_code")),
        ("template", template.get("subject_code"), template_evidence.get("subject_code")),
        ("spatial", spatial.get("subject_code"), spatial_evidence.get("subject_code")),
        (labelled_source, labelled.get("subject_code"), labelled_evidence.get("subject_code")),
    ])
    if not code:
        m = re.search(r"(?:cccd|cmnd|mã|số hiệu)[^\S\n]*[:\-]?[^\S\n]*([A-Z0-9\-/]{3,30})", text, flags=re.I)
        if m:
            code = m.group(1)
            code_source, code_ev = "narrative_text", {"rule": "regex_code", "conf": 1.0}
    if code:
        score, components = _field_score(code_source or "unknown", code_ev, structured)
        field_scores["subject_code"] = score
        chosen_evidence["subject_code"] = {**code_ev, **components}

    position, position_source, position_ev = _pick([
        ("structured", structured.get("position"), {"rule": "structured_input"}),
        ("table", table_values.get("position"), table_evidence.get("position")),
        ("spatial", spatial.get("position"), spatial_evidence.get("position")),
        (labelled_source, labelled.get("position"), labelled_evidence.get("position")),
    ])
    if not position:
        # The label itself can be qualified ("Chức vụ hiện tại: ..."). Without the
        # qualifier in the pattern the match stops after "chức vụ" and the value
        # carries the rest of the label — "hiện tại: trưởng công an phường ...".
        m = re.search(
            r"(?:chức vụ|chức danh|cấp bậc)(?:[^\S\n]+hiện[^\S\n]+(?:tại|nay))?"
            r"[^\S\n]*[:\-]?[^\S\n]*([^.;\n]{2,100})",
            text,
            flags=re.I,
        )
        if m:
            position = m.group(1).strip()
            position_source, position_ev = "narrative_text", {"rule": "regex_position", "conf": 1.0}
    if position:
        score, components = _field_score(position_source or "unknown", position_ev, structured)
        field_scores["position"] = score
        chosen_evidence["position"] = {**position_ev, **components}

    values = {"subject_name": name, "subject_code": code, "position": position, "current_unit": current}
    conf = _overall_extraction_confidence(field_scores, values)

    # A birth year is not one of the four fields the completeness score weighs and
    # has no column of its own, but it is a fact the document carries and the one
    # `PersonResolver` narrows a bare-name lookup on. Carrying it in `fields` keeps
    # it visible to the API projection (as `unit_code` already is) without a
    # migration, and an operator-supplied value outranks a labelled one.
    # Read from the same sources as every other field, in the same order. Taking it
    # from the text alone missed every scan that puts the label on its own line
    # ("Năm sinh:" above "1985"), which is the shape a transcript often has.
    birth_year, _, _ = _pick([
        ("structured", (structured.get("business_fields") or {}).get("birth_year"),
         {"rule": "structured_input"}),
        ("table", table_values.get("birth_year"), table_evidence.get("birth_year")),
        ("spatial", spatial.get("birth_year"), spatial_evidence.get("birth_year")),
        (labelled_source, labelled.get("birth_year"), labelled_evidence.get("birth_year")),
    ])
    if birth_year:
        # A label can carry a full date; the year is what is usable downstream, and
        # it is still a span of the input rather than a reformatted date.
        years = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", str(birth_year))
        birth_year = years[-1] if years else None

    return Extraction(
        name,
        code,
        position,
        current,
        former,
        conf,
        relation_conf,
        {
            "structured": structured,
            "spatial_evidence": spatial_evidence,
            "template_evidence": template_evidence,
            "table_evidence": table_evidence,
            "labelled_fields": labelled,
            "field_confidence": field_scores,
            "field_evidence": chosen_evidence,
            "confidence_method": "field-evidence-v1-uncalibrated",
            "unit_code": unit_code,
            "birth_year": str(birth_year) if birth_year not in (None, "") else None,
        },
        unit_code=unit_code,
    )
