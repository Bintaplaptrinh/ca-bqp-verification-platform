from __future__ import annotations
import random
import re
import unicodedata


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def typo(text: str, rng: random.Random) -> str:
    chars = list(text)
    idxs = [i for i, c in enumerate(chars) if c.isalpha()]
    if not idxs:
        return text
    i = rng.choice(idxs)
    op = rng.choice(["delete","swap","duplicate"])
    if op == "delete" and len(chars) > 5:
        chars.pop(i)
    elif op == "swap" and i < len(chars) - 1:
        chars[i], chars[i+1] = chars[i+1], chars[i]
    else:
        chars.insert(i, chars[i])
    return "".join(chars)


def acronym(text: str) -> str:
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]+", text)
    return "".join(t[0].upper() for t in tokens[:8])


def mutate_unit(name: str, noise_type: str, rng: random.Random) -> str:
    if noise_type == "NO_ACCENT":
        return strip_accents(name)
    if noise_type == "LOWERCASE":
        return name.lower()
    if noise_type == "TYPO_UNIT":
        return typo(name, rng)
    if noise_type == "ABBREVIATION":
        return acronym(name)
    if noise_type == "OCR_LIKE":
        return strip_accents(name).replace("rn","m").replace("cl","d")
    return name


def transform_text(text: str, noise_type: str) -> str:
    if noise_type == "NO_ACCENT":
        return strip_accents(text)
    if noise_type == "LOWERCASE":
        return text.lower()
    if noise_type == "OCR_LIKE":
        return strip_accents(text).replace("rn","m").replace("cl","d")
    return text
