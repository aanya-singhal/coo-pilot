import pytest
from fastapi.testclient import TestClient

from backend.services.storage import InMemoryStorage
from tests.conftest import PNG_BYTES, upload_png


def test_upload_png(
    client: TestClient, storage: InMemoryStorage, claim_id: str
) -> None:
    response = upload_png(client, claim_id)
    assert response.status_code == 201

    body = response.json()
    assert body["claim_id"] == claim_id
    assert body["doc_type"] == "invoice"
    assert body["size_bytes"] == len(PNG_BYTES)
    assert body["storage_path"] == f"claims/{claim_id}/{body['id']}.png"

    # The original file really reached storage.
    assert storage.download(body["storage_path"]) == PNG_BYTES


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("doc.pdf", "application/pdf"),
        ("doc.png", "image/png"),
        ("doc.jpg", "image/jpeg"),
        ("doc.jpeg", "image/jpeg"),
    ],
)
def test_allowed_file_types(
    client: TestClient, claim_id: str, filename: str, content_type: str
) -> None:
    response = client.post(
        f"/claims/{claim_id}/documents",
        files={"file": (filename, b"fake-bytes", content_type)},
        data={"doc_type": "invoice"},
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("notes.txt", "text/plain"),
        ("archive.zip", "application/zip"),
        ("script.exe", "application/octet-stream"),
        ("noextension", "image/png"),
    ],
)
def test_rejected_file_types(
    client: TestClient, claim_id: str, filename: str, content_type: str
) -> None:
    response = client.post(
        f"/claims/{claim_id}/documents",
        files={"file": (filename, b"data", content_type)},
        data={"doc_type": "invoice"},
    )
    assert response.status_code == 400


def test_mismatched_content_type_is_rejected(
    client: TestClient, claim_id: str
) -> None:
    """A .png name with a text content type must not slip through."""
    response = client.post(
        f"/claims/{claim_id}/documents",
        files={"file": ("sneaky.png", b"data", "text/plain")},
        data={"doc_type": "invoice"},
    )
    assert response.status_code == 400


def test_empty_file_is_rejected(client: TestClient, claim_id: str) -> None:
    response = client.post(
        f"/claims/{claim_id}/documents",
        files={"file": ("empty.png", b"", "image/png")},
        data={"doc_type": "invoice"},
    )
    assert response.status_code == 400


def test_upload_to_missing_claim_returns_404(client: TestClient) -> None:
    response = upload_png(client, "does-not-exist")
    assert response.status_code == 404


def test_invalid_doc_type_is_rejected(client: TestClient, claim_id: str) -> None:
    response = client.post(
        f"/claims/{claim_id}/documents",
        files={"file": ("invoice.png", PNG_BYTES, "image/png")},
        data={"doc_type": "not_a_type"},
    )
    assert response.status_code == 422


def test_list_documents(client: TestClient, claim_id: str) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    upload_png(client, claim_id, doc_type="packing_list")

    response = client.get(f"/claims/{claim_id}/documents")
    assert response.status_code == 200
    assert {d["doc_type"] for d in response.json()} == {"invoice", "packing_list"}


def test_upload_is_audited(client: TestClient, claim_id: str) -> None:
    upload_png(client, claim_id)
    actions = [row["action"] for row in client.get(f"/claims/{claim_id}/audit").json()]
    assert "document_uploaded" in actions
