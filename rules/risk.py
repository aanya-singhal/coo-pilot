"""Risk scoring for triage.

This is an internal prioritisation aid, not a regulatory measure. The weights
are a deliberate policy choice of this tool and carry no statutory basis; they
exist so officers can queue the most doubtful claims first. Every contribution
is itemised so a score can always be explained.
"""

from __future__ import annotations

from typing import Any

#: Points contributed by each observation. Tune freely - they are not law.
WEIGHTS: dict[str, int] = {
    "blocking_mismatch": 30,
    "advisory_mismatch": 10,
    "missing_document": 25,
    "origin_insufficient_data": 25,
    "origin_not_satisfied": 40,
    "extraction_error": 20,
}

BANDS: tuple[tuple[int, str], ...] = ((70, "HIGH"), (35, "MEDIUM"), (0, "LOW"))


def _band(score: int) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "LOW"


def score(
    reconciliation: dict[str, Any],
    origin: dict[str, Any],
    extraction_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Produce an itemised risk score from the other modules' findings."""
    factors: list[dict[str, Any]] = []

    def add(kind: str, detail: str) -> None:
        factors.append({"factor": kind, "points": WEIGHTS[kind], "detail": detail})

    for field in reconciliation.get("blocking_mismatches", []):
        add("blocking_mismatch", f"'{field}' disagrees across the documents")
    for field in reconciliation.get("advisory_mismatches", []):
        add("advisory_mismatch", f"'{field}' is inconsistent (advisory)")
    for doc in reconciliation.get("missing_documents", []):
        add("missing_document", f"'{doc}' was not supplied")

    if origin.get("status") == "INSUFFICIENT_DATA":
        add("origin_insufficient_data", "Origin criteria could not be evaluated")
    elif not origin.get("satisfied", False):
        add("origin_not_satisfied", "Declared goods do not meet the origin criterion")

    for error in extraction_errors or []:
        add("extraction_error", f"Extraction failed for {error}")

    total = min(100, sum(f["points"] for f in factors))
    return {
        "score": total,
        "band": _band(total),
        "factors": factors,
        "basis": (
            "Internal triage score. Weights are a policy choice of this tool, "
            "not a statutory measure."
        ),
    }
