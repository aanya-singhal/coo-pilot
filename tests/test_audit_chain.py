"""Tests for the tamper-evident audit log.

These exercise the chain end to end through the database layer rather than
calling the hashing helpers in isolation, so they cover the wiring as well as
the arithmetic.
"""

from __future__ import annotations

from backend.database import InMemoryDatabase
from backend.services import hashing

TRAIL = [
    ("claim_created", {"claim_id": "c1"}),
    ("extraction_completed", {"fields": 6}),
    ("processing_completed", {"decision": "APPROVED"}),
    ("approved", {"reviewer": "Officer A", "comments": "Documents consistent."}),
]


def _seed(db: InMemoryDatabase, count: int = 4) -> None:
    for action, details in TRAIL[:count]:
        db.write_audit_log(claim_id="c1", action=action, details=details)


def test_every_entry_is_hashed_and_linked() -> None:
    db = InMemoryDatabase()
    _seed(db)
    rows = db.list_all_audit_logs()

    assert all(r["entry_hash"] for r in rows)
    assert rows[0]["previous_entry_hash"] is None
    for earlier, later in zip(rows, rows[1:]):
        assert later["previous_entry_hash"] == earlier["entry_hash"]


def test_untouched_chain_verifies() -> None:
    db = InMemoryDatabase()
    _seed(db)

    valid, broken = hashing.verify_chain(db.list_all_audit_logs())
    report = hashing.verify_chain_report(db.list_all_audit_logs())

    assert valid is True and broken is None
    assert report["intact"] is True
    assert report["checked"] == 4
    assert all(e["status"] == "ok" for e in report["entries"])


def test_editing_an_entry_is_detected() -> None:
    db = InMemoryDatabase()
    _seed(db)
    db.audit[3]["details"]["comments"] = "Approved without review."

    valid, broken = hashing.verify_chain(db.list_all_audit_logs())
    report = hashing.verify_chain_report(db.list_all_audit_logs())

    assert valid is False and broken == 3
    assert report["broken_at_index"] == 3
    assert "altered" in report["reason"]


def test_editing_pinpoints_the_altered_entry() -> None:
    """The report names the row that changed rather than flagging every row
    after it, so an auditor sees exactly where to look."""
    db = InMemoryDatabase()
    _seed(db)
    db.audit[1]["action"] = "extraction_failed"

    report = hashing.verify_chain_report(db.list_all_audit_logs())

    assert [e["status"] for e in report["entries"]] == ["ok", "broken", "ok", "ok"]
    assert report["broken_at_index"] == 1


def test_rehashing_an_edited_entry_still_breaks_the_next_link() -> None:
    """An attacker who edits a row and recomputes that row's own hash is
    still caught, because the next row records the original hash."""
    db = InMemoryDatabase()
    _seed(db)
    row = db.audit[1]
    row["action"] = "extraction_failed"
    row["entry_hash"] = hashing.compute_entry_hash(
        entry_id=row["id"],
        timestamp=str(row["created_at"]),
        action=row["action"],
        claim_id=row.get("claim_id"),
        payload_hash=hashing.compute_payload_hash(row["details"]),
        previous_entry_hash=row["previous_entry_hash"],
    )

    report = hashing.verify_chain_report(db.list_all_audit_logs())

    assert report["intact"] is False
    assert report["broken_at_index"] == 2
    assert "removed or reordered" in report["reason"]


def test_deleting_an_entry_is_detected() -> None:
    db = InMemoryDatabase()
    _seed(db)
    del db.audit[1]

    assert hashing.verify_chain(db.list_all_audit_logs())[0] is False
    assert hashing.verify_chain_report(db.list_all_audit_logs())["intact"] is False


def test_reordering_entries_is_detected() -> None:
    db = InMemoryDatabase()
    _seed(db)
    db.audit[1], db.audit[2] = db.audit[2], db.audit[1]

    assert hashing.verify_chain_report(db.list_all_audit_logs())["intact"] is False


def test_empty_log_is_intact() -> None:
    report = hashing.verify_chain_report([])

    assert report["intact"] is True
    assert report["checked"] == 0


def test_legacy_unhashed_rows_are_skipped_not_flagged() -> None:
    """Rows written before hashing existed sit outside the chain."""
    db = InMemoryDatabase()
    _seed(db, count=2)
    db.audit.insert(
        0,
        {
            "id": "legacy",
            "claim_id": "c1",
            "action": "claim_created",
            "details": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    report = hashing.verify_chain_report(db.list_all_audit_logs())

    assert report["unhashed"] == 1
    assert report["intact"] is True


def test_details_key_order_does_not_change_the_hash() -> None:
    a = hashing.compute_payload_hash({"x": 1, "y": 2})
    b = hashing.compute_payload_hash({"y": 2, "x": 1})

    assert a == b


def test_timestamp_reformatting_is_not_treated_as_tampering() -> None:
    """Postgres may return '...Z' where we wrote '...+00:00'. Canonicalising
    before hashing keeps that from looking like an edit."""
    base = dict(
        entry_id="e1",
        action="approved",
        claim_id="c1",
        payload_hash=hashing.compute_payload_hash({}),
        previous_entry_hash=None,
    )
    with_offset = hashing.compute_entry_hash(timestamp="2026-01-01T00:00:00+00:00", **base)
    with_zulu = hashing.compute_entry_hash(timestamp="2026-01-01T00:00:00Z", **base)

    assert with_offset == with_zulu


def test_verify_endpoint_returns_a_report(client) -> None:
    response = client.get("/claims/audit/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["intact"] is True
    assert "entries" in body