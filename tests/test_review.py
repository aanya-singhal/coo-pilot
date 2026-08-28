"""Human review workflow, review queue, and dashboard."""

import pytest
from fastapi.testclient import TestClient

from backend.services import pipeline as pipeline_service
from tests.conftest import upload_png

REVIEWER = {"reviewer": "officer.rao", "comments": "Checked against Form I."}

INVOICE = {
    "doc_type": "invoice",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets",
    "quantity": 500,
    "value": 4200.00,
    "invoice_number": "INV-2026-0451",
}


@pytest.fixture
def mock_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline_service,
        "extract_document_bytes",
        lambda **kwargs: dict(INVOICE, doc_type=kwargs["doc_type"]),
    )


# --- claim identity ---------------------------------------------------


def test_claim_gets_a_claim_number_and_exporter(client: TestClient) -> None:
    body = client.post(
        "/claims", json={"reference": "EXP-1", "exporter": "Nilgiri Textiles Pvt Ltd"}
    ).json()

    assert body["claim_number"].startswith("CLM-")
    assert body["exporter"] == "Nilgiri Textiles Pvt Ltd"


def test_claim_numbers_are_unique(client: TestClient) -> None:
    numbers = {client.post("/claims", json={}).json()["claim_number"] for _ in range(25)}
    assert len(numbers) == 25


# --- review queue -----------------------------------------------------


def test_review_queue_path_is_not_captured_as_a_claim_id(client: TestClient) -> None:
    """GET /claims/review must not be read as claim_id='review'."""
    response = client.get("/claims/review")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_review_queue_only_lists_claims_needing_attention(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    # A freshly created claim is CREATED, so not in the queue.
    assert claim_id not in [c["id"] for c in client.get("/claims/review").json()]

    upload_png(client, claim_id)
    client.post(f"/claims/{claim_id}/verify")

    # Now PENDING_REVIEW, so it should appear.
    assert claim_id in [c["id"] for c in client.get("/claims/review").json()]


def test_approving_removes_a_claim_from_the_queue(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    upload_png(client, claim_id)
    client.post(f"/claims/{claim_id}/verify")
    client.post(f"/claims/{claim_id}/approve", json=REVIEWER)

    assert claim_id not in [c["id"] for c in client.get("/claims/review").json()]


# --- decisions --------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "expected_status"),
    [
        ("approve", "APPROVED"),
        ("reject", "REJECTED"),
        ("request-info", "REQUESTED_INFO"),
    ],
)
def test_review_actions_set_status_and_record_a_decision(
    client: TestClient, claim_id: str, endpoint: str, expected_status: str
) -> None:
    response = client.post(f"/claims/{claim_id}/{endpoint}", json=REVIEWER)
    assert response.status_code == 200

    decision = response.json()
    assert decision["decision"] == expected_status
    assert decision["reviewer"] == "officer.rao"

    assert client.get(f"/claims/{claim_id}").json()["status"] == expected_status


def test_decision_appears_in_history_and_result(
    client: TestClient, claim_id: str
) -> None:
    client.post(f"/claims/{claim_id}/approve", json=REVIEWER)

    history = client.get(f"/claims/{claim_id}/decisions").json()
    assert len(history) == 1
    assert history[0]["comments"] == "Checked against Form I."

    assert len(client.get(f"/claims/{claim_id}/result").json()["decisions"]) == 1


def test_review_is_audited(client: TestClient, claim_id: str) -> None:
    client.post(f"/claims/{claim_id}/reject", json=REVIEWER)
    actions = [r["action"] for r in client.get(f"/claims/{claim_id}/audit").json()]
    assert "rejected" in actions


def test_reviewer_is_required(client: TestClient, claim_id: str) -> None:
    assert client.post(f"/claims/{claim_id}/approve", json={}).status_code == 422
    assert (
        client.post(f"/claims/{claim_id}/approve", json={"reviewer": ""}).status_code
        == 422
    )


def test_review_on_missing_claim_returns_404(client: TestClient) -> None:
    assert client.post("/claims/nope/approve", json=REVIEWER).status_code == 404
    assert client.get("/claims/nope/review").status_code == 404


def test_review_detail_returns_the_full_case(
    client: TestClient, claim_id: str, mock_extraction: None
) -> None:
    upload_png(client, claim_id)
    client.post(f"/claims/{claim_id}/verify")

    body = client.get(f"/claims/{claim_id}/review").json()
    assert body["claim"]["id"] == claim_id
    assert len(body["documents"]) == 1
    assert body["status"] == "PENDING_REVIEW"


# --- claim filtering --------------------------------------------------


def test_list_claims_filters_by_status(client: TestClient, claim_id: str) -> None:
    client.post(f"/claims/{claim_id}/approve", json=REVIEWER)
    other = client.post("/claims", json={}).json()["id"]

    approved = client.get("/claims", params={"status": "APPROVED"}).json()
    assert [c["id"] for c in approved] == [claim_id]

    created = client.get("/claims", params={"status": "CREATED"}).json()
    assert other in [c["id"] for c in created]


def test_list_claims_accepts_several_statuses(
    client: TestClient, claim_id: str
) -> None:
    client.post(f"/claims/{claim_id}/reject", json=REVIEWER)
    client.post("/claims", json={})

    rows = client.get("/claims?status=REJECTED&status=CREATED").json()
    assert {c["status"] for c in rows} == {"REJECTED", "CREATED"}


def test_invalid_status_filter_is_rejected(client: TestClient) -> None:
    assert client.get("/claims", params={"status": "NONSENSE"}).status_code == 422


# --- dashboard --------------------------------------------------------


def test_dashboard_counts(client: TestClient) -> None:
    approved = client.post("/claims", json={}).json()["id"]
    client.post(f"/claims/{approved}/approve", json=REVIEWER)
    rejected = client.post("/claims", json={}).json()["id"]
    client.post(f"/claims/{rejected}/reject", json=REVIEWER)
    client.post("/claims", json={})

    body = client.get("/dashboard").json()
    assert body["total"] == 3
    assert body["approved"] == 1
    assert body["rejected"] == 1
    assert body["created"] == 1
    assert body["pending_review"] == 0


def test_dashboard_on_empty_database(client: TestClient) -> None:
    body = client.get("/dashboard").json()
    assert body["total"] == 0
    assert body["approved"] == 0
