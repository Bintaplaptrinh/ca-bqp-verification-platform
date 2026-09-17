from __future__ import annotations

import json
import tempfile
from functools import lru_cache
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import numpy as np


def _clean_table(table) -> list[list[str]]:
    return [["" if cell is None else str(cell).strip() for cell in row] for row in table]


def extract_pdf_table_results(content: bytes) -> list[dict]:
    """Extract native PDF tables in *document page order* with page/engine metadata.

    pdfplumber is the deterministic baseline. Camelot lattice is attempted only for
    pages with a strong ruled-table signal, but its results are re-associated with the
    original page before returning. This matters for multi-page rosters: returning all
    ordinary pages before ruled pages can silently break header-continuation handling.
    """
    out: list[dict] = []
    tmp_path: str | None = None
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(content)) as pdf:
            ruled_pages: list[int] = []
            for page_no, page in enumerate(pdf.pages, start=1):
                horizontal = sum(abs(float(line.get("y1", 0)) - float(line.get("y0", 0))) < 2 for line in page.lines)
                vertical = sum(abs(float(line.get("x1", 0)) - float(line.get("x0", 0))) < 2 for line in page.lines)
                if horizontal > 4 and vertical > 4:
                    ruled_pages.append(page_no)

            camelot_by_page: dict[int, list[list[list[str]]]] = {}
            if ruled_pages:
                try:
                    import camelot

                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    tables = camelot.read_pdf(tmp_path, pages=",".join(map(str, ruled_pages)), flavor="lattice")
                    for table in tables:
                        try:
                            table_page = int(str(getattr(table, "page", "")).strip())
                        except (TypeError, ValueError):
                            continue
                        if table_page in ruled_pages:
                            camelot_by_page.setdefault(table_page, []).append(_clean_table(table.df.values.tolist()))
                except Exception:
                    camelot_by_page = {}

            for page_no, page in enumerate(pdf.pages, start=1):
                camelot_tables = camelot_by_page.get(page_no) or []
                if camelot_tables:
                    for table in camelot_tables:
                        out.append({"cells": table, "page": page_no, "source": "camelot-lattice"})
                    continue
                # Fallback is per page, so a Camelot failure cannot reorder the document.
                for table in page.extract_tables() or []:
                    out.append({"cells": _clean_table(table), "page": page_no, "source": "pdfplumber"})
    except Exception:
        return out
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
    return out


def extract_pdf_tables(content: bytes) -> list[list[list[str]]]:
    """Compatibility facade returning only cell matrices."""
    return [item["cells"] for item in extract_pdf_table_results(content)]


def extract_docx_tables(doc) -> list[list[list[str]]]:
    return [[[cell.text.strip() for cell in row.cells] for row in table.rows] for table in doc.tables]


