import re
import unicodedata


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", str(value or ""))
    value = value.replace("–", "-").replace("—", "-")
    value = value.casefold().strip()
    value = re.sub(r"[\s\-_]+", " ", value)
    value = re.sub(r"[^\w\sÀ-ỹđ]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def ascii_key(value: str) -> str:
    v = str(value or "").replace("Đ", "D").replace("đ", "d")
    v = "".join(c for c in unicodedata.normalize("NFD", v) if unicodedata.category(c) != "Mn")
    return normalize_text(v)


# Backward-compatible name used by registry ingestion.
normalized_key = normalize_text
