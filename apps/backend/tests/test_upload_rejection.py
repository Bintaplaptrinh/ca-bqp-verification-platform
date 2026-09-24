"""Uploads are screened before any parser or OCR engine sees them.

The router has a catch-all that sends unrecognised bytes down the OCR path. That branch is
only ever reached from internal callers: every upload goes through validate_upload first,
and these tests pin that the screen actually holds.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException
from PIL import Image

from cabqp.modules.document_intelligence.file_validation import validate_upload

BINARY_JUNK = bytes([0, 1, 2, 3, 255, 254]) * 20
GZIP_HEADER = b"\x1f\x8b\x08" + bytes(30)
EXE_HEADER = b"MZ\x90\x00" + bytes(60)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name,content",
    [
        ("payload.bin", BINARY_JUNK),
        ("installer.exe", EXE_HEADER),
        ("archive.gz", GZIP_HEADER),
        ("script.sh", b"#!/bin/sh\nrm -rf /\n"),
        ("page.html", b"<html><body>x</body></html>"),
    ],
)
def test_unsupported_extensions_are_rejected(name, content):
    with pytest.raises(HTTPException) as exc:
        validate_upload(name, content, None)
    assert exc.value.status_code == 415
    assert "Unsupported file extension" in str(exc.value.detail)


@pytest.mark.parametrize(
    "name",
    ["fake.png", "fake.pdf", "fake.docx", "fake.xlsx", "fake.jpg"],
)
def test_content_must_match_the_claimed_extension(name):
    """Renaming arbitrary bytes to a permitted extension must not get them parsed."""
    with pytest.raises(HTTPException) as exc:
        validate_upload(name, BINARY_JUNK, None)
    assert exc.value.status_code == 415
    assert "signature does not match" in str(exc.value.detail)


def test_declared_mime_must_be_allowed_for_the_extension():
    with pytest.raises(HTTPException) as exc:
        validate_upload("scan.png", _png(), "application/x-msdownload")
    assert exc.value.status_code == 415


def test_genuine_png_is_accepted():
    name, mime = validate_upload("scan.png", _png(), "image/png")
    assert name == "scan.png"
    assert mime == "image/png"


def test_genuine_text_is_accepted():
    name, mime = validate_upload("note.txt", "Đồng chí A".encode(), "text/plain")
    assert name == "note.txt"
    assert mime == "text/plain"


def test_office_archive_is_accepted_and_typed():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<x/>")
    name, mime = validate_upload("ho-so.docx", buffer.getvalue(), None)
    assert name == "ho-so.docx"
    assert "wordprocessingml" in mime


def test_extensionless_upload_is_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_upload("khong-co-duoi", BINARY_JUNK, None)
    assert exc.value.status_code == 415