class _HTMLGridParser(HTMLParser):
    """Small dependency-free parser for PP-Structure's ``pred_html`` tables.

    It deliberately preserves the grid instead of flattening text. ``rowspan`` and
    ``colspan`` are expanded so downstream code can reason in row/column space.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, int, int]]]] = []
        self._table_depth = 0
        self._rows: list[list[tuple[str, int, int]]] | None = None
        self._row: list[tuple[str, int, int]] | None = None
        self._cell_text: list[str] | None = None
        self._rowspan = 1
        self._colspan = 1

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.casefold()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            attr = {str(k).casefold(): str(v) for k, v in attrs if k}
            try:
                self._rowspan = max(1, int(attr.get("rowspan", "1")))
            except ValueError:
                self._rowspan = 1
            try:
                self._colspan = max(1, int(attr.get("colspan", "1")))
            except ValueError:
                self._colspan = 1
            self._cell_text = []
        elif tag == "br" and self._cell_text is not None:
            self._cell_text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._table_depth == 1 and self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell_text is not None:
            text = " ".join("".join(self._cell_text).split())
            if self._row is not None:
                self._row.append((text, self._rowspan, self._colspan))
            self._cell_text = None
            self._rowspan = 1
            self._colspan = 1
        elif self._table_depth == 1 and tag == "tr":
            if self._rows is not None and self._row is not None:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._rows is not None:
                self.tables.append(self._rows)
                self._rows = None
            self._table_depth -= 1


def _fill_active_until_free(
    row: list[str], active: dict[int, tuple[int, str]], col: int
) -> int:
    """Write any rowspan carry-over occupying `col` onwards; return the next free column.

    Taken as an argument rather than closed over: defining this inside the row
    loop captured the loop's `row`, which reads as a late-binding hazard even
    though it was called immediately.
    """
    while col in active:
        remaining, text = active[col]
        while len(row) <= col:
            row.append("")
        row[col] = text
        if remaining <= 1:
            del active[col]
        else:
            active[col] = (remaining - 1, text)
        col += 1
    return col


def _expand_html_grid(rows: list[list[tuple[str, int, int]]]) -> list[list[str]]:
    grid: list[list[str]] = []
    # column -> (remaining rows after current row, text)
    active: dict[int, tuple[int, str]] = {}
    for source_row in rows:
        row: list[str] = []
        col = 0

        for text, rowspan, colspan in source_row:
            col = _fill_active_until_free(row, active, col)
            for offset in range(colspan):
                target = col + offset
                while len(row) <= target:
                    row.append("")
                # For merged cells, retain the content in the leading cell only. The
                # blank continuation cells preserve geometry without fabricating values.
                row[target] = text if offset == 0 else ""
                if rowspan > 1:
                    active[target] = (rowspan - 1, text if offset == 0 else "")
            col += colspan
        _fill_active_until_free(row, active, col)
        grid.append(row)

    while active:
        row: list[str] = []
        col = 0
        max_col = max(active)
        while col <= max_col:
            if col in active:
                remaining, text = active[col]
                while len(row) <= col:
                    row.append("")
                row[col] = text
                if remaining <= 1:
                    del active[col]
                else:
                    active[col] = (remaining - 1, text)
            else:
                while len(row) <= col:
                    row.append("")
            col += 1
        grid.append(row)
    return _clean_table(grid)


def html_tables_to_matrices(html: str) -> list[list[list[str]]]:
    if not html or "<table" not in html.casefold():
        return []
    parser = _HTMLGridParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return []
    return [_expand_html_grid(rows) for rows in parser.tables if rows]


def _score_p10(scores) -> float | None:
    vals: list[float] = []
    for value in scores or []:
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        if 0.0 <= score <= 1.0:
            vals.append(score)
        elif 1.0 < score <= 100.0:
            vals.append(score / 100.0)
    if not vals:
        return None
    vals.sort()
    idx = int((len(vals) - 1) * 0.10)
    return round(vals[idx], 4)


def _iter_table_results(node):
    if isinstance(node, dict):
        results = node.get("table_res_list")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    yield item
        for key, value in node.items():
            if key != "table_res_list":
                yield from _iter_table_results(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _iter_table_results(item)


def tables_from_scan_structure(structure: list[dict]) -> list[dict]:
    """Convert PP-StructureV3 table output to grid matrices plus auditable confidence.

    PP-StructureV3 exposes ``pred_html`` for table geometry and ``rec_scores`` for
    recognized table text. We use the HTML only to reconstruct cells; recognized text
    is never 'corrected' from domain knowledge. Confidence is conservative p10 across
    table OCR scores and is left ``None`` when the engine did not provide scores.
    """
    out: list[dict] = []
    for result in _iter_table_results(structure):
        html = str(result.get("pred_html") or result.get("html") or "")
        matrices = html_tables_to_matrices(html)
        ocr = result.get("table_ocr_pred") if isinstance(result.get("table_ocr_pred"), dict) else {}
        confidence = _score_p10((ocr or {}).get("rec_scores"))
        for matrix in matrices:
            if matrix:
                out.append(
                    {
                        "cells": matrix,
                        "confidence": confidence,
                        "engine": "PP-StructureV3",
                        "table_id": result.get("table_id"),
                    }
                )
    return out


def looks_like_table_image(image) -> bool:
    """Cheap line heuristic; PP-Structure is only invoked when a table is plausible."""
    try:
        import cv2

        arr = np.asarray(image.convert("L"))
        binary = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, arr.shape[1] // 20), 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, arr.shape[0] // 20)))
        h = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        v = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        hc, _ = cv2.findContours(h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        vc, _ = cv2.findContours(v, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return len(hc) > 4 and len(vc) > 4
    except Exception:
        return False


def looks_like_table_ocr_lines(lines: list) -> bool:
    """Detect repeated row/column alignment for borderless scanned tables.

    This is only a *hint* to run PP-StructureV3. It never proves that a table exists
    and therefore cannot by itself create bulk records.
    """
    boxes=[]
    for item in lines or []:
        try:
            bbox=getattr(item,"bbox",None) or item.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x0,y0,x1,y1=(float(v) for v in bbox)
            if x1 <= x0 or y1 <= y0:
                continue
            boxes.append((x0,y0,x1,y1,max(1.0,y1-y0)))
        except (AttributeError,TypeError,ValueError):
            continue
    if len(boxes) < 6:
        return False
    heights=sorted(x[4] for x in boxes)
    median_h=heights[len(heights)//2]
    y_tol=max(6.0,median_h*0.75)
    rows=[]
    for box in sorted(boxes,key=lambda x:((x[1]+x[3])/2,x[0])):
        cy=(box[1]+box[3])/2
        target=None
        for row in rows:
            if abs(cy-row[0]) <= y_tol:
                target=row; break
        if target is None:
            target=[cy,[]]; rows.append(target)
        target[1].append(box)
        target[0]=sum((b[1]+b[3])/2 for b in target[1])/len(target[1])
    multi=[r[1] for r in rows if len(r[1]) >= 2]
    if len(multi) < 3:
        return False
    x_tol=max(12.0,median_h*2.0)
    clusters=[]
    for row in multi:
        for box in row:
            x=box[0]
            cluster=next((c for c in clusters if abs(x-c[0]) <= x_tol),None)
            if cluster is None:
                clusters.append([x,1])
            else:
                cluster[0]=(cluster[0]*cluster[1]+x)/(cluster[1]+1); cluster[1]+=1
    stable=sum(1 for _,count in clusters if count >= 3)
    return stable >= 2


@lru_cache(maxsize=1)
def _pp_structure_pipeline():
    from paddleocr import PPStructureV3

    # One model instance per worker process. Re-creating the whole pipeline for every
    # PDF page is extremely expensive and can dominate CPU/GPU latency.
    return PPStructureV3(use_doc_orientation_classify=False, use_doc_unwarping=False)


def extract_scan_structure(image, *, force: bool=False) -> list[dict]:
    """Run PP-StructureV3 only when a table-like page is plausible.

    The raw result is retained as evidence. Downstream bulk ingestion may consume only
    an explicit table grid reconstructed from ``pred_html`` and still applies confidence
    and human-review gates; arbitrary OCR text is never split into rows heuristically.
    """
    if not force and not looks_like_table_image(image):
        return []
    try:
        pipeline = _pp_structure_pipeline()
        results = pipeline.predict(input=np.asarray(image.convert("RGB")))
        out: list[dict] = []
        for result in results:
            payload = getattr(result, "json", None)
            if callable(payload):
                payload = payload()
            if payload is None and isinstance(result, dict):
                payload = result
            # Convert numpy-ish leaves through JSON's default=str to preserve audit evidence safely.
            out.append(json.loads(json.dumps(payload or {}, ensure_ascii=False, default=str)))
        return out
    except Exception as exc:
        return [{"pp_structure_error": type(exc).__name__}]


def _mentions_table(node) -> bool:
    """Look for a table in the structure's keys, not anywhere in its serialized text.

    Matching the whole JSON blob also matched diagnostics such as
    {'pp_structure_error': 'TableRecognitionError'}, so a failed structure call was
    reported as "this scan contains a table" and sent the case to review for the wrong
    reason. Recognised text is likewise excluded: a page that merely says "bảng phân
    công" is not a table.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key).casefold()
            if key_text.endswith("_error") or key_text in {"error", "exception"}:
                continue
            if key_text == "table_res_list":
                if isinstance(value,list) and any(
                    isinstance(x,dict) and (
                        bool(x.get("pred_html"))
                        or bool(x.get("html"))
                        or bool(x.get("cell_box_list"))
                        or bool(x.get("table_ocr_pred"))
                    )
                    for x in value
                ):
                    return True
                continue
            if key_text == "block_label" and str(value).casefold() in {"table","table_body"}:
                return True
            if key_text in {"table_cells", "table_cell_list"} and value not in (None,"",[],{}):
                return True
            # PP-StructureV3 documents table results through table_res_list (and layout
            # blocks through block_label). Do not infer a table merely because a config
            # or diagnostic key happens to contain the word "table".
            if _mentions_table(value):
                return True
        return False
    if isinstance(node, (list, tuple)):
        return any(_mentions_table(item) for item in node)
    return False


def scan_structure_contains_table(structure: list[dict]) -> bool:
    return bool(structure) and _mentions_table(structure)
