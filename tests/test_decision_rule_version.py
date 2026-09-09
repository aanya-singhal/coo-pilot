"""Tests for decisions recording the rule version that produced them.

Reviewing a decision months later has to show the rule as it stood on the
day it was taken. If the review silently used today's rule, an approval made
under a 35% threshold would appear to have been made under 45%, which is
both wrong and unauditable.
"""

from __future__ import annotations

import pytest

from rules import agreements

AMENDMENT = {
    "value_content_min_percent": 45.0,
    "effective_from": "2026-10-01",
    "amendment_note": "Threshold raised by gazette notification.",
}


@pytest.fixture(autouse=True)
def restore_registry():
    snapshot = {code: list(v) for code, v in agreements.REGISTRY.items()}
    yield
    agreements.REGISTRY.clear()
    agreements.REGISTRY.update(snapshot)


def _decided_claim(db, claim_id: str = "c1", version: int = 1) -> None:
    """Store a decision as the pipeline would, stamped with a rule version."""
    criteria = agreements.get_criteria("AIFTA", version)
    assert criteria is not None
    db.save_verification_result(
        claim_id=claim_id,
        decision="APPROVED",
        result={
            "decision": "APPROVED",
            "applied_rule": {
                "agreement": "AIFTA",
                "version": criteria.version,
                "effective_from": criteria.effective_from,
                "criterion": criteria.describe(),
            },
        },
    )


def test_a_decision_reports_the_rule_that_produced_it(client, db) -> None:
    _decided_claim(db)

    body = client.get("/claims/c1/decision").json()

    assert body["decision"] == "APPROVED"
    assert body["applied_rule"]["version"] == 1
    assert body["rule_at_decision"]["value_content_min_percent"] == 35.0
    assert body["rule_superseded"] is False


def test_an_old_decision_is_explained_under_its_original_version(client, db) -> None:
    _decided_claim(db)
    client.post("/rules/AIFTA/amend", json=AMENDMENT)

    body = client.get("/claims/c1/decision").json()

    # judged under v1's 35%, even though v2's 45% is now in force
    assert body["rule_at_decision"]["version"] == 1
    assert body["rule_at_decision"]["value_content_min_percent"] == 35.0
    assert body["rule_now"]["version"] == 2
    assert body["rule_now"]["value_content_min_percent"] == 45.0
    assert body["rule_superseded"] is True
    assert "remains valid" in body["note"]


def test_a_decision_under_the_current_rule_is_not_flagged(client, db) -> None:
    client.post("/rules/AIFTA/amend", json=AMENDMENT)
    _decided_claim(db, version=2)

    body = client.get("/claims/c1/decision").json()

    assert body["rule_at_decision"]["version"] == 2
    assert body["rule_superseded"] is False
    assert "still current" in body["note"]


def test_missing_decision_is_404(client) -> None:
    assert client.get("/claims/unknown/decision").status_code == 404


def test_a_decision_without_a_stamp_still_returns(client, db) -> None:
    """Decisions recorded before versioning existed must not break review."""
    db.save_verification_result(
        claim_id="legacy", decision="APPROVED", result={"decision": "APPROVED"}
    )

    body = client.get("/claims/legacy/decision").json()

    assert body["decision"] == "APPROVED"
    assert body["rule_at_decision"] is None
    assert body["rule_superseded"] is False


def test_an_unknown_stored_version_does_not_break_review(client, db) -> None:
    """A version we can no longer resolve must degrade, not error."""
    db.save_verification_result(
        claim_id="c1",
        decision="APPROVED",
        result={"decision": "APPROVED", "applied_rule": {"agreement": "AIFTA", "version": 99}},
    )

    response = client.get("/claims/c1/decision")

    assert response.status_code == 200
    assert response.json()["rule_at_decision"] is None