from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from functools import lru_cache
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path

import yaml
from openpyxl import load_workbook
from rapidfuzz.fuzz import ratio
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cabqp.modules.audit.service import audit
from cabqp.modules.cases.service import process_case
from cabqp.modules.document_intelligence.limits import DocumentLimitError
from cabqp.shared.metrics import BULK_INGEST
from cabqp.shared.models import BulkIngestJob, BulkIngestRow, Case, HeaderAliasCandidate, RowError
from cabqp.shared.normalization import ascii_key
from cabqp.shared.schemas import _validate_business_date
from cabqp.shared.settings import get_settings

MAPPING_VERSION = "header-map-2026.09-v1"
ALLOWED_MAPPING_FIELDS = {
    "subject_name",
    "subject_code",
    "position",
    "unit_name",
    "unit_code",
    "subject_group",
    "employment_status",
    "birth_year",
    "as_of_date",
}

DEFAULT_FIELD_ALIASES = {
    "subject_name": ["họ và tên","họ tên","ho ten","full_name"],
    "subject_code": ["cccd","cmnd","personal_code"],
    "position": ["chức vụ","position"],
    "unit_name": ["đơn vị công tác","unit_name","canonical_unit_name"],
}

@lru_cache(maxsize=1)
def _mapping_config() -> tuple[str,dict[str,list[str]]]:
    path=Path(get_settings().header_alias_path)
    if not path.is_absolute():
        cwd_candidate=Path.cwd()/path
        package_candidate=Path(__file__).resolve().parents[4]/path
        path=cwd_candidate if cwd_candidate.exists() else package_candidate
    if path.exists():
        data=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return str(data.get("version") or MAPPING_VERSION), dict(data.get("fields") or DEFAULT_FIELD_ALIASES)
    return MAPPING_VERSION,DEFAULT_FIELD_ALIASES


def _aliases() -> dict[str,list[str]]:
    return _mapping_config()[1]


UNIT_RE = re.compile(
    r"\b(?:Công an|Cục|Bộ Tư lệnh|Bộ Chỉ huy|Ban Chỉ huy|Học viện|Trường|Bệnh viện|Viện|Trung tâm|Quân khu|Quân đoàn|Sư đoàn|Lữ đoàn|Trung đoàn|Tiểu đoàn|Tổng cục|Binh chủng|Quân chủng)\b",
    re.I,
)


def _header_index(matrix: list[list]) -> int:
    """Choose the most plausible header while preserving manual-mapping compatibility.

    Prefer rows that contain known header aliases, but fall back to the old generic
    string-row heuristic when a customer uses completely custom column names. This
    avoids selecting merged/group headings such as ``Thông tin cá nhân | Công tác``
    when the real field header is on the next row.
    """
    fallback=None
    best_idx=None
    best_score=-1.0
    cfg=get_settings()
    for i,row in enumerate(matrix[:20]):
        non=[v for v in row if v not in (None,"")]
        if not non:
            continue
        string_ratio=sum(isinstance(v,str) for v in non)/len(non)
        if fallback is None and len(non)>=2 and string_ratio>=0.7:
            fallback=i
        alias_scores=[_cell_alias_score(v) for v in non]
        strong=sum(score>=cfg.bulk_header_alias_min for score in alias_scores)
        if strong:
            score=(2.0*strong)+sum(alias_scores)+string_ratio
            if score>best_score:
                best_score=score; best_idx=i
    if best_idx is not None:
        return best_idx
    if fallback is not None:
        return fallback
    return next((i for i,row in enumerate(matrix[:20]) if any(v not in (None,"") for v in row)),0)


def _sheet_payloads(sheet_name: str, matrix: list[list], *, start_index: int, preserve_source_rows: bool) -> tuple[list[str], list[dict], int]:
    # Keep blank rows in the matrix so audit metadata points to the *actual* source row.
    # Filtering them first made Excel row 17 appear as row 12 whenever blank separators
    # existed above the data.
    if not any(any(v not in (None,"") for v in r) for r in matrix):
        return [],[],start_index
    header_idx=_header_index(matrix)
    header_row=list(matrix[header_idx])
    while header_row and header_row[-1] in (None,""):
        header_row.pop()
    if not header_row:
        return [],[],start_index
    headers=[]
    for i,v in enumerate(header_row):
        name=str(v).strip() if v not in (None,"") else f"Unnamed: {i+1}"
        headers.append(name)
    rows=[]
    cursor=start_index
    for source_zero_idx,r in enumerate(matrix[header_idx+1:], start=header_idx+1):
        source_row=source_zero_idx+1
        payload={headers[i]: (r[i] if i<len(r) else None) for i in range(len(headers))}
        if not any(v not in (None,"") for v in payload.values()):
            continue
        if preserve_source_rows:
            row_index=source_row
            cursor=max(cursor,row_index)
        else:
            cursor+=1
            row_index=cursor
        payload["_source_sheet"]=sheet_name
        payload["_source_row"]=source_row
        payload["_source_row_index"]=row_index
        rows.append(payload)
    return headers,rows,cursor



