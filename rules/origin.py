"""Rules-of-origin evaluation: value content and change in tariff classification.

What this module will and will not do
------------------------------------
It evaluates the general rule of origin for an agreement when it is given the
inputs that rule needs. It does NOT estimate, infer, or default those inputs.

An invoice and a packing list do not carry them. Determining origin requires a
cost statement - the FOB value plus the value and classification of every
non-originating material. That is precisely the information CAROTAR 2020
requires an importer to hold in Form I. When it is absent this module returns
``INSUFFICIENT_DATA`` and names the missing fields, which is the real customs
outcome: the officer requests Form I information rather than assuming a result.

Supply the inputs via an ``origin_declaration`` entry in the payload::

    {
      "agreement": "AIFTA",
      "hs_code": "630231",
      "fob_value": 4200.00,
      "wholly_obtained": false,
      "non_originating_materials": [
        {"description": "Greige cotton fabric", "hs_code": "520811", "value": 1500.00}
      ]
    }
"""

from __future__ import annotations

from typing import Any

from rules.agreements import DEFAULT_AGREEMENT, OriginCriteria, get_criteria

#: Fields required to evaluate the general rule, per CAROTAR 2020 Form I.
REQUIRED_FIELDS: tuple[str, ...] = ("hs_code", "fob_value", "non_originating_materials")


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _insufficient(
    criteria: OriginCriteria, missing: list[str], detail: str
) -> dict[str, Any]:
    return {
        "status": "INSUFFICIENT_DATA",
        "satisfied": False,
        "agreement": criteria.code,
        "criterion": criteria.describe(),
        "citation": criteria.citation,
        "source_url": criteria.source_url,
        "missing_fields": missing,
        "detail": detail,
        "required_action": (
            "Obtain the origin cost statement (CAROTAR 2020 Form I) from the "
            "importer before a preferential claim can be substantiated."
        ),
    }


def _evaluate_value_content(
    criteria: OriginCriteria, fob_value: float, materials: list[dict]
) -> dict[str, Any]:
    """Indirect (build-down) method: (FOB - non-originating value) / FOB."""
    non_originating = 0.0
    unvalued: list[str] = []
    for material in materials:
        value = _to_float(material.get("value"))
        if value is None:
            unvalued.append(str(material.get("description") or material.get("hs_code")))
        else:
            non_originating += value

    percent = (fob_value - non_originating) / fob_value * 100.0
    satisfied = percent >= criteria.value_content_min_percent

    return {
        "method": "indirect (build-down)",
        "regional_value_content_percent": round(percent, 2),
        "threshold_percent": criteria.value_content_min_percent,
        "non_originating_value": round(non_originating, 2),
        "fob_value": fob_value,
        "satisfied": satisfied,
        "materials_without_declared_value": unvalued,
        "note": (
            f"Regional value content {percent:.2f}% against a "
            f"{criteria.value_content_min_percent}% threshold."
            + (
                f" {len(unvalued)} material(s) carry no declared value and were "
                "treated as originating, which overstates the result."
                if unvalued
                else ""
            )
        ),
    }


def _evaluate_ctc(
    criteria: OriginCriteria, hs_code: str, materials: list[dict]
) -> dict[str, Any]:
    """Every non-originating material must change classification at the required level."""
    digits = criteria.ctc_digits
    product_prefix = str(hs_code).replace(".", "").strip()[:digits]

    failures: list[dict[str, Any]] = []
    unclassified: list[str] = []
    for material in materials:
        code = str(material.get("hs_code") or "").replace(".", "").strip()
        if not code:
            unclassified.append(str(material.get("description") or "unnamed material"))
            continue
        if code[:digits] == product_prefix:
            failures.append(
                {
                    "description": material.get("description"),
                    "hs_code": code,
                    "reason": (
                        f"Shares the product's {digits}-digit classification "
                        f"'{product_prefix}', so no {criteria.ctc_rule.value} occurs."
                    ),
                }
            )

    satisfied = not failures and not unclassified
    if unclassified:
        note = (
            f"{len(unclassified)} non-originating material(s) carry no HS code, "
            f"so {criteria.ctc_rule.value} cannot be established."
        )
    elif failures:
        note = (
            f"{len(failures)} non-originating material(s) do not undergo the "
            f"required {criteria.ctc_rule.value}."
        )
    else:
        note = (
            f"All non-originating materials change classification at the "
            f"{digits}-digit level."
        )

    return {
        "rule": criteria.ctc_rule.value,
        "digits": digits,
        "product_hs_prefix": product_prefix,
        "satisfied": satisfied,
        "failures": failures,
        "materials_without_hs_code": unclassified,
        "note": note,
    }


def evaluate_origin(declaration: dict[str, Any] | None) -> dict[str, Any]:
    """Evaluate the general rule of origin for the claimed agreement."""
    declaration = declaration or {}
    criteria = get_criteria(declaration.get("agreement")) or get_criteria(
        DEFAULT_AGREEMENT
    )
    assert criteria is not None  # DEFAULT_AGREEMENT is always registered

    if not declaration:
        return _insufficient(
            criteria,
            list(REQUIRED_FIELDS),
            "No origin declaration was supplied. An invoice and packing list "
            "alone cannot establish origin.",
        )

    # Wholly obtained goods satisfy origin without a value/CTC test.
    if declaration.get("wholly_obtained") is True:
        return {
            "status": "EVALUATED",
            "satisfied": True,
            "agreement": criteria.code,
            "criterion": "Wholly obtained or produced in the exporting party",
            "citation": criteria.citation,
            "source_url": criteria.source_url,
            "detail": (
                "Declared wholly obtained, so the value-content and tariff-shift "
                "tests do not apply. The wholly-obtained claim itself remains "
                "subject to verification."
            ),
        }

    missing = [f for f in REQUIRED_FIELDS if declaration.get(f) in (None, "", [])]
    fob_value = _to_float(declaration.get("fob_value"))
    if fob_value is not None and fob_value <= 0 and "fob_value" not in missing:
        missing.append("fob_value")
    if missing:
        return _insufficient(
            criteria,
            missing,
            f"Origin cannot be determined without: {', '.join(missing)}.",
        )

    materials = declaration.get("non_originating_materials") or []
    assert fob_value is not None

    value_content = _evaluate_value_content(criteria, fob_value, materials)
    ctc = _evaluate_ctc(criteria, str(declaration["hs_code"]), materials)

    if criteria.requires_both:
        satisfied = value_content["satisfied"] and ctc["satisfied"]
    else:
        satisfied = value_content["satisfied"] or ctc["satisfied"]

    reasons = [part["note"] for part in (value_content, ctc)]
    return {
        "status": "EVALUATED",
        "satisfied": satisfied,
        "agreement": criteria.code,
        "criterion": criteria.describe(),
        "citation": criteria.citation,
        "source_url": criteria.source_url,
        "value_content": value_content,
        "change_in_tariff_classification": ctc,
        "detail": " ".join(reasons),
    }
