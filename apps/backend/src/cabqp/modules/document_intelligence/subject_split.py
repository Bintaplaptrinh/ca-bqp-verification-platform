from __future__ import annotations

from dataclasses import dataclass

from cabqp.modules.document_intelligence.extraction import (
    _LABEL_FUZZY_THRESHOLD,
    LABELS,
    _label_score,
)
from cabqp.shared.normalization import ascii_key

# Splitting a scanned/hybrid document by OCR line geometry is materially riskier than
# splitting clean text by line breaks: OCR line ordering and column layout are not
# reliable enough to trust a boundary decision on. Per the project's "abstain rather
# than force a low-confidence decision" principle, v1 only auto-splits parse methods
# that give us trustworthy line breaks and defers OCR-sourced multi-subject documents
# to human review instead of guessing a geometric split.
_OCR_PARSE_METHODS = {"OCR", "PADDLE_OCR", "PDF_HYBRID"}

MULTIPLE_SUBJECTS_OCR_UNSUPPORTED = "MULTIPLE_SUBJECTS_OCR_UNSUPPORTED"
MULTIPLE_SUBJECTS_AMBIGUOUS_BOUNDARY = "MULTIPLE_SUBJECTS_AMBIGUOUS_BOUNDARY"


@dataclass
class SubjectBlock:
    index: int
    text: str
    ambiguous: bool
    ambiguous_reason: str | None = None


def _is_name_label_line(line: str) -> bool:
    label_part = line.split(":", 1)[0]
    key = ascii_key(label_part).rstrip(":")
    return _label_score(key, LABELS["subject_name"]) >= _LABEL_FUZZY_THRESHOLD


def detect_subject_blocks(text: str, parse_method: str | None) -> list[SubjectBlock]:
    """Split free text into one block per detected person.

    A block starts at each line matching a "Họ và tên"-style label and runs to the
    line before the next such label (or EOF). Zero or one name-label line returns the
    whole document as a single, non-ambiguous block: existing single-subject behavior
    is completely unchanged. `extract()` itself is never modified by this module; the
    caller runs it once per returned block.
    """
    lines = (text or "").splitlines()
    label_line_indexes = [i for i, line in enumerate(lines) if line.strip() and _is_name_label_line(line)]

    if len(label_line_indexes) <= 1:
        return [SubjectBlock(index=0, text=text or "", ambiguous=False)]

    if (parse_method or "") in _OCR_PARSE_METHODS:
        return [
            SubjectBlock(
                index=0,
                text=text or "",
                ambiguous=True,
                ambiguous_reason=MULTIPLE_SUBJECTS_OCR_UNSUPPORTED,
            )
        ]

    blocks: list[SubjectBlock] = []
    boundaries = [*label_line_indexes, len(lines)]
    # boundaries has N+1 marks for N blocks by construction; zip(a, a[1:]) intentionally
    # yields N pairs, so strict=True would always raise here.
    for block_index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):  # noqa: B905
        block_lines = lines[start:end]
        block_text = "\n".join(block_lines).strip()
        # Content beyond the label line itself: if nothing follows before the next
        # name label, the boundary can't be trusted enough to isolate this person's
        # other fields, so this block abstains to review rather than guessing.
        remaining = "\n".join(block_lines[1:]).strip()
        ambiguous = not remaining
        blocks.append(
            SubjectBlock(
                index=block_index,
                text=block_text,
                ambiguous=ambiguous,
                ambiguous_reason=MULTIPLE_SUBJECTS_AMBIGUOUS_BOUNDARY if ambiguous else None,
            )
        )
    return blocks
