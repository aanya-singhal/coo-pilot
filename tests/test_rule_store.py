"""Tests for rule version persistence.

The property under test: an amendment must survive a restart. If the
registry comes back knowing only version 1, a decision taken under version 2
becomes unexplainable, which defeats the point of versioning it.
"""

from __future__ import annotations

import pytest

from backend.database import InMemoryDatabase
from backend.services import rule_store
from rules import agreements
from rules.agreements import ChangeInTariffClassification


@pytest.fixture(autouse=True)
def restore_registry():
    snapshot = {code: list(v) for code, v in agreements.REGISTRY.items()}
    yield
    agreements.REGISTRY.clear()
    agreements.REGISTRY.update(snapshot)


def _wipe_registry_to_code_defaults() -> None:
    """Simulate a restart: only versions defined in code remain."""
    for code, versions in agreements.REGISTRY.items():
        agreements.REGISTRY[code] = [v for v in versions if v.version == 1]


def test_a_version_survives_a_round_trip() -> None:
    original = agreements.get_criteria("AIFTA")
    row = rule_store.to_row(original)
    rebuilt = rule_store.from_row(row)

    assert rebuilt == original


def test_ctc_rule_survives_serialisation() -> None:
    """The enum has to come back as an enum, not a bare string."""
    row = rule_store.to_row(agreements.get_criteria("AIFTA"))

    assert row["ctc_rule"] == "CTSH"
    assert rule_store.from_row(row).ctc_rule is ChangeInTariffClassification.CTSH


def test_an_amendment_is_restored_after_a_restart() -> None:
    db = InMemoryDatabase()
    amended = agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Raised by gazette notification.",
    )
    rule_store.persist(db, amended)

    _wipe_registry_to_code_defaults()
    assert agreements.get_criteria("AIFTA").version == 1  # restart happened

    restored = rule_store.restore(db)

    assert restored == 1
    current = agreements.get_criteria("AIFTA")
    assert current.version == 2
    assert current.value_content_min_percent == 45.0
    assert current.effective_from == "2026-10-01"


def test_the_superseded_version_is_still_available_after_a_restart() -> None:
    db = InMemoryDatabase()
    rule_store.persist(
        db,
        agreements.amend(
            "AIFTA",
            value_content_min_percent=45.0,
            effective_from="2026-10-01",
            amendment_note="Raised.",
        ),
    )
    _wipe_registry_to_code_defaults()
    rule_store.restore(db)

    assert agreements.get_criteria("AIFTA", 1).value_content_min_percent == 35.0


def test_restore_is_safe_to_run_twice() -> None:
    """Startup may run more than once in tests and reloads."""
    db = InMemoryDatabase()
    rule_store.persist(
        db,
        agreements.amend(
            "AIFTA",
            value_content_min_percent=45.0,
            effective_from="2026-10-01",
            amendment_note="Raised.",
        ),
    )
    _wipe_registry_to_code_defaults()

    first = rule_store.restore(db)
    second = rule_store.restore(db)

    assert first == 1
    assert second == 0
    assert [c.version for c in agreements.list_versions("AIFTA")] == [1, 2]


def test_restore_on_an_empty_database_changes_nothing() -> None:
    assert rule_store.restore(InMemoryDatabase()) == 0
    assert agreements.get_criteria("AIFTA").version == 1


def test_several_amendments_restore_in_order() -> None:
    db = InMemoryDatabase()
    for pct, version_date in ((40.0, "2026-10-01"), (45.0, "2027-01-01")):
        rule_store.persist(
            db,
            agreements.amend(
                "AIFTA",
                value_content_min_percent=pct,
                effective_from=version_date,
                amendment_note=f"Raised to {pct}%.",
            ),
        )
    _wipe_registry_to_code_defaults()

    assert rule_store.restore(db) == 2
    assert [c.version for c in agreements.list_versions("AIFTA")] == [1, 2, 3]
    assert agreements.get_criteria("AIFTA").value_content_min_percent == 45.0


def test_an_unreadable_row_is_skipped_not_fatal() -> None:
    """One bad row must not stop the service from starting."""
    db = InMemoryDatabase()
    db.save_rule_version(criteria={"code": "AIFTA", "version": "not-a-number"})

    assert rule_store.restore(db) == 0
    assert agreements.get_criteria("AIFTA").version == 1


def test_a_storage_read_failure_does_not_break_startup() -> None:
    class Broken(InMemoryDatabase):
        def list_rule_versions(self):  # type: ignore[override]
            raise RuntimeError("storage unavailable")

    assert rule_store.restore(Broken()) == 0


def test_amending_through_the_api_persists_the_version(client, db) -> None:
    response = client.post(
        "/rules/AIFTA/amend",
        json={
            "value_content_min_percent": 45.0,
            "effective_from": "2026-10-01",
            "amendment_note": "Raised by gazette notification.",
        },
    )

    assert response.status_code == 200
    stored = db.list_rule_versions()
    assert any(int(r["version"]) == 2 for r in stored)