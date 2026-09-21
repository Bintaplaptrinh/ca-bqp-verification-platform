import re

from cabqp.shared.normalization import ascii_key

# Conservative rule-first subject-group classifier.
# Unit membership alone never proves force membership.

KNOWN_GROUPS = {"CAND", "QUAN_NHAN", "CO_YEU_HUONG_LUONG_NHU_QUAN_NHAN"}
# Vietnamese puts copulas and qualifiers between the negation and the noun
# ("không còn là sĩ quan", "không phải một quân nhân"). Anchoring the negation directly
# against the keyword missed those and reported the subject as serving personnel, so a
# short run of filler words is allowed — bounded, so the match cannot span a clause.
_NEGATION_FILLER = r"(?:\s+(?:la|mot|dang|hien|thuoc|trong|bien\s+che)){0,3}"
NEGATION = re.compile(
    r"(?:khong\s+phai|khong\s+thuoc|khong\s+la|chua\s+phai|chua\s+la|khong\s+con|thoi\s+khong\s+con)"
    + _NEGATION_FILLER
    + r"\s+$",
    re.I,
)

# A historical role is not evidence of present membership when the same clause says
# the person has since left service. Keep this rule local to the keyword occurrence:
# an earlier historical mention must not suppress a separate current affirmative.
PAST_ROLE = re.compile(r"(?:da\s+)?tung\s+la\s+$|truoc\s+day\s+(?:la\s+)?$|nguyen\s+la\s+$", re.I)
CURRENT_EXIT = re.compile(
    r"\b(?:nhung\s+)?(?:nay|hien\s+nay|hien\s+tai)\s+"
    r"(?:da\s+)?(?:khong\s+con|khong)\s+"
    r"(?:cong\s+tac|phuc\s+vu|thuoc|trong\s+bien\s+che)\b"
    r"|\b(?:da\s+)?(?:thoi\s+cong\s+tac|xuat\s+ngu|chuyen\s+nganh)\b",
    re.I,
)


def _positive_not_negated(text: str, keyword: str) -> bool:
    start = 0
    key = ascii_key(keyword)
    while True:
        idx = text.find(key, start)
        if idx < 0:
            return False
        prefix = text[max(0, idx - 40):idx]
        suffix = text[idx + len(key):idx + len(key) + 140]
        historical_then_left = bool(PAST_ROLE.search(prefix) and CURRENT_EXIT.search(suffix))
        if not NEGATION.search(prefix) and not historical_then_left:
            return True
        start = idx + len(key)


def classify_subject_group(*, organization_type: str, position: str | None, text: str, fields: dict | None = None):
    f = fields or {}
    explicit = f.get("subject_group")
    if explicit:
        explicit = str(explicit).strip().upper()
        if explicit in KNOWN_GROUPS:
            return explicit, 1.0, "EXPLICIT_FIELD"
        return None, 0.0, "INVALID_EXPLICIT_GROUP"

    # Classification is structural, so match on an ASCII/lowercase copy while the
    # caller retains the untouched document as evidence.
    t = ascii_key(" ".join([position or "", text or ""]))

    if organization_type == "BCA":
        for keyword in ["sĩ quan công an", "hạ sĩ quan công an", "chiến sĩ công an", "công an nhân dân", "cand"]:
            if _positive_not_negated(t, keyword):
                return "CAND", 0.95, "RULE_TEXT"

    if organization_type == "BQP":
        if _positive_not_negated(t, "cơ yếu"):
            return "CO_YEU_HUONG_LUONG_NHU_QUAN_NHAN", 0.90, "RULE_TEXT"
        for keyword in ["quân nhân", "sĩ quan", "hạ sĩ quan", "binh sĩ", "quân đội nhân dân"]:
            if _positive_not_negated(t, keyword):
                return "QUAN_NHAN", 0.92, "RULE_TEXT"

    return None, 0.0, "INSUFFICIENT_EVIDENCE"
