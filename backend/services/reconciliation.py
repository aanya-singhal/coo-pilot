"""Cross-document reconciliation, exposed in the API's shape.

Deterministic comparison only - no LLM is involved in comparing fields.

This module deliberately contains no comparison logic of its own. The
implementation lives in ``rules/reconciliation.py``; this is the adapter that
calls it and maps its output to the ``{status, matches, mismatches}`` shape
the API contract uses. Keeping one implementation means the reconcile
endpoint and the verification pipeline can never disagree.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

MATCHED = "MATCHED"
MISMATCHED = "MISMATCHED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
UNAVAILABLE = "UNAVAILABLE"


def _load_reconcile() -> Callable[..., dict[str, Any]] | None:
    try:
        from rules.reconciliation import reconcile
    except ImportError:
        logger.warning("rules.reconciliation not importable")
        return None
    return reconcile


def _field_entry(comparison: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "field": comparison.get("field"),
        "invoice": comparison.get("invoice_value"),
        "packing_list": comparison.get("packing_list_value"),
    }
    if not comparison.get("match"):
        entry["severity"] = comparison.get("severity")
        entry["note"] = comparison.get("note")
    return entry


def reconcile_documents(
    invoice: dict[str, Any] | None, packing_list: dict[str, Any] | None
) -> dict[str, Any]:
    """Compare the two documents and report matches and mismatches."""
    reconcile = _load_reconcile()
    if reconcile is None:
        return {
            "status": UNAVAILABLE,
            "matches": [],
            "mismatches": [],
            "summary": "Reconciliation module is not available.",
        }

    result = reconcile(invoice, packing_list)
    comparisons = result.get("comparisons", [])

    matches = [_field_entry(c) for c in comparisons if c.get("match")]
    mismatches = [_field_entry(c) for c in comparisons if not c.get("match")]

    # A document that is missing or whose extraction failed produces no
    # comparisons at all. That must never be reported as MATCHED - "nothing
    # was compared" is not "everything agrees".
    if result.get("status") == "INSUFFICIENT_DATA" or not comparisons:
        status = INSUFFICIENT_DATA
    elif mismatches:
        status = MISMATCHED
    else:
        status = MATCHED

    return {
        "status": status,
        "matches": matches,
        "mismatches": mismatches,
        "missing_documents": result.get("missing_documents", []),
        "summary": result.get("summary"),
    }


def documents_from_extraction(
    rows: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build ``{doc_type: data}`` from stored extracted_data rows.

    The document type comes from the ``documents`` row the uploader supplied,
    not from the extracted payload, so a model that omits or misreports
    ``doc_type`` cannot misfile a document. Rows whose extraction failed are
    skipped rather than compared as if they held real values.
    """
    doc_types = {d["id"]: d.get("doc_type") for d in documents}

    result: dict[str, Any] = {}
    for row in rows:
        data = row.get("data") or {}
        if not isinstance(data, dict) or data.get("error") or data.get("skipped"):
            continue
        doc_type = doc_types.get(row.get("document_id")) or data.get("doc_type")
        if doc_type:
            result[doc_type] = data
    return result
