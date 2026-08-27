"""Tests for the POST /process compatibility endpoint used by console.html.

Person 1's extractor is mocked - these tests cover the adapting, not the AI.
"""

import pytest
from fastapi.testclient import TestClient

from backend.services import pipeline as pipeline_service

FAKE_INVOICE = {
    "doc_type": "invoice",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets (Set)",
    "quantity": 500,
    "value": 4200.00,
    "invoice_number": "INV-2026-0451",
}

CONSOLE_PAYLOAD = {
    "case_id": "case-clean-01",
    "files": ["sample_invoice.png", "packing_list_clean.png"],
}


@pytest.fixture
def mock_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: dict(FAKE_INVOICE, doc_type=kwargs["doc_type"]),
    )


def test_process_returns_console_shape(
    client: TestClient, mock_extraction: None
) -> None:
    response = client.post("/process", json=CONSOLE_PAYLOAD)
    assert response.status_code == 200

    body = response.json()
    assert body["invoice"]["invoice_number"] == "INV-2026-0451"
    assert body["packing_list"]["doc_type"] == "packing_list"
    assert body["verdict"]["case_id"] == "case-clean-01"
    # No rules engine in the repo yet, so the verdict must not claim a pass.
    assert body["verdict"]["verdict"] == "YELLOW"
    assert body["verdict"]["decision"] == "PENDING_REVIEW"
    assert body["verdict"]["rule_satisfied"] is False


def test_process_persists_a_real_claim(
    client: TestClient, mock_extraction: None
) -> None:
    """The shim must go through the real flow, not a shortcut."""
    body = client.post("/process", json=CONSOLE_PAYLOAD).json()
    claim_id = body["claim_id"]

    result = client.get(f"/claims/{claim_id}/result").json()
    assert len(result["documents"]) == 2

    actions = [r["action"] for r in client.get(f"/claims/{claim_id}/audit").json()]
    assert "document_uploaded" in actions
    assert "processing_completed" in actions


def test_extraction_failure_returns_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad extraction must fail loudly so the console falls back cleanly."""
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: {"error": "Gemini API call failed"},
    )
    response = client.post("/process", json=CONSOLE_PAYLOAD)
    assert response.status_code == 502


@pytest.mark.parametrize(
    "filename",
    ["../schema.py", "../../etc/passwd", "/etc/passwd", "..", "sub/dir/file.png"],
)
def test_path_traversal_is_rejected(client: TestClient, filename: str) -> None:
    response = client.post("/process", json={"case_id": "x", "files": [filename]})
    assert response.status_code in (400, 404)


def test_unknown_sample_returns_404(client: TestClient) -> None:
    response = client.post(
        "/process", json={"case_id": "x", "files": ["no_such_invoice.png"]}
    )
    assert response.status_code == 404


def test_undeterminable_doc_type_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/process", json={"case_id": "x", "files": ["test_connection.py"]}
    )
    assert response.status_code == 400


def test_empty_files_list_is_rejected(client: TestClient) -> None:
    response = client.post("/process", json={"case_id": "x", "files": []})
    assert response.status_code == 422


DECLARATION = {
    "agreement": "AIFTA",
    "hs_code": "630231",
    "fob_value": 4200.00,
    "non_originating_materials": [
        {"description": "Greige cotton fabric", "hs_code": "520811", "value": 1500.00}
    ],
}


def test_without_declaration_console_cannot_show_green(
    client: TestClient, mock_extraction: None
) -> None:
    """The gap this endpoint had: every case came back yellow."""
    body = client.post("/process", json=CONSOLE_PAYLOAD).json()
    assert body["verdict"]["verdict"] == "YELLOW"


def test_declaration_lets_the_clean_case_reach_green(
    client: TestClient, mock_extraction: None
) -> None:
    body = client.post(
        "/process", json={**CONSOLE_PAYLOAD, "origin_declaration": DECLARATION}
    ).json()

    assert body["verdict"]["verdict"] == "GREEN"
    assert body["verdict"]["decision"] == "APPROVED"
    assert body["verdict"]["rule_satisfied"] is True
    assert body["rules"]["origin"]["status"] == "EVALUATED"


def test_failing_declaration_reaches_red(
    client: TestClient, mock_extraction: None
) -> None:
    declaration = {
        **DECLARATION,
        "non_originating_materials": [
            {"description": "Greige cotton fabric", "hs_code": "520811", "value": 3500.0}
        ],
    }
    body = client.post(
        "/process", json={**CONSOLE_PAYLOAD, "origin_declaration": declaration}
    ).json()

    assert body["verdict"]["verdict"] == "RED"
    assert body["verdict"]["decision"] == "REJECTED"


def test_declaration_is_persisted_on_the_claim(
    client: TestClient, mock_extraction: None
) -> None:
    body = client.post(
        "/process", json={**CONSOLE_PAYLOAD, "origin_declaration": DECLARATION}
    ).json()
    stored = client.get(f"/claims/{body['claim_id']}/origin-declaration")
    assert stored.status_code == 200
    assert stored.json()["declaration"]["hs_code"] == "630231"
