from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".txt", ".csv"}
DECLARED_MIMES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip", "application/octet-stream"},
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "image/jpg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "image/jpg", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".csv": {"text/csv", "application/csv", "text/plain", "application/octet-stream", "application/vnd.ms-excel"},
}


def safe_filename(name: str | None) -> str:
    raw = Path(name or "upload").name.replace("\x00", "")
    clean = "".join(ch for ch in raw if ch.isprintable() and ch not in "/\\")
    # A name made only of dots carries no filename and reads as a relative path segment.
    if not clean.strip(". "):
        return "upload"
    return clean[:240] or "upload"


def _zip_kind(content: bytes) -> str | None:
    try:
        with ZipFile(BytesIO(content)) as z:
            infos = z.infolist()
            if len(infos) > 20_000:
                raise HTTPException(422, "Office archive contains too many entries")
            expanded = 0
            names = set()
            for info in infos:
                name = info.filename.replace("\\", "/")
                segments = name.split("/")
                # Compare against the ".." segment: splitting on "/" can never yield the
                # string "../", so the previous check silently accepted every traversal
                # path (verified: "../../etc/passwd" and "..\\..\\evil.txt" both passed).
                if name.startswith("/") or ".." in segments:
                    raise HTTPException(422, "Unsafe path inside Office archive")
                expanded += info.file_size
                if expanded > 250 * 1024 * 1024:
                    raise HTTPException(422, "Office archive expands beyond safe limit")
                names.add(name)
    except BadZipFile:
        return None
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    return "zip"


def detect_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"PK\x03\x04"):
        return _zip_kind(content) or "zip"
    if content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "xls"
    if b"\x00" not in content[:4096]:
        try:
            content[:4096].decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            pass
    return "unknown"


def validate_upload(
    file_name: str | None,
    content: bytes,
    declared_mime: str | None = None,
) -> tuple[str, str]:
    name = safe_filename(file_name)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file extension: {ext or '(none)'}")

    declared = (declared_mime or "").split(";", 1)[0].strip().casefold()
    if declared and declared not in {x.casefold() for x in DECLARED_MIMES[ext]}:
        raise HTTPException(415, "Declared MIME type is not allowed for this extension")

    actual = detect_type(content)
    expected = {
        ".pdf": {"pdf"},
        ".docx": {"docx"},
        ".xlsx": {"xlsx"},
        ".xls": {"xls"},
        ".png": {"png"},
        ".jpg": {"jpeg"},
        ".jpeg": {"jpeg"},
        ".txt": {"text"},
        ".csv": {"text"},
    }[ext]
    if actual not in expected:
        raise HTTPException(415, f"File signature does not match extension {ext}")

    mime = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "png": "image/png",
        "jpeg": "image/jpeg",
        "text": "text/csv" if ext == ".csv" else "text/plain",
    }[actual]
    return name, mime
