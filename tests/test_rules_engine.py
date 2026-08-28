"""Tests for the rules engine."""

import copy

import pytest

from rules.agreements import AIFTA, SAFTA_NON_LDC, get_criteria
from rules.engine import APPROVED, PENDING_REVIEW, REJECTED, evaluate
from rules.reconciliation import normalise_text, reconcile

INVOICE = {
    "doc_type": "invoice",
    "exporter": "Nilgiri Textiles Pvt Ltd",
    "product": "Cotton Bedsheets (Set)",
    "quantity": 500,
    "value": 4200.00,
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
    "hs_code": "630231",
    "fob_value": 4200.00,
    "non_originating_materials": [
        {"description": "Greige cotton fabric", "hs_code": "520811", "value": 1500.00}
    ],
}


def case(**overrides) -> dict:
    payload = {
        "invoice": copy.deepcopy(INVOICE),
        "packing_list": copy.deepcopy(PACKING_LIST),
    }
    payload.update(copy.deepcopy(overrides))
    return payload


# --- reconciliation --------------------------------------------------


def test_matching_documents_reconcile() -> None:
    result = reconcile(INVOICE, PACKING_LIST)
    assert result["consistent"] is True
    assert result["blocking_mismatches"] == []


def test_quantity_mismatch_is_blocking() -> None:
    pl = {**PACKING_LIST, "quantity": 480}
    result = reconcile(INVOICE, pl)
    assert result["consistent"] is False
    assert "quantity" in result["blocking_mismatches"]


def test_reference_mismatch_is_advisory_not_blocking() -> None:
    """A filing-convention mismatch must not read as an origin failure."""
    pl = {**PACKING_LIST, "packing_list_number": "PL-2026-0452"}
    result = reconcile(INVOICE, pl)
    assert result["consistent"] is True
    assert result["advisory_mismatches"] == ["document_reference"]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Nilgiri Textiles Pvt Ltd", "Nilgiri Textiles Private Limited"),
        ("Cotton Bedsheets (Set)", "Cotton Bedsheets Set"),
        ("ACME CO.", "Acme Company"),
    ],
)
def test_normalisation_treats_equivalent_names_as_equal(a: str, b: str) -> None:
    assert normalise_text(a) == normalise_text(b)


def test_missing_document_is_insufficient_data() -> None:
    result = reconcile(INVOICE, None)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["missing_documents"] == ["packing_list"]


# --- origin criteria -------------------------------------------------


def test_no_declaration_yields_insufficient_data_not_a_verdict() -> None:
    """Invoice + packing list alone can never establish origin."""
    result = evaluate(case())
    origin = result["rules"]["origin"]

    assert origin["status"] == "INSUFFICIENT_DATA"
    assert origin["satisfied"] is False
    assert set(origin["missing_fields"]) == {
        "hs_code",
        "fob_value",
        "non_originating_materials",
    }
    assert result["decision"] == PENDING_REVIEW


def test_satisfied_origin_is_approved() -> None:
    result = evaluate(case(origin_declaration=DECLARATION))
    value_content = result["rules"]["origin"]["value_content"]

    # (4200 - 1500) / 4200 = 64.29%, above the AIFTA 35% threshold.
    assert value_content["regional_value_content_percent"] == pytest.approx(64.29)
    assert result["decision"] == APPROVED
    assert result["rules"]["rule_satisfied"] is True


def test_value_content_below_threshold_is_rejected() -> None:
    declaration = copy.deepcopy(DECLARATION)
    declaration["non_originating_materials"][0]["value"] = 3500.00
    result = evaluate(case(origin_declaration=declaration))

    assert result["rules"]["origin"]["value_content"]["satisfied"] is False
    assert result["decision"] == REJECTED


def test_material_in_same_subheading_fails_ctsh() -> None:
    declaration = copy.deepcopy(DECLARATION)
    declaration["non_originating_materials"][0]["hs_code"] = "6302.31"
    result = evaluate(case(origin_declaration=declaration))

    ctc = result["rules"]["origin"]["change_in_tariff_classification"]
    assert ctc["satisfied"] is False
    assert result["decision"] == REJECTED


def test_agreement_thresholds_differ() -> None:
    """35.71% clears AIFTA's 35% but not SAFTA's 40%."""
    declaration = copy.deepcopy(DECLARATION)
    declaration["non_originating_materials"][0]["value"] = 2700.00

    aifta = evaluate(case(origin_declaration={**declaration, "agreement": "AIFTA"}))
    safta = evaluate(case(origin_declaration={**declaration, "agreement": "SAFTA"}))

    assert aifta["decision"] == APPROVED
    assert safta["decision"] == REJECTED


def test_wholly_obtained_skips_value_and_ctc_tests() -> None:
    result = evaluate(
        case(origin_declaration={"agreement": "AIFTA", "wholly_obtained": True})
    )
    assert result["decision"] == APPROVED
    assert "value_content" not in result["rules"]["origin"]


def test_unvalued_material_is_reported_not_silently_dropped() -> None:
    declaration = copy.deepcopy(DECLARATION)
    declaration["non_originating_materials"].append(
        {"description": "Dyestuff", "hs_code": "320412"}
    )
    origin = evaluate(case(origin_declaration=declaration))["rules"]["origin"]
    assert origin["value_content"]["materials_without_declared_value"] == ["Dyestuff"]


def test_material_without_hs_code_fails_ctc() -> None:
    declaration = copy.deepcopy(DECLARATION)
    declaration["non_originating_materials"].append(
        {"description": "Unclassified input", "value": 10.0}
    )
    ctc = evaluate(case(origin_declaration=declaration))["rules"]["origin"][
        "change_in_tariff_classification"
    ]
    assert ctc["satisfied"] is False
    assert ctc["materials_without_hs_code"] == ["Unclassified input"]


# --- decision policy -------------------------------------------------


def test_document_mismatch_routes_to_review_never_auto_rejects() -> None:
    payload = case(origin_declaration=DECLARATION)
    payload["packing_list"]["quantity"] = 480
    assert evaluate(payload)["decision"] == PENDING_REVIEW


def test_extraction_error_is_handled() -> None:
    payload = case()
    payload["invoice"] = {"error": "Gemini API call failed"}
    result = evaluate(payload)

    assert result["decision"] == PENDING_REVIEW
    assert result["reconciliation"]["status"] == "INSUFFICIENT_DATA"


def test_empty_input_does_not_crash() -> None:
    assert evaluate({})["decision"] == PENDING_REVIEW


# --- risk ------------------------------------------------------------


def test_risk_rises_with_findings() -> None:
    clean = evaluate(case(origin_declaration=DECLARATION))["risk"]
    payload = case(origin_declaration=DECLARATION)
    payload["packing_list"]["quantity"] = 480
    messy = evaluate(payload)["risk"]

    assert clean["score"] == 0
    assert messy["score"] > clean["score"]
    assert messy["factors"]


# --- agreement registry ----------------------------------------------


def test_registry_lookup_is_case_insensitive() -> None:
    assert get_criteria("aifta") is AIFTA
    assert get_criteria("SAFTA") is SAFTA_NON_LDC
    assert get_criteria("nonsense") is None


def test_every_agreement_carries_a_citation() -> None:
    """A threshold without a source is not usable by a reviewing officer."""
    for criteria in (AIFTA, SAFTA_NON_LDC):
        assert criteria.citation
        assert criteria.source_url.startswith("https://")
