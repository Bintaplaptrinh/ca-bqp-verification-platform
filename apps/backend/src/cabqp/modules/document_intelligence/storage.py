"""Original-document storage.

Two backends behind one interface. ``MinioStorage`` is the Docker/production
path. ``FilesystemStorage`` writes under ``STORAGE_ROOT`` and is what the local
profile uses, so a POC needs PostgreSQL and nothing else.

Both are addressed by the same opaque ``key``. The database stores only the
returned URI, metadata and checksum — never the bytes — so the two backends are
interchangeable without touching any caller.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath

from cabqp.shared.resilience import CircuitBreaker, retry_call
from cabqp.shared.settings import get_settings


class StorageKeyError(ValueError):
    """The key does not name a location inside the store."""


def _safe_relative(key: str) -> PurePosixPath:
    """Reject anything that would escape the store root.

    Keys are built server-side today, but a store that can be walked out of is
    a latent file-read primitive the moment one becomes caller-influenced.
    """
    candidate = PurePosixPath(str(key).strip().lstrip("/"))
    if not candidate.parts:
        raise StorageKeyError("Empty storage key")
    for part in candidate.parts:
        if part in {"..", "."} or part.startswith("/") or ":" in part or "\\" in part:
            raise StorageKeyError(f"Unsafe storage key segment: {part!r}")
    return candidate


def key_from_uri(uri: str) -> str:
    """Recover the storage key from a URI ``put`` returned.

    The two backends mint different schemes (``s3://bucket/key`` and
    ``file:///abs/path``), so only this module can read one back. Most callers
    never need to: ``process_document`` is handed the key alongside the URI.
    Bulk ingestion is the exception — a confirm request re-reads the source file
    stored by an earlier request, and the key it used is not carried anywhere
    else. Splitting on the MinIO prefix alone, as that call site used to, left a
    ``file://`` URI intact and ``_safe_relative`` then rejected its ``file:``
    segment, so every confirm-with-mapping on the local profile answered 500.
    """
    text = (uri or "").strip()
    if not text:
        raise StorageKeyError("Empty storage URI")
    if text.startswith("s3://"):
        _bucket, _, key = text[len("s3://") :].partition("/")
        if not key:
            raise StorageKeyError("Storage URI names no object")
        return key
    if text.startswith("file://"):
        root = get_settings().storage_path.resolve()
        try:
            return Path(text[len("file://") :]).resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise StorageKeyError("Stored path is outside the storage root") from exc
    # Already a bare key (older rows, and the tests' in-memory doubles).
    return text


class FilesystemStorage:
    """Local-profile store: one file per key under ``STORAGE_ROOT``."""

    def __init__(self):
        self.settings = get_settings()
        self.root = self.settings.storage_path

    def _path(self, key: str) -> Path:
        path = (self.root / Path(*_safe_relative(key).parts)).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise StorageKeyError("Storage key resolves outside the storage root")
        return path

    def ensure_bucket(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling then rename, so a reader never observes a partial
        # file and a crashed write leaves no half-document behind the key.
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(data)
        temporary.replace(path)
        return f"file://{path}"

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Stored object not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def get_stream(self, key: str, chunk_size: int = 1024 * 1024):
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Stored object not found: {key}")
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                yield chunk


class MinioStorage:
    def __init__(self):
        from minio import Minio

        s = get_settings()
        self.settings = s
        self.bucket = s.minio_bucket
        self.client = Minio(
            s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            secure=s.minio_secure,
        )
        self.breaker = CircuitBreaker(
            failure_threshold=s.circuit_breaker_failures,
            recovery_seconds=s.circuit_breaker_recovery_seconds,
        )

    def _call(self, fn):
        return self.breaker.call(
            lambda: retry_call(
                fn,
                attempts=self.settings.external_retry_attempts,
                base_seconds=self.settings.external_retry_base_seconds,
            )
        )

    def ensure_bucket(self):
        def op():
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)

        self._call(op)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.ensure_bucket()

        def op():
            self.client.put_object(
                self.bucket,
                key,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )

        self._call(op)
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes:
        def op():
            resp = self.client.get_object(self.bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        return self._call(op)

    def delete(self, key: str) -> None:
        self._call(lambda: self.client.remove_object(self.bucket, key))

    def get_stream(self, key: str, chunk_size: int = 1024 * 1024):
        resp = self._call(lambda: self.client.get_object(self.bucket, key))
        try:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            resp.close()
            resp.release_conn()


def ObjectStorage():  # noqa: N802 - kept callable-as-constructor for existing call sites
    """Return the store configured for this deployment profile."""
    if get_settings().effective_storage_backend == "filesystem":
        return FilesystemStorage()
    return MinioStorage()
