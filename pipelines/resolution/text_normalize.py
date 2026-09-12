"""Deterministic text normalization shared by the registry index and the resolver.

Two levels are defined and both are exact string equality after normalization.
No edit distance, no token overlap, no phonetic matching is performed here.

STRICT
    Unicode NFC, outer whitespace trimmed, inner whitespace collapsed to a
    single space, case folded. Diacritics are preserved.

ASCII_FOLDED
    STRICT plus Vietnamese d-stroke folded to d and all combining marks
    removed. This level exists because real inputs, in particular scanned or
    keyboard limited inputs, drop diacritics. The registry already carries
    generated no_accent aliases, but those aliases keep the d-stroke, so a
    folded level is still required for full coverage.

Any database backed implementation of UnitRegistryLookup must build its index
columns with these exact functions, otherwise the two implementations will
disagree on what counts as an exact match.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_CODE_TRIM_CHARS = ".,;:!?()[]{}<>\"'`"

_D_STROKE_MAP = str.maketrans({"\u0111": "d", "\u0110": "D"})  # d-stroke lower and upper


def normalize_name(value: str) -> str:
    """Return the STRICT normalized form of a unit name or alias."""
    text = unicodedata.normalize("NFC", value)
    text = _WHITESPACE.sub(" ", text).strip()
    return text.casefold()


def fold_ascii(value: str) -> str:
    """Return the ASCII_FOLDED normalized form of a unit name or alias."""
    text = unicodedata.normalize("NFC", value)
    text = text.translate(_D_STROKE_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = _WHITESPACE.sub(" ", text).strip()
    return text.casefold()


def normalize_code(value: str) -> str:
    """Return the normalized form of a unit code.

    Codes are treated as ASCII identifiers: surrounding punctuation is removed,
    inner whitespace is collapsed and the result is upper cased. Underscores,
    hyphens and digits are preserved because they carry meaning in codes such
    as BCA_CA_HN or BQP_F308.
    """
    text = unicodedata.normalize("NFC", value)
    text = _WHITESPACE.sub(" ", text).strip()
    text = text.strip(_CODE_TRIM_CHARS).strip()
    return text.upper()


def is_blank(value: str | None) -> bool:
    """Return True when the value carries no usable content."""
    return value is None or not value.strip()
