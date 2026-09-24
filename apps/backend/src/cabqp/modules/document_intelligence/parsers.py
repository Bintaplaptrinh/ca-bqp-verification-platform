from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from openpyxl import load_workbook

from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.modules.document_intelligence.ocr import OcrLine, image_from_bytes, run_ocr
from cabqp.modules.document_intelligence.quality import confidence_from_quality, evaluate_quality
from cabqp.modules.document_intelligence.router import RoutingDecision, route_input
from cabqp.modules.document_intelligence.table import (
    extract_docx_tables,
    extract_pdf_table_results,
    extract_scan_structure,
    looks_like_table_ocr_lines,
    scan_structure_contains_table,
    tables_from_scan_structure,
)
from cabqp.shared.enums import InputKind, ParseMethod
from cabqp.shared.metrics import INPUT_ROUTING, OCR_QUALITY
from cabqp.shared.settings import get_settings

logger=logging.getLogger(__name__)


@dataclass(slots=True)
class ParseResult:
    text: str
    confidence: float
    method: str
    input_kind: str
    quality: dict
    evidence: dict=field(default_factory=dict)
    ocr_lines: list[OcrLine]=field(default_factory=list)
    tables: list=field(default_factory=list)


def _text_result(text: str, method: ParseMethod, decision: RoutingDecision, *, tables=None, evidence=None) -> ParseResult:
    q=evaluate_quality(text,source="PARSER")
    return ParseResult(text,confidence_from_quality(q),method.value,decision.kind.value,q.to_dict(),evidence or {"routing":decision.to_dict()},[],tables or [])


def _ocr_image(content: bytes, *, page: int=1, detector: str|None=None, recognizer: str|None=None) -> tuple[list[OcrLine],dict,float,dict]:
    image=image_from_bytes(content)
    settings=get_settings()
    pixels=int(image.width)*int(image.height)
    if pixels > settings.document_max_image_pixels:
        raise DocumentLimitError("IMAGE_PIXEL_LIMIT_EXCEEDED", pixels=pixels, limit=settings.document_max_image_pixels)
    run=run_ocr(image,page=page,detector=detector,recognizer=recognizer)
    engine=run.evidence.get("selected_engine","unknown")
    OCR_QUALITY.labels(engine=engine,gate_result=str(run.quality.get("gate_result","FAIL")).casefold()).inc()
    return run.lines,run.quality,run.confidence,run.evidence