def _cell_alias_score(value) -> float:
    key=ascii_key(str(value or "").strip())
    if not key:
        return 0.0
    return max(
        (ratio(key,ascii_key(alias))/100 for aliases in _aliases().values() for alias in aliases),
        default=0.0,
    )


def _row_dicts(headers: list[str], matrix: list[list]) -> list[dict]:
    return [
        {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        for row in matrix
        if any(v not in (None, "") for v in row)
    ]


def _semantic_header_candidate(matrix: list[list]) -> tuple[int, list[str], dict, dict] | None:
    """Find a horizontal record-table header, not merely the first string row.

    A personnel list is only accepted when a header maps to ``subject_name`` and the
    rows below behave like records. This rejects vertical key/value forms such as
    ``[Họ tên, Nguyễn A] / [CCCD, ...]`` even though they are technically rectangular.
    """
    best=None
    for idx,row in enumerate(matrix[:20]):
        non=[v for v in row if v not in (None, "")]
        if not non:
            continue
        headers=[str(v).strip() if v not in (None, "") else f"Unnamed: {i+1}" for i,v in enumerate(row)]
        preview_matrix=[r for r in matrix[idx+1:idx+21] if any(v not in (None, "") for v in r)]
        if len(preview_matrix) < 1:
            continue
        preview=_row_dicts(headers,preview_matrix)
        mapping,details=infer_mapping(headers,preview)
        name_headers=[h for h,f in mapping.items() if f=="subject_name"]
        if not name_headers:
            continue
        name_header=name_headers[0]
        name_header_score=float(details.get(name_header,{}).get("header_score",0.0))
        cfg=get_settings()
        if name_header_score < cfg.bulk_header_alias_min:
            continue
        mapped_headers=[h for h,f in mapping.items() if f and float(details.get(h,{}).get("header_score",0.0)) >= cfg.bulk_header_alias_min]
        # With only one data row, require at least two confidently mapped columns.
        # This keeps a one-person roster valid while rejecting ambiguous two-cell forms.
        if len(preview_matrix) == 1 and len(mapped_headers) < 2:
            continue
        # Vertical forms expose field labels down their first column. Treat that as a
        # strong anti-signal instead of accidentally ingesting labels as people.
        data_cells=[v for r in preview_matrix for v in r if v not in (None, "")]
        label_like=sum(_cell_alias_score(v)>=0.80 for v in data_cells)/max(1,len(data_cells))
        name_values=[str(r.get(name_header) or "") for r in preview]
        name_value_score=_value_score("subject_name",name_values)
        if len(mapped_headers) == 1 and (label_like >= cfg.bulk_table_label_antisignal_max or name_value_score < cfg.bulk_record_name_value_min):
            continue
        score=(2.0*name_header_score)+sum(float(details[h].get("header_score",0.0)) for h in mapped_headers)+name_value_score-label_like
        candidate=(score,idx,headers,mapping,details)
        if best is None or candidate[0] > best[0]:
            best=candidate
    if best is None:
        return None
    _,idx,headers,mapping,details=best
    return idx,headers,mapping,details


def _continuation_matches(headers: list[str], matrix: list[list]) -> bool:
    if not headers or not matrix:
        return False
    width=max((len(r) for r in matrix if any(v not in (None, "") for v in r)),default=0)
    if abs(width-len(headers)) > 1:
        return False
    preview=_row_dicts(headers,[r for r in matrix[:20] if any(v not in (None, "") for v in r)])
    mapping,details=infer_mapping(headers,preview)
    name_headers=[h for h,f in mapping.items() if f=="subject_name"]
    if not name_headers:
        return False
    name_header=name_headers[0]
    cfg=get_settings()
    if float(details.get(name_header,{}).get("header_score",0.0)) < cfg.bulk_header_alias_min:
        return False
    score=_value_score("subject_name",[str(r.get(name_header) or "") for r in preview])
    label_like=sum(
        _cell_alias_score(v)>=0.80
        for row in matrix[:20] for v in row if v not in (None, "")
    )/max(1,sum(1 for row in matrix[:20] for v in row if v not in (None, "")))
    return score >= cfg.bulk_record_name_value_min and label_like < cfg.bulk_table_label_antisignal_max


def _record_table_payloads(
    source_name: str,
    matrix: list[list],
    *,
    start_index: int,
    table_index: int,
    source_meta: dict | None=None,
    continuation_headers: list[str] | None=None,
) -> tuple[list[str],list[dict],int,list[str] | None]:
    clean=[list(r) for r in matrix if isinstance(r,(list,tuple)) and any(v not in (None, "") for v in r)]
    if not clean:
        return [],[],start_index,continuation_headers
    candidate=_semantic_header_candidate(clean)
    if candidate is not None:
        header_idx,headers,_,_=candidate
        data=clean[header_idx+1:]
        source_row_start=header_idx+2
        active_headers=headers
    elif continuation_headers and _continuation_matches(continuation_headers,clean):
        active_headers=continuation_headers
        data=clean
        source_row_start=1
    else:
        return [],[],start_index,continuation_headers

    rows=[]; cursor=start_index
    normalized_headers=[ascii_key(h) for h in active_headers]
    for offset,row in enumerate(data):
        # Repeated headers on later PDF pages are common; do not create a fake person.
        row_keys=[ascii_key(str(row[i] or "")) if i < len(row) else "" for i in range(len(active_headers))]
        header_matches=sum(1 for i,k in enumerate(row_keys) if k and k==normalized_headers[i])
        nonempty_header_count=len([x for x in normalized_headers if x])
        # Skip repeated headers only on a strict majority match. Using floor(n/2) made
        # a 3-column table drop a legitimate row when just one value happened to equal
        # its column header.
        if header_matches >= max(1,(nonempty_header_count//2)+1):
            continue
        payload={active_headers[i]: (row[i] if i<len(row) else None) for i in range(len(active_headers))}
        if not any(v not in (None, "") for v in payload.values()):
            continue
        cursor+=1
        payload["_source_sheet"]=source_name
        payload["_source_table"]=table_index+1
        payload["_source_row"]=source_row_start+offset
        payload["_source_row_index"]=cursor
        meta=source_meta or {}
        if meta.get("page") is not None:
            payload["_source_page"]=meta.get("page")
        if meta.get("source"):
            payload["_source_table_engine"]=meta.get("source")
        if meta.get("confidence") is not None:
            payload["_source_table_confidence"]=meta.get("confidence")
        rows.append(payload)
    return active_headers,rows,cursor,active_headers


def tables_have_record_list(tables: list) -> bool:
    continuation=None
    for idx,table in enumerate(tables or []):
        headers,rows,_,continuation=_record_table_payloads(
            f"table-{idx+1}", table, start_index=0, table_index=idx, continuation_headers=continuation
        )
        if headers and len(rows)>=1:
            return True
    return False


def extract_unruled_text_table(text: str) -> list[list]:
    """Reconstruct a simple column-major personnel list from a digital PDF.

    Some official-looking exports contain aligned text columns but no PDF table
    borders. PyMuPDF then returns the column headers followed by each row's cell
    values as separate lines while ``find_tables`` returns nothing. Keep this
    fallback deliberately strict: require a row-number column plus at least two
    recognised business headers, including the person's name.
    """
    lines=[line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 8:
        return []
    cfg=get_settings()
    for start,line in enumerate(lines[:30]):
        if ascii_key(line) not in {"stt", "so thu tu", "#"}:
            continue
        headers=[line]
        mapped=[]
        cursor=start+1
        while cursor < min(len(lines), start+12):
            value=lines[cursor]
            if re.fullmatch(r"\d+", value):
                break
            field_scores={
                field:max((ratio(ascii_key(value),ascii_key(alias))/100 for alias in aliases),default=0.0)
                for field,aliases in _aliases().items()
            }
            field,score=max(field_scores.items(),key=lambda item:item[1])
            if score < cfg.bulk_header_alias_min or field in mapped:
                break
            headers.append(value); mapped.append(field); cursor+=1
        if "subject_name" not in mapped or len(mapped) < 2 or cursor >= len(lines):
            continue
        width=len(headers)
        values=lines[cursor:]
        rows=[]
        for offset in range(0,len(values),width):
            row=values[offset:offset+width]
            if len(row) != width or not re.fullmatch(r"\d+",row[0]):
                break
            rows.append(row)
        if len(rows) >= 2:
            return [headers,*rows]
    return []

def _read_rows(file_name: str, content: bytes) -> tuple[list[str], list[dict], int]:
    ext=Path(file_name).suffix.lower()
    settings=get_settings()
    headers: list[str]=[]
    rows: list[dict]=[]
    first_row=1
    total_source_rows=0
    cursor=0

    def add_headers(local: list[str]):
        for h in local:
            if h not in headers:
                headers.append(h)

    if ext in {".xlsx",".xlsm"}:
        wb=load_workbook(BytesIO(content),read_only=True,data_only=True)
        if len(wb.worksheets) > settings.document_max_worksheets:
            raise DocumentLimitError("WORKSHEET_LIMIT_EXCEEDED", worksheets=len(wb.worksheets), limit=settings.document_max_worksheets)
        sheet_matrices=[]
        for ws in wb.worksheets:
            matrix=[]
            for r in ws.iter_rows(values_only=True):
                total_source_rows+=1
                if total_source_rows > settings.document_max_spreadsheet_rows:
                    raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=total_source_rows, limit=settings.document_max_spreadsheet_rows)
                matrix.append(list(r))
            sheet_matrices.append((ws.title,matrix,_semantic_header_candidate(matrix) is not None))
        # If at least one sheet is confidently a personnel table, ignore cover/instruction
        # sheets. If none are recognizable, keep every sheet so operator mapping still
        # works for genuinely custom headers.
        selected=[x for x in sheet_matrices if x[2]] or sheet_matrices
        first_data_seen=False
        preserve_rows=len(selected)==1
        for sheet_name,matrix,_ in selected:
            local_headers,local_rows,cursor=_sheet_payloads(sheet_name,matrix,start_index=cursor,preserve_source_rows=preserve_rows)
            add_headers(local_headers)
            if local_rows and not first_data_seen:
                first_row=int(local_rows[0]["_source_row_index"])
                first_data_seen=True
            rows.extend(local_rows)
    elif ext == ".xls":
        import xlrd
        book=xlrd.open_workbook(file_contents=content)
        if book.nsheets > settings.document_max_worksheets:
            raise DocumentLimitError("WORKSHEET_LIMIT_EXCEEDED", worksheets=book.nsheets, limit=settings.document_max_worksheets)
        sheet_matrices=[]
        for sheet_idx in range(book.nsheets):
            sh=book.sheet_by_index(sheet_idx)
            total_source_rows += sh.nrows
            if total_source_rows > settings.document_max_spreadsheet_rows:
                raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=total_source_rows, limit=settings.document_max_spreadsheet_rows)
            matrix=[sh.row_values(i) for i in range(sh.nrows)]
            sheet_matrices.append((sh.name,matrix,_semantic_header_candidate(matrix) is not None))
        selected=[x for x in sheet_matrices if x[2]] or sheet_matrices
        first_data_seen=False
        preserve_rows=len(selected)==1
        for sheet_name,matrix,_ in selected:
            local_headers,local_rows,cursor=_sheet_payloads(sheet_name,matrix,start_index=cursor,preserve_source_rows=preserve_rows)
            add_headers(local_headers)
            if local_rows and not first_data_seen:
                first_row=int(local_rows[0]["_source_row_index"])
                first_data_seen=True
            rows.extend(local_rows)
    elif ext == ".csv":
        text=content.decode("utf-8-sig",errors="replace")
        try: dialect=csv.Sniffer().sniff(text[:4096],delimiters=",;\t|")
        except csv.Error: dialect=csv.excel
        matrix=list(csv.reader(StringIO(text),dialect))
        if len(matrix) > settings.document_max_spreadsheet_rows:
            raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=len(matrix), limit=settings.document_max_spreadsheet_rows)
        local_headers,local_rows,_=_sheet_payloads("CSV",matrix,start_index=0,preserve_source_rows=True)
        add_headers(local_headers); rows.extend(local_rows)
        if local_rows: first_row=int(local_rows[0]["_source_row_index"])
    elif ext in {".pdf", ".docx"}:
        # PDFs/DOCX stay structured. Native tables and PP-StructureV3 scan tables are
        # converted into records only when a semantic personnel-list header is found.
        from cabqp.modules.document_intelligence.parsers import parse_document

        parsed=parse_document(file_name,content)
        sources=list((parsed.evidence or {}).get("table_sources") or [])
        continuation_headers=None
        continuation_page=None
        first_data_seen=False
        total_table_rows=0
        for table_idx,table in enumerate(parsed.tables or []):
            total_table_rows += len(table) if isinstance(table,list) else 0
            if total_table_rows > settings.document_max_spreadsheet_rows:
                raise DocumentLimitError("SPREADSHEET_ROW_LIMIT_EXCEEDED", rows=total_table_rows, limit=settings.document_max_spreadsheet_rows)
            meta=sources[table_idx] if table_idx < len(sources) and isinstance(sources[table_idx],dict) else {}
            source_label=f"{ext.lstrip('.').upper()} table {table_idx+1}"
            current_page=meta.get("page")
            allowed_continuation=None
            try:
                if continuation_headers and continuation_page is not None and current_page is not None and int(current_page)==int(continuation_page)+1:
                    allowed_continuation=continuation_headers
            except (TypeError,ValueError):
                allowed_continuation=None
            local_headers,local_rows,cursor,new_continuation=_record_table_payloads(
                source_label,table,start_index=cursor,table_index=table_idx,source_meta=meta,
                continuation_headers=allowed_continuation,
            )
            if not local_rows:
                # Do not carry a schema across unrelated pages/tables after a failed match.
                if current_page is not None:
                    continuation_headers=None; continuation_page=None
                continue
            continuation_headers=new_continuation
            continuation_page=current_page
            add_headers(local_headers)
            if not first_data_seen:
                first_row=int(local_rows[0]["_source_row_index"]); first_data_seen=True
            rows.extend(local_rows)
        if not rows and ext == ".pdf":
            # Borderless digital lists are text, not native PDF tables. Rebuild
            # their strict header/row layout before declaring the upload invalid.
            text_table=extract_unruled_text_table(parsed.text)
            if text_table:
                local_headers,local_rows,cursor,_=_record_table_payloads(
                    "PDF text layout",text_table,start_index=cursor,table_index=0,
                    source_meta={"source":"pdf-text-layout","page":1},
                )
                add_headers(local_headers); rows.extend(local_rows)
                if local_rows:
                    first_row=int(local_rows[0]["_source_row_index"])
        if not rows:
            reason="No structured personnel-list table could be reconstructed from this document"
            if (parsed.evidence or {}).get("scan_table_pages"):
                reason += "; scanned table requires a successful PP-StructureV3 table result"
            raise ValueError(reason)
    else:
        raise ValueError("Bulk ingestion supports XLS/XLSX/CSV/PDF/DOCX")
    return headers,rows,first_row


def _value_score(field: str, values: list[str]) -> float:
    vals=[v.strip() for v in values if v.strip()][:50]
    if not vals: return 0.0
    if field == "subject_code": return sum(bool(re.fullmatch(r"\d{9}|\d{12}",v)) for v in vals)/len(vals)
    if field == "birth_year": return sum(bool(re.fullmatch(r"(?:19|20)\d{2}",v)) for v in vals)/len(vals)
    if field == "as_of_date": return sum(bool(re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}",v)) for v in vals)/len(vals)
    if field == "unit_name": return sum(bool(UNIT_RE.search(v)) for v in vals)/len(vals)
    if field == "subject_name":
        # A person's name is separated by real whitespace and mixes case per word
        # ("Nguyễn Minh An"). An all-caps token like "SYNTHETIC_DEMO" or a status
        # code only *looks* like 2+ words once underscores are treated as letters
        # by the word regex below, so require whitespace-separated words and
        # reject a value that is entirely uppercase (no lowercase letters at all).
        def looks_like_person_name(v: str) -> bool:
            words = v.split()
            if not (2 <= len(words) <= 7):
                return False
            if any(ch.isdigit() for ch in v):
                return False
            if not any(ch.islower() for ch in v):
                return False
            return all(re.fullmatch(r"[A-Za-zÀ-ỹĐđ.'-]+", w) for w in words)

        return sum(looks_like_person_name(v) for v in vals)/len(vals)
    return 0.0


def infer_mapping(headers: list[str], rows: list[dict]) -> tuple[dict,dict]:
    mapping={}; details={}; used_by: dict[str,list[str]]={}
    for h in headers:
        hk=ascii_key(h)
        vals=[str(r.get(h) or "") for r in rows]
        candidates=[]
        for field,aliases in _aliases().items():
            alias_score=max([ratio(hk,ascii_key(a))/100 for a in aliases]+[0.0])
            value_score=_value_score(field,vals)
            score=max(alias_score,0.75*alias_score+0.25*value_score,value_score*0.92)
            candidates.append((score,field,alias_score,value_score))
        candidates.sort(reverse=True)
        best=candidates[0]
        field=best[1]
        conflicting_headers=used_by.get(field,[])
        conflicts=any(
            r.get(h) not in (None,"") and any(r.get(prev) not in (None,"") for prev in conflicting_headers)
            for r in rows
        )
        confidence=best[0] if not conflicts else min(best[0],0.60)
        # Two populated source columns must never be auto-mapped to the same
        # canonical field.  The old boundary condition kept the conflicting
        # column at exactly 0.60, which is also the acceptance threshold.  A
        # metadata column such as ``source_kind`` could therefore become a
        # second ``subject_name`` and leave an otherwise valid CSV stuck in
        # AWAITING_MAPPING.  Keep mutually-exclusive aliases supported, but
        # abstain whenever both columns actually contain data.
        mapping[h]=field if confidence>=0.60 and not conflicts else None
        if mapping[h]: used_by.setdefault(field,[]).append(h)
        details[h]={
            "field":mapping[h],"confidence":round(confidence,4),
            "header_score":round(best[2],4),"value_score":round(best[3],4),
            "mutually_exclusive_alias":bool(conflicting_headers and not conflicts),
        }
    return mapping,details



def validate_mapping(headers: list[str], mapping: dict[str, str | None]) -> dict[str, str | None]:
    unknown_headers = sorted(set(mapping) - set(headers))
    if unknown_headers:
        raise ValueError(f"Unknown source columns in mapping: {', '.join(unknown_headers)}")
    bad_fields = sorted({str(v) for v in mapping.values() if v and v not in ALLOWED_MAPPING_FIELDS})
    if bad_fields:
        raise ValueError(f"Unsupported target fields: {', '.join(bad_fields)}")
    targets = [v for v in mapping.values() if v]
    duplicates = sorted({x for x in targets if targets.count(x) > 1})
    if duplicates:
        raise ValueError(f"A target field can only be mapped once: {', '.join(duplicates)}")
    return {h: mapping.get(h) for h in headers}

def _canonical_payload(raw: dict, mapping: dict) -> dict:
    out={}
    business={}
    for original,field in mapping.items():
        if not field: continue
        raw_value=raw.get(original)
        if raw_value is None: continue
        if field == "as_of_date":
            if isinstance(raw_value, datetime):
                v=raw_value.date().isoformat()
            elif isinstance(raw_value, date):
                v=raw_value.isoformat()
            else:
                text=str(raw_value).strip()
                v=text
                for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        v=datetime.strptime(text,fmt).date().isoformat(); break
                    except ValueError:
                        pass
        else:
            v=str(raw_value).strip()
        if field in {"subject_group","employment_status","birth_year"}: business[field]=v
        else: out[field]=v
    if business: out["business_fields"]=business
    return out


def bulk_row_summary(row: BulkIngestRow, mapping: dict) -> dict:
    """Return user-facing values for an imported row without source internals."""
    payload=_canonical_payload(row.raw_payload_json or {},mapping or {})
    business=payload.get("business_fields") or {}
    return {
        "row_index":row.row_index,
        "status":row.status,
        "case_id":row.case_id,
        "error_code":row.error_code,
        "subject_name":payload.get("subject_name"),
        "subject_code":payload.get("subject_code"),
        "position":payload.get("position"),
        "unit_name":payload.get("unit_name"),
        "subject_group":business.get("subject_group"),
        "as_of_date":payload.get("as_of_date"),
    }


def _row_hash(raw: dict) -> str:
    return sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def _add_error(db: Session, job_id: str, row_index: int, column: str|None, code: str, severity: str, message: str):
    db.add(RowError(job_id=job_id,row_index=row_index,column=column,code=code,severity=severity,message_vi=message))


def profile_and_validate(db: Session, job: BulkIngestJob, content: bytes, *, user_mapping: dict|None=None) -> BulkIngestJob:
    headers,rows,first_row=_read_rows(job.file_name,content)
    # Refuse an oversized list before any row is written, so a rejected import
    # leaves nothing behind. This is checked here rather than in the route
    # because confirm re-profiles through the same function: a file that grew
    # past the cap between upload and confirm must not slip in on the second
    # call either.
    row_cap=get_settings().bulk_max_rows
    if len(rows)>row_cap:
        raise DocumentLimitError("BULK_ROW_LIMIT_EXCEEDED",rows=len(rows),limit=row_cap)
    inferred,details=infer_mapping(headers,rows)
    mapping=validate_mapping(headers, user_mapping) if user_mapping is not None else inferred
    if user_mapping:
        # Operator-confirmed aliases are candidates only; never auto-activate them.
        for h,field in user_mapping.items():
            if field and h not in _aliases().get(field,[]):
                db.add(HeaderAliasCandidate(canonical_field=field,alias=h,status="PENDING_QA",source_job_id=job.id))
    db.execute(delete(BulkIngestRow).where(BulkIngestRow.job_id==job.id))
    db.execute(delete(RowError).where(RowError.job_id==job.id))
    seen_codes={}
    errors=0; warnings=0; skipped=0
    # Excel/CSV row indices are the numbers the user sees (header offset included).
    for offset,raw in enumerate(rows):
        row_index=int(raw.get("_source_row_index", first_row+offset))
        canon=_canonical_payload(raw,mapping)
        row=BulkIngestRow(job_id=job.id,row_index=row_index,raw_payload_json=raw,row_hash=_row_hash(raw),status="PENDING")
        db.add(row)
        source_conf=raw.get("_source_table_confidence")
        if source_conf is not None:
            try:
                source_conf_value=float(source_conf)
            except (TypeError,ValueError):
                source_conf_value=0.0
            if source_conf_value < get_settings().bulk_ocr_table_confidence_min:
                _add_error(
                    db,job.id,row_index,None,"LOW_TABLE_OCR_CONFIDENCE","WARNING",
                    "Độ tin cậy OCR của bảng thấp; dòng sẽ được tạo nhưng bắt buộc đối soát",
                )
                warnings+=1
        name=(canon.get("subject_name") or "").strip()
        if not name:
            row.status="FAILED"; row.error_code="MISSING_REQUIRED"; row.error_detail="Thiếu họ tên"
            col=next((h for h,f in mapping.items() if f=="subject_name"),"Họ và tên")
            _add_error(db,job.id,row_index,col,"MISSING_REQUIRED","ERROR","Thiếu trường bắt buộc: họ và tên")
            errors+=1; continue
        code=(canon.get("subject_code") or "").strip()
        if code:
            digits=re.sub(r"\D","",code)
            numeric_like=bool(re.fullmatch(r"[\d\s.\-]+",code))
            if numeric_like and len(digits) not in {9,12}:
                row.status="FAILED"; row.error_code="BAD_FORMAT"; row.error_detail="CCCD/CMND phải có 9 hoặc 12 số"
                col=next((h for h,f in mapping.items() if f=="subject_code"),"CCCD/CMND")
                _add_error(db,job.id,row_index,col,"BAD_FORMAT","ERROR","CCCD/CMND phải có 9 hoặc 12 chữ số")
                errors+=1; continue
            key=digits or ascii_key(code)
            if key in seen_codes:
                row.status="SKIPPED_DUPLICATE"; row.error_code="DUPLICATE_IN_FILE"; row.error_detail=f"Trùng dòng {seen_codes[key]}"
                col=next((h for h,f in mapping.items() if f=="subject_code"),"CCCD/CMND")
                _add_error(db,job.id,row_index,col,"DUPLICATE_IN_FILE","ERROR",f"Mã cá nhân trùng với dòng {seen_codes[key]}")
                skipped+=1; continue
            seen_codes[key]=row_index
        as_of_value=(canon.get("as_of_date") or "").strip()
        if as_of_value:
            try:
                # Same plausibility rule as the text/lookup paths: a batch column must not
                # be a way around the effective-date guard.
                _validate_business_date(date.fromisoformat(as_of_value))
            except ValueError:
                row.status="FAILED"; row.error_code="BAD_FORMAT"; row.error_detail="Ngày đánh giá không hợp lệ"
                col=next((h for h,f in mapping.items() if f=="as_of_date"),"Ngày đánh giá")
                _add_error(db,job.id,row_index,col,"BAD_FORMAT","ERROR","Ngày đánh giá phải theo YYYY-MM-DD hoặc DD/MM/YYYY")
                errors+=1; continue
        unit=(canon.get("unit_name") or "").strip()
        # Ambiguity signal: multiple explicit unit fragments in one cell. Warning still creates a Case.
        if unit and len([x for x in re.split(r"\s*(?:\||;)\s*",unit) if x])>1:
            col=next((h for h,f in mapping.items() if f=="unit_name"),"Đơn vị công tác")
            _add_error(db,job.id,row_index,col,"AMBIGUOUS_UNIT","WARNING","Ô đơn vị chứa nhiều giá trị; hồ sơ sẽ vào NEED_REVIEW")
            warnings+=1
    db.flush()
    confidences=[v["confidence"] for v in details.values() if v.get("field")]
    required_mapped={f for f in mapping.values() if f}
    certain=(min(confidences or [0.0])>=get_settings().bulk_auto_map_threshold and "subject_name" in required_mapped)
    job.total_rows=len(rows); job.mapping_version=_mapping_config()[0]; job.mapping_json=mapping
    source_sheets=sorted({str(r.get("_source_sheet")) for r in rows if r.get("_source_sheet")})
    job.profile_json={"headers":headers,"mapping_details":details,"first_data_row":first_row,"auto_map_confident":certain,"source_sheets":source_sheets}
    job.validation_report={"errors":errors,"warnings":warnings,"skipped_duplicates":skipped,"rows":len(rows)}
    job.status="PROFILED" if certain or (user_mapping is not None and "subject_name" in required_mapped) else "AWAITING_MAPPING"
    db.flush(); return job


def process_bulk_row(db: Session, row: BulkIngestRow, job: BulkIngestJob) -> BulkIngestRow:
    if row.status in {"SUCCEEDED","FAILED","SKIPPED_DUPLICATE"}: return row
    row.attempts+=1
    raw=row.raw_payload_json or {}; structured=_canonical_payload(raw,job.mapping_json or {})
    source_meta={k:v for k,v in raw.items() if str(k).startswith("_source_")}
    structured["_bulk_source"]={
        "job_id":job.id,
        "row_index":row.row_index,
        "row_hash":row.row_hash,
        **source_meta,
    }
    idem=f"{job.id}:{row.row_index}"
    case=db.scalar(select(Case).where(Case.created_by==job.created_by, Case.idempotency_key==idem))
    if case is None:
        case=Case(created_by=job.created_by,input_type="TABULAR_LIST",raw_text="",input_payload=structured,idempotency_key=idem)
        db.add(case); db.flush()
        audit(
            db, actor="system:bulk-worker", role="SYSTEM", action="BULK_CASE_CREATE",
            entity_type="CASE", entity_id=case.id,
            metadata={"job_id":job.id,"row_index":row.row_index,"row_hash":row.row_hash},
        )
    unit=(structured.get("unit_name") or "")
    case.raw_text=" ".join(str(v) for v in [structured.get("subject_name"),structured.get("position"),unit] if v)
    warnings=list(db.scalars(
        select(RowError).where(
            RowError.job_id==job.id,
            RowError.row_index==row.row_index,
            RowError.severity=="WARNING",
        )
    ))
    if warnings:
        structured["_batch_warnings"]=[
            {"code":w.code,"column":w.column,"message_vi":w.message_vi} for w in warnings
        ]
    # WARNING rows still create Cases, but they must abstain to Human Review.
    process_case(db,case,structured)
    row.case_id=case.id; row.status="SUCCEEDED"; row.error_code=None; row.error_detail=None
    BULK_INGEST.labels(status="succeeded").inc()
    db.flush(); return row


def refresh_job_counts(db: Session, job: BulkIngestJob) -> BulkIngestJob:
    """Recompute a job's counters and terminal status from its rows.

    Every row task calls this after finishing its own row, and row tasks run
    concurrently — two inline workers in the local profile, more under Celery.
    That makes this a read-modify-write over shared state, so it takes the job
    row's lock first. Without it the aggregate below is a snapshot taken before
    a peer committed, and the last writer stores counts that omit its peer's
    row: a job whose rows are *all* terminal then keeps ``PROCESSING`` and a
    processed count short of its total, forever. Nothing finalises it
    afterwards in the local profile (there is no Beat running
    ``reconcile_bulk_jobs``), so the client polls a job that will never finish.

    Locking the job row makes the second caller wait for the first to commit and
    then re-read committed truth. On SQLite ``with_for_update`` is a no-op, which
    is correct there: the tests drive rows one at a time.
    """
    locked=db.scalar(select(BulkIngestJob).where(BulkIngestJob.id==job.id).with_for_update())
    if locked is not None:
        job=locked
    counts=dict(db.execute(select(BulkIngestRow.status,func.count()).where(BulkIngestRow.job_id==job.id).group_by(BulkIngestRow.status)).all())
    job.succeeded=int(counts.get("SUCCEEDED",0)); job.failed=int(counts.get("FAILED",0)); job.skipped=int(counts.get("SKIPPED_DUPLICATE",0))
    job.processed=job.succeeded+job.failed+job.skipped
    pending=int(counts.get("PENDING",0))
    if pending: job.status="PROCESSING"
    elif job.failed or job.skipped: job.status="COMPLETED_WITH_ERRORS"
    else: job.status="COMPLETED"
    db.flush(); return job
