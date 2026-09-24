"""Compatibility shim. Canonical normalization lives in cabqp.shared.normalization."""
from __future__ import annotations

try:
    from cabqp.shared.normalization import ascii_key, normalize_text, normalized_key
except ImportError:  # pipeline invoked from repository root without backend installed
    import re
    import unicodedata
    def normalized_key(value: str) -> str:
        value=unicodedata.normalize("NFC",str(value or "")).replace("–","-").replace("—","-")
        value=re.sub(r"\s+"," ",value).strip().casefold()
        value=re.sub(r"[^\wÀ-ỹ0-9 ]+"," ",value,flags=re.UNICODE)
        return re.sub(r"\s+"," ",value).strip()
    normalize_text=normalized_key
    def ascii_key(value: str) -> str:
        value=str(value or "").replace("Đ","D").replace("đ","d")
        return normalized_key("".join(c for c in unicodedata.normalize("NFD",value) if unicodedata.category(c)!="Mn"))

__all__=["normalize_text","normalized_key","ascii_key"]
