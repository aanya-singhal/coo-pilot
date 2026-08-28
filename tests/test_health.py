from fastapi.testclient import TestClient


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "CoO-PILOT Backend"


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["supabase_configured"], bool)


def test_json_responses_declare_utf8(client: TestClient) -> None:
    """Origin criteria contain "≥"; without a charset browsers mangle it."""
    response = client.get("/health")
    assert "charset=utf-8" in response.headers["content-type"].lower()
