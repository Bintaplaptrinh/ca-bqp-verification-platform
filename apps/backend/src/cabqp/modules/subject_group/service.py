import re

# Conservative rule-first subject-group classifier.
# Unit membership alone never proves force membership.

KNOWN_GROUPS = {"CAND", "QUAN_NHAN", "CO_YEU_HUONG_LUONG_NHU_QUAN_NHAN"}
# Vietnamese puts copulas and qualifiers between the negation and the noun
# ("không còn là sĩ quan", "không phải một quân nhân"). Anchoring the negation directly
# against the keyword missed those and reported the subject as serving personnel, so a
# short run of filler words is allowed — bounded, so the match cannot span a clause.
_NEGATION_FILLER = r"(?:\s+(?:là|một|đang|hiện|thuộc|trong|biên\s+chế)){0,3}"
NEGATION = re.compile(
    r"(?:không\s+phải|không\s+thuộc|không\s+là|chưa\s+phải|chưa\s+là|không\s+còn|thôi\s+không\s+còn)"
    + _NEGATION_FILLER
    + r"\s+$",
    re.I,
)


def _positive_not_negated(text: str, keyword: str) -> bool:
    start = 0
    key = keyword.casefold()
    while True:
        idx = text.find(key, start)
        if idx < 0:
            return False
        prefix = text[max(0, idx - 40):idx]
        if not NEGATION.search(prefix):
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

    t = " ".join([position or "", text or ""]).casefold()

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
