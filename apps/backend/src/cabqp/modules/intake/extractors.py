"""Document Extractors & Parsers for CA/BQP Verification Platform.

Supports:
- PDF: Text extraction via pdfplumber/pypdf (with graceful fallback)
- Word (.docx): Document paragraphs extraction via python-docx
- Text (.txt): Direct decoding
- Images (.png, .jpg, .jpeg) & Scanned PDFs: VietOCR / Tesseract pipeline (lazy loaded)
"""

import io
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger("cabqp.extractors")

# VietOCR lazy loader cache
_VIETOCR_PREDICTOR = None


def get_vietocr_predictor():
    """
    Lazy load VietOCR predictor when required.
    Ensures server does not crash on startup if weights or heavy libraries are missing.
    """
    global _VIETOCR_PREDICTOR
    if _VIETOCR_PREDICTOR is not None:
        return _VIETOCR_PREDICTOR

    try:
        from PIL import Image
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        config = Cfg.load_config_from_name("vgg_transformer")
        # CPU default for standard container environments
        config["device"] = "cpu"
        config["predictor"]["beamsearch"] = False
        _VIETOCR_PREDICTOR = Predictor(config)
        logger.info("VietOCR Predictor successfully initialized")
        return _VIETOCR_PREDICTOR
    except Exception as exc:
        logger.warning("VietOCR not available or dependencies missing: %s", exc)
        return None


class DocumentParser:
    """Intelligent document parser selecting the fastest and most accurate extraction engine."""

    @classmethod
    def extract_text(cls, file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> Tuple[str, str]:
        """
        Extract text from file bytes based on file extension and MIME type.
        Returns:
            Tuple[extracted_text, engine_used]
        """
        filename_lower = (filename or "").lower()

        # 1. Plain Text (.txt, .csv, .log)
        if filename_lower.endswith(".txt") or filename_lower.endswith(".csv") or (content_type and "text/plain" in content_type):
            return cls._extract_from_text(file_bytes), "plain_text"

        # 2. Word Documents (.docx)
        if filename_lower.endswith(".docx") or (content_type and "wordprocessingml" in content_type):
            return cls._extract_from_docx(file_bytes), "python_docx"

        # 3. PDF Documents (.pdf)
        if filename_lower.endswith(".pdf") or (content_type and "pdf" in content_type):
            return cls._extract_from_pdf(file_bytes), "pdf_extractor"

        # 4. Image Files (.png, .jpg, .jpeg, .webp, .tiff)
        if (
            filename_lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"))
            or (content_type and content_type.startswith("image/"))
        ):
            return cls._extract_from_image(file_bytes), "vietocr_image"

        # Fallback text decoding
        return cls._extract_fallback(file_bytes, filename), "fallback_decoder"

    @classmethod
    def _extract_from_text(cls, file_bytes: bytes) -> str:
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="ignore")

    @classmethod
    def _extract_from_docx(cls, file_bytes: bytes) -> str:
        try:
            import docx

            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            # Also extract from tables inside Word doc
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        paragraphs.append(row_text)
            return "\n".join(paragraphs)
        except Exception as exc:
            logger.warning("python-docx extraction failed: %s. Falling back.", exc)
            return cls._extract_fallback(file_bytes, "document.docx")

    @classmethod
    def _extract_from_pdf(cls, file_bytes: bytes) -> str:
        # Try pdfplumber first (best layout and table extraction)
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                extracted = []
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        extracted.append(text)
                if extracted:
                    return "\n".join(extracted)
        except Exception as exc:
            logger.debug("pdfplumber not available or failed: %s", exc)

        # Try pypdf next
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(file_bytes))
            extracted = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    extracted.append(text)
            if extracted:
                return "\n".join(extracted)
        except Exception as exc:
            logger.debug("pypdf not available or failed: %s", exc)

        # If PDF is scanned without digital text, attempt OCR via VietOCR / pdf2image if installed
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, first_page=1, last_page=3)
            ocr_text = []
            predictor = get_vietocr_predictor()
            if predictor:
                for img in images:
                    ocr_text.append(predictor.predict(img))
                if ocr_text:
                    return "\n".join(ocr_text)
        except Exception as exc:
            logger.debug("PDF image OCR failed: %s", exc)

        return cls._extract_fallback(file_bytes, "document.pdf")

    @classmethod
    def _extract_from_image(cls, file_bytes: bytes) -> str:
        """Runs VietOCR on image bytes with fallback to pytesseract."""
        # 1. Try VietOCR (specialized for Vietnamese)
        predictor = get_vietocr_predictor()
        if predictor:
            try:
                from PIL import Image

                image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                text = predictor.predict(image)
                if text and text.strip():
                    return text
            except Exception as exc:
                logger.warning("VietOCR prediction failed: %s", exc)

        # 2. Try pytesseract as fallback
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(image, lang="vie+eng")
            if text and text.strip():
                return text
        except Exception as exc:
            logger.debug("pytesseract failed: %s", exc)

        return "Nội dung hình ảnh (Chưa có dịch vụ OCR khả dụng)"

    @classmethod
    def _extract_fallback(cls, file_bytes: bytes, filename: str) -> str:
        """Extract recognizable Vietnamese and ASCII text patterns from binary streams."""
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore")
            # Extract printable chunks
            import re
            words = re.findall(r"[\w\s,.:;/–—\-]{4,}", decoded)
            joined = " ".join(w.strip() for w in words[:50] if len(w.strip()) > 3)
            if len(joined) > 20:
                return joined
        except Exception:
            pass
        return f"Tài liệu đính kèm: {filename}"
