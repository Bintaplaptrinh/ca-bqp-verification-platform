"""Input Processing & Intake Pipeline for CA/BQP Verification Platform.

Standard: Quality-first 2026 Production Architecture.
Implements Section 1.2, Section 3.1 & Invariant 3:
  1. Two intake channels (Direct Text / File Upload) converging to a unified intermediate record.
  2. Extraction of subject identity, identifier patterns (CA-xxxx, BQP-xxxx, CCCD).
  3. Distinction between CURRENT_WORK_UNIT and FORMER_WORK_UNIT (Invariant 3: Do NOT pick first ORG).
  4. Vietnamese Unicode NFC normalization and noise cleaning.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class NormalizedRecord(BaseModel):
    """Unified intermediate record schema (CASE + NORMALIZED RECORD)."""
    full_name: str
    birth_year: str
    identifier: Optional[str] = None
    cccd: Optional[str] = None
    position: Optional[str] = None
    current_work_unit: str
    former_work_units: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None
    input_channel: str = Field(..., description="'DIRECT_TEXT' or 'FILE_UPLOAD'")
    extraction_confidence: float = 1.0


class InputProcessor:
    """Core processor for text normalization and entity/relation extraction."""

    # Regex patterns for high-precision entity extraction
    CA_IDENTIFIER_PATTERN = re.compile(r"\b(CA[-\s]?\d{4,8})\b", re.IGNORECASE)
    BQP_IDENTIFIER_PATTERN = re.compile(r"\b(BQP[-\s]?\d{4,8}|QD[-\s]?\d{4,8})\b", re.IGNORECASE)
    CCCD_PATTERN = re.compile(r"\b(\d{12})\b")
    BIRTH_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20[0-2]\d)\b")

    # Keyword indicators for current vs historical work unit relations
    CURRENT_MARKERS = [
        "hiện công tác tại",
        "đang công tác tại",
        "đơn vị hiện tại",
        "hiện đang giữ chức",
        "bổ nhiệm giữ chức vụ",
        "đang làm việc tại",
        "công tác tại",
        "đơn vị:",
        "cơ quan:",
    ]

    FORMER_MARKERS = [
        "trước đây công tác tại",
        "nguyên là",
        "từng công tác tại",
        "chuyển công tác từ",
        "đơn vị cũ",
        "nguyên cán bộ",
        "nguyên sĩ quan",
        "nguyên chiến sĩ",
        "trước công tác ở",
    ]

    @classmethod
    def normalize_text(cls, text: Optional[str]) -> str:
        """Applies Unicode NFC normalization and collapses irregular whitespaces."""
        if not text:
            return ""
        # NFC standard normalization
        normalized = unicodedata.normalize("NFC", text.strip())
        # Replace non-breaking spaces and collapse tabs/newlines
        cleaned = re.sub(r"[\r\n\t]+", " ", normalized)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    @classmethod
    def extract_identifiers(cls, text: str) -> Dict[str, Optional[str]]:
        """Extracts security numbers, defense codes and citizen IDs."""
        result = {
            "ca_code": None,
            "bqp_code": None,
            "cccd": None,
            "birth_year": None,
        }

        ca_match = cls.CA_IDENTIFIER_PATTERN.search(text)
        if ca_match:
            result["ca_code"] = ca_match.group(1).upper().replace(" ", "-")

        bqp_match = cls.BQP_IDENTIFIER_PATTERN.search(text)
        if bqp_match:
            result["bqp_code"] = bqp_match.group(1).upper().replace(" ", "-")

        cccd_match = cls.CCCD_PATTERN.search(text)
        if cccd_match:
            result["cccd"] = cccd_match.group(1)

        by_match = cls.BIRTH_YEAR_PATTERN.search(text)
        if by_match:
            result["birth_year"] = by_match.group(1)

        return result

    @classmethod
    def extract_work_units(cls, text: str, default_unit: Optional[str] = None) -> Tuple[str, List[str]]:
        """
        Enforces Invariant 3:
        If multiple organizations are present in text, resolve CURRENT_WORK_UNIT;
        do NOT simply pick the first organization that appears.
        """
        norm_text = cls.normalize_text(text)
        lower_text = norm_text.lower()

        current_unit = default_unit or ""
        former_units = []

        # Check for explicit former unit mentions
        for marker in cls.FORMER_MARKERS:
            pattern = re.escape(marker)
            for match in re.finditer(pattern, lower_text):
                idx = match.end()
                snippet = norm_text[idx:idx + 100].lstrip(" :-–\t")
                chunk = re.split(r"[,;.\n\r]|(?:\s+-\s+)", snippet)[0].strip()
                if chunk and chunk not in former_units:
                    former_units.append(chunk)

        # Check for explicit current unit mentions
        for marker in cls.CURRENT_MARKERS:
            pattern = re.escape(marker)
            match = re.search(pattern, lower_text)
            if match:
                idx = match.end()
                snippet = norm_text[idx:idx + 120].lstrip(" :-–\t")
                chunk = re.split(r"[,;.\n\r]|(?:\s+-\s+)", snippet)[0].strip()
                if chunk:
                    current_unit = chunk
                    break

        # Fallback to default if no explicit marker found
        if not current_unit and default_unit:
            current_unit = default_unit

        return cls.normalize_text(current_unit), [cls.normalize_text(u) for u in former_units]

    @classmethod
    def process_direct_intake(
        cls,
        full_name: str,
        birth_year: str,
        current_unit: Optional[str] = None,
        identifier: Optional[str] = None,
        position: Optional[str] = None,
        department: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> NormalizedRecord:
        """Processes structured form intake and returns a canonical NormalizedRecord."""
        norm_name = cls.normalize_text(full_name)
        norm_birth = cls.normalize_text(birth_year) or "1985"
        norm_unit = cls.normalize_text(current_unit or department or "")
        norm_pos = cls.normalize_text(position or "")
        norm_id = cls.normalize_text(identifier or "").upper()

        combined_text = f"{norm_name} {norm_birth} {norm_pos} {norm_unit} {norm_id} {raw_text or ''}"
        extracted_ids = cls.extract_identifiers(combined_text)

        # Invariant 3: Resolve current vs former units if raw_text is supplied
        curr_unit, formers = cls.extract_work_units(combined_text, default_unit=norm_unit)

        # Prefer extracted structured identifier
        final_id = norm_id or extracted_ids["ca_code"] or extracted_ids["bqp_code"]
        final_cccd = extracted_ids["cccd"]

        return NormalizedRecord(
            full_name=norm_name,
            birth_year=extracted_ids["birth_year"] or norm_birth,
            identifier=final_id,
            cccd=final_cccd,
            position=norm_pos or None,
            current_work_unit=curr_unit or "Chưa rõ đơn vị",
            former_work_units=formers,
            raw_text=raw_text,
            input_channel="DIRECT_TEXT",
            extraction_confidence=0.98 if norm_name and (final_id or curr_unit) else 0.85,
        )

    @classmethod
    def process_file_intake(
        cls,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        extracted_text_hint: Optional[str] = None,
    ) -> NormalizedRecord:
        """
        Processes file/document intake (PDF, image, docx) through text/metadata extraction.
        Convergences into the same intermediate schema.
        """
        text_content = extracted_text_hint or ""
        engine_used = "direct_hint"

        if not text_content:
            from .extractors import DocumentParser

            text_content, engine_used = DocumentParser.extract_text(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )

        norm_text = cls.normalize_text(text_content)
        ids = cls.extract_identifiers(norm_text)
        curr_unit, formers = cls.extract_work_units(norm_text)

        # Heuristic extraction for name (e.g. following 'Họ và tên:', 'Họ tên:', 'Đồng chí:')
        name_match = re.search(
            r"(?:họ và tên|họ tên|cán bộ|đồng chí|khen thưởng|bổ nhiệm)\s*[:\-–]\s*([A-ZÀ-Ỹa-zà-ỹ\s]+)",
            norm_text,
            re.IGNORECASE,
        )
        if name_match:
            extracted_name = name_match.group(1).split("\n")[0].split(",")[0].strip()
        else:
            # Fallback to readable filename parts if name not found in text
            cleaned_fname = re.sub(r"^[0-9_\-]+", "", filename.rsplit(".", 1)[0]).replace("_", " ").replace("-", " ").strip()
            extracted_name = cleaned_fname if len(cleaned_fname) >= 2 else "Chưa rõ họ tên"

        # Extract position if available
        pos_match = re.search(r"(?:chức vụ|cấp bậc|vị trí)\s*[:\-–]\s*([A-ZÀ-Ỹa-zà-ỹ0-9\s]+)", norm_text, re.IGNORECASE)
        extracted_pos = pos_match.group(1).split("\n")[0].split(",")[0].strip() if pos_match else "Cán bộ theo hồ sơ"

        return NormalizedRecord(
            full_name=extracted_name or "Chưa rõ họ tên",
            birth_year=ids["birth_year"] or "1985",
            identifier=ids["ca_code"] or ids["bqp_code"] or ids["cccd"],
            cccd=ids["cccd"],
            position=extracted_pos,
            current_work_unit=curr_unit or "Đơn vị trên tài liệu",
            former_work_units=formers,
            raw_text=norm_text,
            input_channel="FILE_UPLOAD",
            extraction_confidence=0.92 if (ids["ca_code"] or ids["bqp_code"] or ids["cccd"]) else 0.78,
        )
