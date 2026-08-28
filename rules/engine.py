"""Rules engine entry point.

``evaluate(extraction)`` is the function the backend's rules adapter locates
and calls. It composes the three stages and returns the shape the backend
stores:

    {"reconciliation": {...}, "rules": {...}, "risk": {...}, "decision": "..."}

Decision policy
---------------
``APPROVED``       documents reconcile AND the origin criterion is met.
``REJECTED``       the origin criterion was evaluated and failed.
``PENDING_REVIEW`` anything else - notably whenever origin could not be
                   evaluated, which is the norm when only an invoice and a
                   packing list are available.

A document discrepancy never auto-rejects. It routes to human review, which
is what a customs officer would do.
"""

from __future__ import annotations

from typing import Any

from rules.origin import evaluate_origin
from rules.reconciliation import reconcile
from rules.risk import score as score_risk

APPROVED = "APPROVED"
REJECTED = "REJECTED"
PENDING_REVIEW = "PENDING_REVIEW"


def _usable(document: Any) -> dict[str, Any] | None:
    """Return the document only if extraction produced real fields."""
    if not isinstance(document, dict):
        return None
    if document.get("error") or document.get("skipped"):
        return None
    return document


def _decide(reconciliation: dict, origin: dict) -> tuple[str, str]:
    """Return ``(decision, reason)``."""
    if origin.get("status") == "EVALUATED" and not origin.get("satisfied"):
        return REJECTED, (
            f"The origin criterion was not met. {origin.get('detail', '')}".strip()
        )

    if not reconciliation.get("consistent", False):
        return PENDING_REVIEW, reconciliation.get(
            "summary", "Documents could not be reconciled."
        )

    if origin.get("status") == "INSUFFICIENT_DATA":
        return PENDING_REVIEW, (
            f"{reconciliation.get('summary', '')} However, origin remains "
            f"unsubstantiated: {origin.get('detail', '')}".strip()
        )

    if origin.get("satisfied"):
        return APPROVED, (
            f"{reconciliation.get('summary', '')} {origin.get('detail', '')}".strip()
        )

    return PENDING_REVIEW, "Insufficient basis for an automated decision."


def evaluate(extraction: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one case from extracted document data."""
    extraction = extraction or {}

    invoice = _usable(extraction.get("invoice"))
    packing_list = _usable(extraction.get("packing_list"))

    extraction_errors = [
        name
        for name in ("invoice", "packing_list")
        if name in extraction and _usable(extraction.get(name)) is None
    ]

    reconciliation = reconcile(invoice, packing_list)
    origin = evaluate_origin(extraction.get("origin_declaration"))
    risk = score_risk(reconciliation, origin, extraction_errors)
    decision, reason = _decide(reconciliation, origin)

    return {
        "reconciliation": reconciliation,
        "rules": {
            "rule_applied": origin.get("criterion", "Cross-document consistency"),
            "rule_satisfied": decision == APPROVED,
            "reason": reason,
            "origin": origin,
            "citation": origin.get("citation"),
            "source_url": origin.get("source_url"),
        },
        "risk": risk,
        "decision": decision,
    }
