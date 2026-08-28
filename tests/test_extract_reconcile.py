"""Per-document extraction and the standalone reconcile endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.services import pipeline as pipeline_service
from tests.conftest import upload_png

INVOICE = {
    "doc_type": "invoice",
    "exporter": "ABC Ltd",
    "product": "Steel Bolts",
    "quantity": 1000,
    "value": 5000.00,
    "invoice_number": "INV-77",
}

PACKING_LIST = {
    "doc_type": "packing_list",
    "exporter": "ABC Ltd",
    "product": "Steel Bolts",
    "quantity": 1000,
    "packages": 40,
    "packing_list_number": "PL-77",
}


def stub_extraction(monkeypatch: pytest.MonkeyPatch, packing_quantity: int) -> None:
    def fake(**kwargs):
        if kwargs["doc_type"] == "invoice":
            return dict(INVOICE)
        return dict(PACKING_LIST, quantity=packing_quantity)

    monkeypatch.setattr(pipeline_service, "extract_document_bytes", fake)


@pytest.fixture
def matching(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_extraction(monkeypatch, 1000)


@pytest.fixture
def mismatched(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_extraction(monkeypatch, 1200)


def upload_pair(client: TestClient, claim_id: str) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    upload_png(client, claim_id, doc_type="packing_list")


def extract_all(client: TestClient, claim_id: str) -> None:
    for doc in client.get(f"/claims/{claim_id}/documents").json():
        client.post(f"/claims/{claim_id}/documents/{doc['id']}/extract")


# --- per-document extraction -----------------------------------------


def test_extract_one_document(
    client: TestClient, claim_id: str, matching: None
) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    doc_id = client.get(f"/claims/{claim_id}/documents").json()[0]["id"]

    response = client.post(f"/claims/{claim_id}/documents/{doc_id}/extract")
    assert response.status_code == 200

    body = response.json()
    assert body["extraction_status"] == "SUCCESS"
    assert body["data"]["invoice_number"] == "INV-77"
    assert body["document_id"] == doc_id


def test_extraction_failure_is_stored_not_raised(
    client: TestClient, claim_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: {"error": "Gemini API call failed"},
    )
    upload_png(client, claim_id)
    doc_id = client.get(f"/claims/{claim_id}/documents").json()[0]["id"]

    response = client.post(f"/claims/{claim_id}/documents/{doc_id}/extract")
    assert response.status_code == 200
    assert response.json()["extraction_status"] == "FAILED"
    assert response.json()["data"]["error"]


def test_re_extracting_replaces_the_previous_result(
    client: TestClient, claim_id: str, db, matching: None
) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    doc_id = client.get(f"/claims/{claim_id}/documents").json()[0]["id"]

    client.post(f"/claims/{claim_id}/documents/{doc_id}/extract")
    client.post(f"/claims/{claim_id}/documents/{doc_id}/extract")

    assert len(db.list_extracted_data(claim_id)) == 1


def test_extract_unknown_document_returns_404(
    client: TestClient, claim_id: str
) -> None:
    response = client.post(f"/claims/{claim_id}/documents/nope/extract")
    assert response.status_code == 404


def test_extract_document_from_another_claim_returns_404(
    client: TestClient, claim_id: str, matching: None
) -> None:
    """A document must not be reachable through a claim it does not belong to."""
    upload_png(client, claim_id)
    doc_id = client.get(f"/claims/{claim_id}/documents").json()[0]["id"]
    other = client.post("/claims", json={}).json()["id"]

    response = client.post(f"/claims/{other}/documents/{doc_id}/extract")
    assert response.status_code == 404


def test_extraction_is_audited(
    client: TestClient, claim_id: str, matching: None
) -> None:
    upload_png(client, claim_id)
    doc_id = client.get(f"/claims/{claim_id}/documents").json()[0]["id"]
    client.post(f"/claims/{claim_id}/documents/{doc_id}/extract")

    actions = [r["action"] for r in client.get(f"/claims/{claim_id}/audit").json()]
    assert "extraction_started" in actions
    assert "extraction_completed" in actions


# --- reconciliation ---------------------------------------------------


def test_reconcile_matching_documents(
    client: TestClient, claim_id: str, matching: None
) -> None:
    upload_pair(client, claim_id)
    extract_all(client, claim_id)

    body = client.post(f"/claims/{claim_id}/reconcile").json()
    assert body["status"] == "MATCHED"
    assert body["mismatches"] == []

    fields = {m["field"] for m in body["matches"]}
    assert {"exporter", "product", "quantity"} <= fields

    quantity = next(m for m in body["matches"] if m["field"] == "quantity")
    assert quantity["invoice"] == 1000
    assert quantity["packing_list"] == 1000


def test_reconcile_reports_a_quantity_mismatch(
    client: TestClient, claim_id: str, mismatched: None
) -> None:
    upload_pair(client, claim_id)
    extract_all(client, claim_id)

    body = client.post(f"/claims/{claim_id}/reconcile").json()
    assert body["status"] == "MISMATCHED"

    quantity = next(m for m in body["mismatches"] if m["field"] == "quantity")
    assert quantity["invoice"] == 1000
    assert quantity["packing_list"] == 1200


def test_reconcile_without_extraction_returns_400(
    client: TestClient, claim_id: str
) -> None:
    upload_pair(client, claim_id)
    assert client.post(f"/claims/{claim_id}/reconcile").status_code == 400


def test_reconcile_on_missing_claim_returns_404(client: TestClient) -> None:
    assert client.post("/claims/nope/reconcile").status_code == 404


def test_reconcile_is_audited(
    client: TestClient, claim_id: str, matching: None
) -> None:
    upload_pair(client, claim_id)
    extract_all(client, claim_id)
    client.post(f"/claims/{claim_id}/reconcile")

    actions = [r["action"] for r in client.get(f"/claims/{claim_id}/audit").json()]
    assert "reconciliation_completed" in actions


def test_failed_extraction_is_not_reconciled_as_real_data(
    client: TestClient, claim_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error payload must not be compared as if it held fields."""
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: (
            dict(INVOICE)
            if kwargs["doc_type"] == "invoice"
            else {"error": "extraction failed"}
        ),
    )
    upload_pair(client, claim_id)
    extract_all(client, claim_id)

    body = client.post(f"/claims/{claim_id}/reconcile").json()
    # Nothing could be compared, which must not read as "everything agrees".
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["missing_documents"] == ["packing_list"]
    assert body["matches"] == []


# --- verify alias -----------------------------------------------------


def test_verify_and_process_behave_identically(
    client: TestClient, matching: None
) -> None:
    results = []
    for endpoint in ("verify", "process"):
        claim = client.post("/claims", json={}).json()["id"]
        upload_pair(client, claim)
        results.append(client.post(f"/claims/{claim}/{endpoint}").json())

    assert results[0]["decision"] == results[1]["decision"]
    assert results[0]["documents_processed"] == results[1]["documents_processed"] == 2
