"""Office archives must not smuggle paths outside their extraction root.

DOCX/XLSX uploads are ZIP containers. The traversal guard compared each entry against the
string "../", which splitting on "/" can never produce, so every traversal entry was
accepted. These tests pin the segment-based check.
"""
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from cabqp.modules.document_intelligence.file_validation import _zip_kind, safe_filename

BACKSLASH = chr(92)


def _office_zip(extra_names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<x/>")
        for name in extra_names:
            archive.writestr(name, "payload")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "entry",
    [
        "../../etc/passwd",
        "word/../../evil.xml",
        "..",
        ".." + BACKSLASH + ".." + BACKSLASH + "evil.txt",
    ],
)
def test_traversal_entries_are_rejected(entry):
    with pytest.raises(HTTPException) as exc:
        _zip_kind(_office_zip([entry]))
    assert exc.value.status_code == 422
    assert "Unsafe path" in str(exc.value.detail)


def test_absolute_entry_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _zip_kind(_office_zip(["/etc/passwd"]))
    assert exc.value.status_code == 422


def test_ordinary_office_archive_is_accepted():
    """The guard must not reject legitimate documents."""
    assert _zip_kind(_office_zip(["word/styles.xml", "docProps/core.xml"])) == "docx"


def test_workbook_archive_is_still_detected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<x/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<x/>")
    assert _zip_kind(buffer.getvalue()) == "xlsx"


@pytest.mark.parametrize("name", ["..", "....", ". .", "   "])
def test_dot_only_filenames_are_replaced(name):
    """A name made only of dots is a path fragment, not a filename."""
    assert safe_filename(name) == "upload"


def test_ordinary_filenames_survive():
    assert safe_filename("ho-so.pdf") == "ho-so.pdf"
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(None) == "upload"
