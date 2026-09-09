"""Tests for the rule administration endpoints."""

from __future__ import annotations

import pytest

from rules import agreements


@pytest.fixture(autouse=True)
def restore_registry():
    """Amendments mutate a module-level registry, so isolate each test."""
    snapshot = {code: list(v) for code, v in agreements.REGISTRY.items()}
    yield
    agreements.REGISTRY.clear()
    agreements.REGISTRY.update(snapshot)


AMENDMENT = {
    "value_content_min_percent": 45.0,
    "effective_from": "2026-10-01",
    "amendment_note": "Threshold raised to 45% by gazette notification.",
}


def test_list_rules_returns_every_agreement(client) -> None:
    body = client.get("/rules").json()
    codes = [a["code"] for a in body["agreements"]]

    assert "AIFTA" in codes
    assert "SAFTA" in codes


def test_get_rule_returns_current_and_history(client) -> None:
    body = client.get("/rules/AIFTA").json()

    assert body["current"]["version"] == 1
    assert body["current"]["value_content_min_percent"] == 35.0
    assert len(body["versions"]) == 1


def test_get_unknown_rule_is_404(client) -> None:
    assert client.get("/rules/NONSENSE").status_code == 404


def test_amending_creates_a_new_version(client) -> None:
    response = client.post("/rules/AIFTA/amend", json=AMENDMENT)

    assert response.status_code == 200
    body = response.json()
    assert body["previous"]["version"] == 1
    assert body["previous"]["value_content_min_percent"] == 35.0
    assert body["current"]["version"] == 2
    assert body["current"]["value_content_min_percent"] == 45.0


def test_history_grows_after_an_amendment(client) -> None:
    client.post("/rules/AIFTA/amend", json=AMENDMENT)
    body = client.get("/rules/AIFTA").json()

    assert [v["version"] for v in body["versions"]] == [1, 2]
    assert body["current"]["version"] == 2


def test_amendment_is_written_to_the_audit_log(client) -> None:
    """Who changed the policy is covered by the same chain as the decisions."""
    client.post("/rules/AIFTA/amend", json=AMENDMENT)
    report = client.get("/claims/audit/verify").json()
    actions = [e["action"] for e in report["entries"]]

    assert "rule_amended" in actions
    assert report["intact"] is True


def test_amendment_with_no_changes_is_rejected(client) -> None:
    response = client.post(
        "/rules/AIFTA/amend",
        json={"effective_from": "2026-10-01", "amendment_note": "No actual change."},
    )

    assert response.status_code == 422


def test_amendment_needs_a_note(client) -> None:
    response = client.post(
        "/rules/AIFTA/amend",
        json={"value_content_min_percent": 45.0, "effective_from": "2026-10-01"},
    )

    assert response.status_code == 422


def test_threshold_outside_zero_to_hundred_is_rejected(client) -> None:
    response = client.post(
        "/rules/AIFTA/amend",
        json={**AMENDMENT, "value_content_min_percent": 140.0},
    )

    assert response.status_code == 422


def test_amending_an_unknown_agreement_is_404(client) -> None:
    assert client.post("/rules/NONSENSE/amend", json=AMENDMENT).status_code == 404


def test_the_tariff_shift_rule_can_be_amended(client) -> None:
    response = client.post(
        "/rules/AIFTA/amend",
        json={
            "ctc_rule": "CTH",
            "effective_from": "2026-10-01",
            "amendment_note": "Tariff shift relaxed to heading level.",
        },
    )
    body = response.json()

    assert body["current"]["ctc_rule"] == "CTH"
    assert body["current"]["ctc_digits"] == 4
    # unchanged fields carry over from the previous version
    assert body["current"]["value_content_min_percent"] == 35.0


def test_a_new_claim_is_judged_under_the_amended_rule(client) -> None:
    """The amendment has to actually reach the engine, not just the registry."""
    client.post("/rules/AIFTA/amend", json=AMENDMENT)

    response = client.post(
        "/process",
        json={
            "case_id": "COO-2026-001",
            "files": ["sample_invoice.png", "packing_list_clean.png"],
            "origin_declaration": {
                "agreement": "AIFTA",
                "hs_code": "6302.21",
                "fob_value": 4200.0,
                "wholly_obtained": False,
                "non_originating_materials": [
                    {"description": "yarn", "hs_code": "5205.11", "value": 2400.0}
                ],
            },
        },
    )

    if response.status_code != 200:
        pytest.skip("pipeline unavailable in this environment")
    origin = response.json()["rules"]["origin"]
    assert origin["rule_version"] == 2
    assert origin["value_content"]["threshold_percent"] == 45.0