from __future__ import annotations

import re
from collections import defaultdict


BCA_PATTERNS = [
    r"\bVăn phòng Bộ\b",
    r"\bCục [A-ZÀ-Ỹ][^.;:\n]{2,150}",
    r"\bBộ Tư lệnh (?:Cảnh sát cơ động|Cảnh vệ)\b",
    r"\bVăn phòng Cơ quan Cảnh sát điều tra(?: Bộ Công an)?\b",
    r"\bViện [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bTrung tâm [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bHọc viện [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bTrường (?:Đại học|Cao đẳng|Văn hóa) [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bBệnh viện (?:19-8|30-4|199|Y học cổ truyền)[^.;:\n]{0,60}",
    r"\bCông an (?:tỉnh|thành phố) [A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9 \-–Đđ]{1,80}",
    r"\bCông an (?:xã|phường|đặc khu) [A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9 \-–Đđ]{1,80}",
]

BQP_PATTERNS = [
    r"\bBộ Tổng Tham mưu\b",
    r"\bTổng cục [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bCục [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bQuân khu [1-9]\b",
    r"\bQuân đoàn \d+\b",
    r"\bQuân chủng [A-ZÀ-Ỹ][^.;:\n]{2,100}",
    r"\bBinh chủng [A-ZÀ-Ỹ][^.;:\n]{2,100}",
    r"\bBộ Tư lệnh [A-ZÀ-Ỹ0-9][^.;:\n]{2,120}",
    r"\bBộ Chỉ huy quân sự (?:tỉnh|thành phố) [A-ZÀ-Ỹ][A-Za-zÀ-ỹ0-9 \-–Đđ]{1,80}",
    r"\bBan Chỉ huy Bộ đội Biên phòng [A-ZÀ-Ỹ][^.;:\n]{1,100}",
    r"\bSư đoàn \d+[A-Za-zÀ-ỹ0-9\- ]{0,70}",
    r"\bLữ đoàn \d+[A-Za-zÀ-ỹ0-9\- ]{0,70}",
    r"\bTrung đoàn \d+[A-Za-zÀ-ỹ0-9\- ]{0,70}",
    r"\bTiểu đoàn \d+[A-Za-zÀ-ỹ0-9\- ]{0,70}",
    r"\bHọc viện [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bTrường Sĩ quan [A-ZÀ-Ỹ0-9][^.;:\n]{1,110}",
    r"\bBệnh viện (?:Trung ương Quân đội|Quân y) [A-Za-zÀ-ỹ0-9\- ]{1,70}",
    r"\bViện [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bTrung tâm [A-ZÀ-Ỹ][^.;:\n]{2,130}",
    r"\bBinh đoàn \d+\b",
]

STOP_AFTER = re.compile(
    r"\s+(?:đã|đang|sẽ|và|cùng|tổ chức|chủ trì|tham dự|phối hợp|"
    r"thực hiện|triển khai|cho biết|tại|theo|trong)\b.*$",
    flags=re.I,
)


def clean_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n,;:.–-()[]{}")
    value = STOP_AFTER.sub("", value).strip()
    if len(value.split()) > 24:
        value = " ".join(value.split()[:24])
    return value.strip(" ,;:.-")


def extract_candidates(pages: list[dict], cfg: dict) -> list[dict]:
    result = []
    min_chars = int(cfg.get("min_candidate_chars", 5))
    max_chars = int(cfg.get("max_candidate_chars", 180))

    for page in pages:
        if not page.get("relevant"):
            continue

        org = page["organization_type"]
        patterns = BCA_PATTERNS if org == "BCA" else BQP_PATTERNS
        text = page["text"]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = clean_candidate(match.group(0))
                if not (min_chars <= len(name) <= max_chars):
                    continue

                result.append({
                    "canonical_name_candidate": name,
                    "organization_type": org,
                    "source_id": page["source_id"],
                    "source_role": page["source_role"],
                    "source_url": page["final_url"],
                    "source_sha256": page["sha256"],
                    "source_title": page.get("title", ""),
                })

    return result
