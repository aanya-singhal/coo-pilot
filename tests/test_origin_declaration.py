"""Tests for attaching an origin declaration and its effect on the pipeline.

This closes the gap where an invoice and packing list alone can never
substantiate origin.
"""

import pytest
from fastapi.testclient import TestClient

from backend.services import pipeline as pipeline_service
from tests.conftest import upload_png

DECLARATION = {
    "agreement": "AIFTA",
    "hs_code": "630231",
    "fob_value": 4200.00,
    "non_originating_materials": [
        {"description": "Greige cotton fabric", "hs_code": "520811", "value": 1500.00}
    ],
}

INVOICE = {
    "doc_type": "invoice",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets",
    "quantity": 500,
    "value": 4200.00,
    "invoice_number": "INV-2026-0451",
}

PACKING_LIST = {
    "doc_type": "packing_list",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets",
    "quantity": 500,
    "packages": 25,
    "packing_list_number": "PL-2026-0451",
}


@pytest.fixture
def mock_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Person 1's extractor, stubbed with consistent documents."""
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: dict(
            INVOICE if kwargs["doc_type"] == "invoice" else PACKING_LIST
        ),
    )


def attach_documents(client: TestClient, claim_id: str) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    upload_png(client, claim_id, doc_type="packing_list")


def test_set_and_get_declaration(client: TestClient, claim_id: str) -> None:
    response = client.put(
        f"/claims/{claim_id}/origin-declaration", json=DECLARATION
    )
    assert response.status_code == 200
    assert response.json()["declaration"]["hs_code"] == "630231"

    fetched = client.get(f"/claims/{claim_id}/origin-declaration")
    assert fetched.status_code == 200
    assert fetched.json()["declaration"]["fob_value"] == 4200.00


def test_setting_twice_replaces(client: TestClient, claim_id: str) -> None:
    client.put(f"/claims/{claim_id}/origin-declaration", json=DECLARATION)
    client.put(
        f"/claims/{claim_id}/origin-declaration",
        json={**DECLARATION, "hs_code": "610910"},
    )
    body = client.get(f"/claims/{claim_id}/origin-declaration").json()
    assert body["declaration"]["hs_code"] == "610910"


def test_declaration_on_missing_claim_returns_404(client: TestClient) -> None:
    response = client.put("/claims/nope/origin-declaration", json=DECLARATION)
    assert response.status_code == 404


def test_get_missing_declaration_returns_404(
    client: TestClient, claim_id: str
) -> None:
    assert client.get(f"/claims/{claim_id}/origin-declaration").status_code == 404


def test_negative_fob_value_is_rejected(client: TestClient, claim_id: str) -> None:
    response = client.put(
        f"/claims/{claim_id}/origin-declaration",
        json={**DECLARATION, "fob_value": -1},
    )
    assert response.status_code == 422


def test_without_declaration_pipeline_cannot_approve(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    """Documents agree, but origin is unsubstantiated - so no approval."""
    attach_documents(client, claim_id)
    body = client.post(f"/claims/{claim_id}/process").json()

    assert body["decision"] == "PENDING_REVIEW"
    result = client.get(f"/claims/{claim_id}/result").json()
    assert result["rules"]["origin"]["status"] == "INSUFFICIENT_DATA"


def test_with_declaration_pipeline_approves(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    """The same case, once the cost statement is supplied, evaluates for real."""
    attach_documents(client, claim_id)
    client.put(f"/claims/{claim_id}/origin-declaration", json=DECLARATION)

    body = client.post(f"/claims/{claim_id}/process").json()
    assert body["decision"] == "APPROVED"
    assert body["status"] == "APPROVED"

    result = client.get(f"/claims/{claim_id}/result").json()
    origin = result["rules"]["origin"]
    assert origin["status"] == "EVALUATED"
    assert origin["value_content"]["regional_value_content_percent"] == pytest.approx(
        64.29
    )
    assert result["risk"]["score"] == 0


def test_declaration_below_threshold_is_rejected(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    attach_documents(client, claim_id)
    declaration = {
        **DECLARATION,
        "non_originating_materials": [
            {"description": "Greige cotton fabric", "hs_code": "520811", "value": 3500.0}
        ],
    }
    client.put(f"/claims/{claim_id}/origin-declaration", json=declaration)

    body = client.post(f"/claims/{claim_id}/process").json()
    assert body["decision"] == "REJECTED"
    assert body["status"] == "REJECTED"


def test_declaration_is_audited(client: TestClient, claim_id: str) -> None:
    client.put(f"/claims/{claim_id}/origin-declaration", json=DECLARATION)
    actions = [r["action"] for r in client.get(f"/claims/{claim_id}/audit").json()]
    assert "origin_declaration_set" in actions
