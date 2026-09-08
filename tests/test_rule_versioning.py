"""Tests for versioned rules of origin.

The property under test is that amending a rule never changes a decision
already taken: a case assessed under version 1 must still evaluate the same
way after version 2 supersedes it.
"""

from __future__ import annotations

import pytest

from rules import agreements
from rules.agreements import AIFTA, ChangeInTariffClassification, get_criteria
from rules.engine import evaluate

INVOICE = {
    "doc_type": "invoice",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets (Set)",
    "quantity": 500,
    "value": 4200.0,
    "invoice_number": "INV-2026-0451",
}
PACKING_LIST = {
    "doc_type": "packing_list",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets (Set)",
    "quantity": 500,
    "packages": 25,
    "packing_list_number": "PL-2026-0451",
}
DECLARATION = {
    "agreement": "AIFTA",
    "hs_code": "6302.21",
    "fob_value": 4200.0,
    "wholly_obtained": False,
    "non_originating_materials": [
        {"description": "Raw cotton yarn", "hs_code": "5205.11", "value": 2400.0}
    ],
}


@pytest.fixture(autouse=True)
def restore_registry():
    """Amendments are global, so snapshot and restore around each test."""
    snapshot = {code: list(v) for code, v in agreements.REGISTRY.items()}
    yield
    agreements.REGISTRY.clear()
    agreements.REGISTRY.update(snapshot)


def _case(declaration: dict) -> dict:
    return evaluate(
        {
            "invoice": INVOICE,
            "packing_list": PACKING_LIST,
            "origin_declaration": declaration,
        }
    )


def test_rules_start_at_version_one() -> None:
    criteria = get_criteria("AIFTA")

    assert criteria is not None
    assert criteria.version == 1
    assert criteria is AIFTA


def test_amending_creates_a_new_version_and_keeps_the_old() -> None:
    agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Threshold raised to 45%.",
    )

    assert get_criteria("AIFTA").version == 2
    assert get_criteria("AIFTA").value_content_min_percent == 45.0
    assert get_criteria("AIFTA", 1).value_content_min_percent == 35.0
    assert [c.version for c in agreements.list_versions("AIFTA")] == [1, 2]


def test_new_cases_use_the_current_version() -> None:
    before = _case(DECLARATION)
    assert before["decision"] == "APPROVED"
    assert before["rules"]["origin"]["rule_version"] == 1

    agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Threshold raised to 45%.",
    )
    after = _case(DECLARATION)

    assert after["rules"]["origin"]["rule_version"] == 2
    assert after["rules"]["origin"]["value_content"]["threshold_percent"] == 45.0
    assert after["decision"] == "REJECTED"


def test_a_pinned_version_keeps_an_old_decision_explainable() -> None:
    """The same documents, judged under the rule in force at the time."""
    agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Threshold raised to 45%.",
    )
    old = _case({**DECLARATION, "rule_version": 1})

    assert old["rules"]["origin"]["rule_version"] == 1
    assert old["rules"]["origin"]["value_content"]["threshold_percent"] == 35.0
    assert old["decision"] == "APPROVED"


def test_every_evaluation_reports_its_rule_version() -> None:
    origin = _case(DECLARATION)["rules"]["origin"]

    assert origin["rule_version"] == 1
    assert origin["effective_from"] == "2009-12-31"


def test_insufficient_data_still_reports_a_version() -> None:
    """An officer needs to know which rule could not be evaluated."""
    origin = _case({})["rules"]["origin"]

    assert origin["status"] == "INSUFFICIENT_DATA"
    assert origin["rule_version"] == 1


def test_wholly_obtained_reports_a_version() -> None:
    origin = _case({"agreement": "AIFTA", "wholly_obtained": True})["rules"]["origin"]

    assert origin["satisfied"] is True
    assert origin["rule_version"] == 1


def test_unknown_pinned_version_falls_back_to_current() -> None:
    """A stored version we no longer recognise must not crash a review."""
    origin = _case({**DECLARATION, "rule_version": 99})["rules"]["origin"]

    assert origin["rule_version"] == 1


def test_amending_can_change_the_tariff_shift_rule() -> None:
    agreements.amend(
        "AIFTA",
        ctc_rule=ChangeInTariffClassification.CTH,
        effective_from="2026-10-01",
        amendment_note="Tariff shift relaxed to heading level.",
    )
    current = get_criteria("AIFTA")

    assert current.ctc_rule is ChangeInTariffClassification.CTH
    assert current.ctc_digits == 4
    assert current.value_content_min_percent == 35.0  # unchanged fields carry over


def test_versions_must_move_forward() -> None:
    from dataclasses import replace

    with pytest.raises(ValueError):
        agreements.register_version(replace(AIFTA, version=1))


def test_amending_an_unknown_agreement_is_rejected() -> None:
    with pytest.raises(ValueError):
        agreements.amend(
            "NONSENSE", effective_from="2026-10-01", amendment_note="x"
        )


def test_amendment_note_is_recorded() -> None:
    agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Threshold raised by gazette notification.",
    )

    assert "gazette" in get_criteria("AIFTA").amendment_note
    assert get_criteria("AIFTA").effective_from == "2026-10-01"