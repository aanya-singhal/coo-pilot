from fastapi.testclient import TestClient

from backend.database import InMemoryDatabase


def test_create_claim(client: TestClient) -> None:
    response = client.post(
        "/claims", json={"reference": "EXP-2026-01", "metadata": {"exporter": "Acme"}}
    )
    assert response.status_code == 201

    body = response.json()
    assert body["status"] == "CREATED"
    assert body["reference"] == "EXP-2026-01"
    assert body["metadata"] == {"exporter": "Acme"}
    assert body["id"]


def test_create_claim_without_reference(client: TestClient) -> None:
    response = client.post("/claims", json={})
    assert response.status_code == 201
    assert response.json()["reference"] is None


def test_get_claim(client: TestClient, claim_id: str) -> None:
    response = client.get(f"/claims/{claim_id}")
    assert response.status_code == 200
    assert response.json()["id"] == claim_id


def test_get_missing_claim_returns_404(client: TestClient) -> None:
    response = client.get("/claims/does-not-exist")
    assert response.status_code == 404


def test_list_claims(client: TestClient, claim_id: str) -> None:
    response = client.get("/claims")
    assert response.status_code == 200
    assert claim_id in [c["id"] for c in response.json()]


def test_claim_creation_is_audited(
    client: TestClient, db: InMemoryDatabase, claim_id: str
) -> None:
    actions = [row["action"] for row in db.list_audit_logs(claim_id)]
    assert "claim_created" in actions


def test_audit_endpoint(client: TestClient, claim_id: str) -> None:
    response = client.get(f"/claims/{claim_id}/audit")
    assert response.status_code == 200
    assert response.json()[0]["action"] == "claim_created"


def test_result_before_processing_is_empty(client: TestClient, claim_id: str) -> None:
    response = client.get(f"/claims/{claim_id}/result")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "CREATED"
    assert body["extraction"] == {}
    assert body["decision"] is None
    assert body["documents"] == []
