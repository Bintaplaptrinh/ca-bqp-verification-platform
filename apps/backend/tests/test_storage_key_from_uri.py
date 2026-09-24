"""A stored URI must round-trip back to the key that produced it.

`put` returns a backend-specific URI and bulk ingestion is the one caller that
has to turn one back into a key: a confirm request re-reads the source file an
earlier request stored, and nothing carries the key forward. The call site used
to strip only the MinIO prefix, which left a local-profile `file://` URI whole,
so `_safe_relative` rejected its `file:` segment and every confirm-with-mapping
on a spreadsheet answered 500 instead of queueing the job.
"""

from __future__ import annotations

import pytest

from cabqp.modules.document_intelligence.storage import (
    FilesystemStorage,
    StorageKeyError,
    key_from_uri,
)


def test_filesystem_uri_round_trips_to_its_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    from cabqp.shared.settings import get_settings

    get_settings.cache_clear()
    try:
        store = FilesystemStorage()
        key = "bulk/bulk_abc/deadbeef_danh sách.xlsx"
        uri = store.put(key, b"payload", "application/vnd.ms-excel")

        assert uri.startswith("file://")
        assert key_from_uri(uri) == key
        # The point of the round trip: the key it yields must actually read back.
        assert store.get(key_from_uri(uri)) == b"payload"
    finally:
        get_settings.cache_clear()


def test_minio_uri_round_trips_to_its_key():
    assert key_from_uri("s3://cabqp/bulk/bulk_abc/deadbeef_list.xlsx") == (
        "bulk/bulk_abc/deadbeef_list.xlsx"
    )


def test_bare_key_is_passed_through():
    """Older rows and test doubles store the key itself, not a URI."""
    assert key_from_uri("bulk/bulk_abc/list.xlsx") == "bulk/bulk_abc/list.xlsx"


@pytest.mark.parametrize("value", ["", "   ", "s3://bucket-only"])
def test_unusable_uris_are_refused(value):
    with pytest.raises(StorageKeyError):
        key_from_uri(value)


def test_path_outside_the_storage_root_is_refused(tmp_path, monkeypatch):
    """A URI is data from a database row, so it does not get to name any file."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    from cabqp.shared.settings import get_settings

    get_settings.cache_clear()
    try:
        (tmp_path / "store").mkdir()
        with pytest.raises(StorageKeyError):
            key_from_uri(f"file://{tmp_path / 'etc' / 'passwd'}")
    finally:
        get_settings.cache_clear()