def parse_document(file_name: str, content: bytes) -> ParseResult:
    settings=get_settings()
    deadline=time.monotonic()+settings.document_soft_timeout_seconds
    decision=route_input(file_name,content)
    kind=decision.kind
    INPUT_ROUTING.labels(kind=kind.value, decision=decision.reason[:80]).inc()
    if kind == InputKind.TEXT:
        text=content.decode("utf-8-sig",errors="replace")
        return _text_result(
            text,ParseMethod.PLAIN_TEXT,decision,
            evidence={"routing":decision.to_dict(),"source_preview_text":text[:50_000]},
        )
    if kind == InputKind.DOCX:
        doc=DocxDocument(BytesIO(content))
        text="\n".join(p.text for p in doc.paragraphs if p.text.strip())
        tables=extract_docx_tables(doc)
        if len(tables) > settings.document_max_tables:
            raise DocumentLimitError("TABLE_LIMIT_EXCEEDED", tables=len(tables), limit=settings.document_max_tables)
        return _text_result(
            text, ParseMethod.DOCX_TEXT, decision, tables=tables,
            evidence={
                "routing": decision.to_dict(),
                "table_sources": [{"source": "docx-native"} for _ in tables],
                "source_preview_text": text[:50_000],
            },
        )
    if kind in {InputKind.TABULAR_LIST,InputKind.KEY_VALUE_SHEET}:
        # The parser exposes a preview only. TABULAR_LIST is owned by bulk ingestion and must not become one Case.
        ext=Path(file_name).suffix.lower()
        if ext in {".xlsx",".xlsm"}:
            wb=load_workbook(BytesIO(content),read_only=True,data_only=True)
            if len(wb.worksheets) > settings.document_max_worksheets:
                raise DocumentLimitError("WORKSHEET_LIMIT_EXCEEDED", worksheets=len(wb.worksheets), limit=settings.document_max_worksheets)
            lines=[]; total_rows=0
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    total_rows += 1
                    if total_rows > settings.document_max_spreadsheet_rows:
                        raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=total_rows, limit=settings.document_max_spreadsheet_rows)
                    vals=[str(v) for v in row if v not in (None,"")]
                    if vals: lines.append("\t".join(vals))
            text="\n".join(lines)
        elif ext == ".xls":
            import xlrd
            book=xlrd.open_workbook(file_contents=content)
            if book.nsheets > settings.document_max_worksheets:
                raise DocumentLimitError("WORKSHEET_LIMIT_EXCEEDED", worksheets=book.nsheets, limit=settings.document_max_worksheets)
            lines=[]; total_rows=0
            for sheet in book.sheets():
                total_rows += sheet.nrows
                if total_rows > settings.document_max_spreadsheet_rows:
                    raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=total_rows, limit=settings.document_max_spreadsheet_rows)
                for row_idx in range(sheet.nrows):
                    vals=[str(v) for v in sheet.row_values(row_idx) if v not in (None,"")]
                    if vals: lines.append("\t".join(vals))
            text="\n".join(lines)
        else:
            # CSV/text tabular inputs have already been routed, but retain an independent
            # guard here for direct parser callers and future refactors.
            line_count=content.count(b"\n")+1
            if line_count > settings.document_max_spreadsheet_rows:
                raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=line_count, limit=settings.document_max_spreadsheet_rows)
            text=content.decode("utf-8-sig",errors="replace")
        method=ParseMethod.TABULAR_PROBE if kind==InputKind.TABULAR_LIST else ParseMethod.KEY_VALUE
        preview_rows=[line.split("\t") for line in text.splitlines() if line.strip()][:50]
        return _text_result(
            text,method,decision,
            evidence={
                "routing":decision.to_dict(),
                "bulk_required":kind==InputKind.TABULAR_LIST,
                "source_preview_rows":preview_rows,
            },
        )
    if kind == InputKind.PDF_TEXT:
        import fitz
        doc=fitz.open(stream=content,filetype="pdf")
        texts=[]
        for p in doc:
            if time.monotonic() > deadline:
                doc.close()
                raise DocumentLimitError("DOCUMENT_TIME_BUDGET_EXCEEDED", limit_seconds=settings.document_soft_timeout_seconds)
            if p.rotation: p.set_rotation(0)
            texts.append(p.get_text("text") or "")
        doc.close()
        text="\n".join(texts)
        if time.monotonic() > deadline:
            raise DocumentLimitError("DOCUMENT_TIME_BUDGET_EXCEEDED", limit_seconds=settings.document_soft_timeout_seconds)
        native_table_results=extract_pdf_table_results(content)
        if time.monotonic() > deadline:
            raise DocumentLimitError("DOCUMENT_TIME_BUDGET_EXCEEDED", limit_seconds=settings.document_soft_timeout_seconds)
        tables=[x["cells"] for x in native_table_results]
        if len(tables) > settings.document_max_tables:
            raise DocumentLimitError("TABLE_LIMIT_EXCEEDED", tables=len(tables), limit=settings.document_max_tables)
        return _text_result(
            text, ParseMethod.PDF_TEXT, decision, tables=tables,
            evidence={
                "routing": decision.to_dict(),
                "table_sources": [{k:v for k,v in x.items() if k != "cells"} for x in native_table_results],
            },
        )
    if kind in {InputKind.PDF_SCAN,InputKind.PDF_HYBRID}:
        import fitz
        from PIL import Image
        doc=fitz.open(stream=content,filetype="pdf")
        texts=[]; all_lines=[]; qualities=[]; scan_table_pages=[]; scan_structures={}; scan_tables=[]; ocr_page_evidence={}; ocr_page_quality={}
        route_by_page={x.page:x.route for x in decision.page_route_map}
        ocr_page_count=sum(1 for route in route_by_page.values() if route == "OCR")
        if ocr_page_count > settings.document_max_ocr_pages:
            doc.close()
            raise DocumentLimitError("OCR_PAGE_LIMIT_EXCEEDED", pages=ocr_page_count, limit=settings.document_max_ocr_pages)
        raster_pixels=0
        for idx,p in enumerate(doc):
            if time.monotonic() > deadline:
                doc.close()
                raise DocumentLimitError("DOCUMENT_TIME_BUDGET_EXCEEDED", limit_seconds=settings.document_soft_timeout_seconds)
            page_no=idx+1
            if route_by_page.get(page_no,"OCR") == "TEXT":
                page_text=p.get_text("text") or ""
                texts.append(page_text)
                # A text-layer page still has to clear the gate: a broken font renders as
                # U+FFFD, which the charset metric catches. Skipping the check here let a
                # hybrid document pass whenever its OCR pages happened to be clean.
                if page_text.strip():
                    qualities.append(evaluate_quality(page_text,source="PARSER").to_dict())
                continue
            pix=p.get_pixmap(matrix=fitz.Matrix(2.0,2.0),alpha=False)
            page_pixels=int(pix.width)*int(pix.height)
            if page_pixels > settings.document_max_image_pixels:
                doc.close()
                raise DocumentLimitError("IMAGE_PIXEL_LIMIT_EXCEEDED", page=page_no, pixels=page_pixels, limit=settings.document_max_image_pixels)
            raster_pixels += page_pixels
            if raster_pixels > settings.document_max_raster_pixels:
                doc.close()
                raise DocumentLimitError("RASTER_PIXEL_LIMIT_EXCEEDED", pixels=raster_pixels, limit=settings.document_max_raster_pixels)
            image=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
            run=run_ocr(image,page=page_no)
            lines=run.lines
            ocr_page_evidence[str(page_no)]=run.evidence
            ocr_page_quality[str(page_no)]=run.quality
            all_lines.extend(lines); texts.append("\n".join(x.text for x in lines))
            OCR_QUALITY.labels(engine=run.evidence.get("selected_engine","unknown"),gate_result=str(run.quality.get("gate_result","FAIL")).casefold()).inc()
            qualities.append(run.quality)
            if get_settings().scan_table_detection_enabled:
                structure=extract_scan_structure(image, force=looks_like_table_ocr_lines(lines))
                if structure:
                    scan_structures[str(page_no)]=structure
                if scan_structure_contains_table(structure):
                    scan_table_pages.append(page_no)
                    for table in tables_from_scan_structure(structure):
                        scan_tables.append({**table, "page": page_no, "source": "pp-structure-v3"})
        doc.close()
        text="\n".join(texts)
        # Full document gate is conservative: any page failure requires review.
        q=evaluate_quality(text,ocr_scores=[x.conf for x in all_lines],source="OCR" if all_lines else "PARSER")
        quality=q.to_dict()
        page_gate_failed=any(x.get("gate_result")=="FAIL" for x in qualities)
        if page_gate_failed or scan_table_pages:
            quality["gate_result"]="FAIL"
        if page_gate_failed and not quality.get("reason"):
            quality["reason"]="PAGE_QUALITY_GATE_FAILED"
        if scan_table_pages:
            quality["reason"]="SCAN_TABLE_REQUIRES_REVIEW"
        document_confidence=confidence_from_quality(q)
        if str(quality.get("gate_result","")).upper()=="FAIL":
            document_confidence=min(document_confidence, settings.document_failed_gate_confidence_cap)
        native_table_results=extract_pdf_table_results(content)
        # Hybrid PDFs may alternate digital and scanned table pages. Preserve document
        # order across both engines so a header on page N can safely govern a continuation
        # on page N+1 regardless of which engine produced each table.
        combined_table_results=[*native_table_results,*scan_tables]
        combined_table_results.sort(key=lambda x: (int(x.get("page") or 10**9), 0 if str(x.get("source","")).startswith("pdf") or x.get("source")=="camelot-lattice" else 1))
        tables=[x["cells"] for x in combined_table_results]
        if len(tables) > settings.document_max_tables:
            raise DocumentLimitError("TABLE_LIMIT_EXCEEDED", tables=len(tables), limit=settings.document_max_tables)
        table_sources=[{k:v for k,v in x.items() if k != "cells"} for x in combined_table_results]
        method=ParseMethod.PDF_HYBRID if kind==InputKind.PDF_HYBRID else ParseMethod.OCR
        return ParseResult(text,document_confidence,method.value,kind.value,quality,{"routing":decision.to_dict(),"page_route_map":[vars(x) if hasattr(x,'__dict__') else {"page":x.page,"route":x.route,"chars":x.chars,"image_coverage":x.image_coverage,"embedded_fonts":x.embedded_fonts,"char_entropy":x.char_entropy,"replacement_ratio":x.replacement_ratio,"rotation":x.rotation,"reasons":x.reasons} for x in decision.page_route_map],"scan_table_pages":scan_table_pages,"scan_structure":scan_structures,"table_sources":table_sources,"ocr_page_evidence":ocr_page_evidence,"ocr_page_quality":ocr_page_quality},all_lines,tables)
    if kind == InputKind.IMAGE:
        lines,quality,conf,ocr_evidence=_ocr_image(content)
        text="\n".join(x.text for x in lines)
        return ParseResult(text,conf,ParseMethod.OCR.value,kind.value,quality,{"routing":decision.to_dict(),"ocr":ocr_evidence},lines,[])
    return ParseResult("",0.0,ParseMethod.UNKNOWN.value,kind.value,{"gate_result":"FAIL","metrics":{}},{"routing":decision.to_dict()})


def parse_bytes(file_name: str, content: bytes) -> tuple[str,float,str]:
    """Compatibility facade used by older callers/tests without forcing OCR model loading."""
    decision=route_input(file_name,content)
    if decision.kind in {InputKind.IMAGE, InputKind.PDF_SCAN}:
        return "",0.0,"OCR_REQUIRED"
    result=parse_document(file_name,content)
    return result.text,result.confidence,result.method


def ocr_image(content: bytes) -> tuple[str,float]:
    """Compatibility facade. OCR errors are not swallowed; worker retry/DLQ handles failures."""
    lines,_,conf,_=_ocr_image(content)
    return "\n".join(x.text for x in lines),conf
