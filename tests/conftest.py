"""Test fixtures.

Every test runs against in-memory database and storage, so no Supabase or
Gemini credentials are needed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.database import InMemoryDatabase, get_database
from backend.main import app
from backend.services.storage import InMemoryStorage, get_storage

# A tiny but valid 1x1 PNG.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
    "426082"
)


@pytest.fixture
def db() -> InMemoryDatabase:
    return InMemoryDatabase()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(db: InMemoryDatabase, storage: InMemoryStorage) -> Iterator[TestClient]:
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def claim_id(client: TestClient) -> str:
    response = client.post("/claims", json={"reference": "TEST-001"})
    assert response.status_code == 201
    return response.json()["id"]


def upload_png(client: TestClient, claim_id: str, doc_type: str = "invoice"):
    """Helper: upload a valid PNG to a claim."""
    return client.post(
        f"/claims/{claim_id}/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
        data={"doc_type": doc_type},
    )
