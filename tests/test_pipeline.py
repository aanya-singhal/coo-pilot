"""Pipeline tests.

Person 1's extractor and Person 2's rules engine are mocked - the backend is
only responsible for calling them and storing what they return.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.services import pipeline as pipeline_service
from backend.services import rules_adapter
from tests.conftest import upload_png

FAKE_INVOICE = {
    "doc_type": "invoice",
    "exporter": "Acme Exports",
    "product": "Cotton Shirts",
    "quantity": 500,
    "value": 12500,
    "invoice_number": "INV-1",
}

FAKE_RULES_RESULT = {
    "reconciliation": {"quantity_match": True},
    "rules": {"rule_applied": "quantity_match", "rule_satisfied": True},
    "risk": {"score": 0.1, "band": "LOW"},
    "decision": "APPROVED",
}


@pytest.fixture
def mock_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for Person 1 and Person 2."""
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: dict(FAKE_INVOICE, doc_type=kwargs["doc_type"]),
    )
    monkeypatch.setattr(
        pipeline_service, "run_rules", lambda extraction: dict(FAKE_RULES_RESULT)
    )


def test_process_without_documents_returns_400(
    client: TestClient, claim_id: str
) -> None:
    response = client.post(f"/claims/{claim_id}/process")
    assert response.status_code == 400


def test_process_missing_claim_returns_404(client: TestClient) -> None:
    response = client.post("/claims/does-not-exist/process")
    assert response.status_code == 404


def test_process_claim(client: TestClient, claim_id: str, mock_modules: None) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    upload_png(client, claim_id, doc_type="packing_list")

    response = client.post(f"/claims/{claim_id}/process")
    assert response.status_code == 200

    body = response.json()
    assert body["documents_processed"] == 2
    assert body["decision"] == "APPROVED"
    assert body["status"] == "APPROVED"


def test_result_after_processing(
    client: TestClient, claim_id: str, mock_modules: None
) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    client.post(f"/claims/{claim_id}/process")

    body = client.get(f"/claims/{claim_id}/result").json()

    # Everything the dashboard needs is present.
    assert body["claim"]["id"] == claim_id
    assert len(body["documents"]) == 1
    assert body["extraction"]["invoice"]["exporter"] == "Acme Exports"
    assert body["reconciliation"] == FAKE_RULES_RESULT["reconciliation"]
    assert body["rules"] == FAKE_RULES_RESULT["rules"]
    assert body["risk"] == FAKE_RULES_RESULT["risk"]
    assert body["decision"] == "APPROVED"
    assert body["status"] == "APPROVED"
    assert body["processed_at"]


def test_extraction_results_are_stored_per_document(
    client: TestClient, claim_id: str, db: Any, mock_modules: None
) -> None:
    upload_png(client, claim_id, doc_type="invoice")
    client.post(f"/claims/{claim_id}/process")

    rows = db.list_extracted_data(claim_id)
    assert len(rows) == 1
    assert rows[0]["data"]["invoice_number"] == "INV-1"


def test_pipeline_is_audited(
    client: TestClient, claim_id: str, mock_modules: None
) -> None:
    upload_png(client, claim_id)
    client.post(f"/claims/{claim_id}/process")

    actions = [row["action"] for row in client.get(f"/claims/{claim_id}/audit").json()]
    assert "processing_started" in actions
    assert "processing_completed" in actions


def test_extraction_failure_is_stored_not_raised(
    client: TestClient, claim_id: str, db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing document must not abort the run - the error is persisted."""
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: {"error": "Gemini API call failed"},
    )
    upload_png(client, claim_id)

    response = client.post(f"/claims/{claim_id}/process")
    assert response.status_code == 200

    assert db.list_extracted_data(claim_id)[0]["data"]["error"]


def test_unknown_decision_falls_back_to_pending_review(
    client: TestClient, claim_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipeline_service, "extract_document_bytes", lambda **kwargs: FAKE_INVOICE
    )
    monkeypatch.setattr(
        pipeline_service, "run_rules", lambda extraction: {"decision": "YELLOW"}
    )
    upload_png(client, claim_id)

    body = client.post(f"/claims/{claim_id}/process").json()
    assert body["decision"] == "YELLOW"          # stored verbatim
    assert body["status"] == "PENDING_REVIEW"    # claim awaits a human


def test_rules_adapter_discovers_the_engine() -> None:
    """The adapter must find rules.engine.evaluate without any backend change."""
    result = rules_adapter.run_rules({"invoice": FAKE_INVOICE})

    assert result["rules"] is not None
    assert result["reconciliation"] is not None
    assert result["risk"] is not None
    # Only an invoice, and no origin declaration, so nothing can be approved.
    assert result["decision"] == "PENDING_REVIEW"


def test_rules_adapter_placeholder_when_engine_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no engine importable, the adapter must not invent a verdict."""
    monkeypatch.setattr(rules_adapter, "CANDIDATE_MODULES", ("no.such.module",))
    result = rules_adapter.run_rules({"invoice": FAKE_INVOICE})

    assert result["decision"] == "PENDING_REVIEW"
    assert result["rules"] is None
    assert result["raw"]["status"] == "NOT_IMPLEMENTED"
