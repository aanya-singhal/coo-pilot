"""Supabase Storage integration for original uploaded documents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import PurePosixPath
from typing import Any

from backend.config import get_settings
from backend.database import get_supabase_client

logger = logging.getLogger(__name__)


class Storage(ABC):
    """Narrow object-storage interface used by the backend."""

    @abstractmethod
    def upload(self, *, path: str, content: bytes, content_type: str) -> str:
        """Store ``content`` at ``path`` and return the stored path."""

    @abstractmethod
    def download(self, path: str) -> bytes:
        """Return the bytes previously stored at ``path``."""

    @abstractmethod
    def public_url(self, path: str) -> str | None:
        """Return a URL for ``path``, or ``None`` if one cannot be produced."""


class InMemoryStorage(Storage):
    """Dict-backed storage for tests and credential-free local runs."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, *, path: str, content: bytes, content_type: str) -> str:
        self.objects[path] = content
        return path

    def download(self, path: str) -> bytes:
        try:
            return self.objects[path]
        except KeyError:
            raise FileNotFoundError(path) from None

    def public_url(self, path: str) -> str | None:
        return None


class SupabaseStorage(Storage):
    """Supabase Storage implementation."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def upload(self, *, path: str, content: bytes, content_type: str) -> str:
        self._client.storage.from_(self._bucket).upload(
            path=path,
            file=content,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return path

    def download(self, path: str) -> bytes:
        return self._client.storage.from_(self._bucket).download(path)

    def public_url(self, path: str) -> str | None:
        try:
            return self._client.storage.from_(self._bucket).get_public_url(path)
        except Exception as exc:  # pragma: no cover - depends on bucket config
            logger.warning("Could not build public URL for %s: %s", path, exc)
            return None


def build_storage_path(claim_id: str, document_id: str, filename: str) -> str:
    """Return the object path used for an uploaded document.

    Only the extension of the original filename is kept, so user-supplied
    names can never influence the storage layout.
    """
    suffix = PurePosixPath(filename).suffix.lower()
    return f"claims/{claim_id}/{document_id}{suffix}"


_storage: Storage | None = None


def get_storage() -> Storage:
    """FastAPI dependency returning the active storage backend."""
    global _storage

    if _storage is None:
        settings = get_settings()
        client = get_supabase_client(settings)
        if client is None:
            logger.warning(
                "SUPABASE_URL/SUPABASE_KEY not set - using in-memory storage. "
                "Uploaded files will be lost when the process exits."
            )
            _storage = InMemoryStorage()
        else:
            _storage = SupabaseStorage(client, settings.supabase_bucket)
    return _storage
