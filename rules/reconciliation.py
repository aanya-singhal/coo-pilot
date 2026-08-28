"""Cross-document reconciliation: does the invoice agree with the packing list?

This is mechanical comparison of fields that both documents carry. It makes
no origin determination - that is ``rules/origin.py``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

#: Corporate suffixes ignored when comparing party names.
_COMPANY_SUFFIXES = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|incorporated|co|company|corp|corporation)\b"
)
_PUNCTUATION = re.compile(r"[.,'\"&/()-]")
_WHITESPACE = re.compile(r"\s+")

#: Relative tolerance for quantity comparison, to absorb float noise only.
QUANTITY_TOLERANCE = 1e-6

#: Trailing serial in a document reference, e.g. "INV-2026-0451" -> "0451".
_SERIAL = re.compile(r"(\d+)\s*$")


def normalise_text(value: Any) -> str:
    """Lower-case, strip punctuation and corporate suffixes, collapse spaces."""
    text = str(value or "").lower()
    text = _PUNCTUATION.sub(" ", text)
    text = _COMPANY_SUFFIXES.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class FieldComparison:
    """One field compared across both documents."""

    field: str
    invoice_value: Any
    packing_list_value: Any
    match: bool
    severity: str  # "blocking" | "advisory"
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compare_party(invoice: dict, packing_list: dict) -> FieldComparison:
    a, b = invoice.get("exporter"), packing_list.get("exporter")
    match = bool(a) and bool(b) and normalise_text(a) == normalise_text(b)
    return FieldComparison(
        field="exporter",
        invoice_value=a,
        packing_list_value=b,
        match=match,
        severity="blocking",
        note=(
            "Exporter matches across both documents."
            if match
            else "Exporter differs between the invoice and the packing list."
        ),
    )


def _compare_product(invoice: dict, packing_list: dict) -> FieldComparison:
    a, b = invoice.get("product"), packing_list.get("product")
    match = bool(a) and bool(b) and normalise_text(a) == normalise_text(b)
    return FieldComparison(
        field="product",
        invoice_value=a,
        packing_list_value=b,
        match=match,
        severity="blocking",
        note=(
            "Product description matches."
            if match
            else "Product description differs between the two documents."
        ),
    )


def _compare_quantity(invoice: dict, packing_list: dict) -> FieldComparison:
    a, b = _to_float(invoice.get("quantity")), _to_float(packing_list.get("quantity"))
    if a is None or b is None:
        match, note = False, "Quantity missing or unreadable on at least one document."
    else:
        match = abs(a - b) <= QUANTITY_TOLERANCE * max(1.0, abs(a), abs(b))
        note = (
            "Quantities agree."
            if match
            else f"Invoice states {a:g} against packing list {b:g} — a difference of {abs(a - b):g}."
        )
    return FieldComparison(
        field="quantity",
        invoice_value=invoice.get("quantity"),
        packing_list_value=packing_list.get("quantity"),
        match=match,
        severity="blocking",
        note=note,
    )


def _compare_reference(invoice: dict, packing_list: dict) -> FieldComparison:
    """Advisory only: many exporters share a serial across paired documents.

    This is a filing convention, not a rule of origin, so a mismatch is
    flagged for attention rather than treated as disqualifying.
    """
    a = str(invoice.get("invoice_number") or "")
    b = str(packing_list.get("packing_list_number") or "")
    sa, sb = _SERIAL.search(a), _SERIAL.search(b)
    match = bool(sa and sb and sa.group(1) == sb.group(1))
    return FieldComparison(
        field="document_reference",
        invoice_value=a or None,
        packing_list_value=b or None,
        match=match,
        severity="advisory",
        note=(
            "Document references share a common serial."
            if match
            else (
                f"Packing list reference '{b}' does not correspond to invoice "
                f"'{a}'. This is a filing convention, not an origin criterion."
            )
        ),
    )


def reconcile(invoice: dict | None, packing_list: dict | None) -> dict[str, Any]:
    """Compare the two documents field by field."""
    if not invoice or not packing_list:
        missing = [
            name
            for name, doc in (("invoice", invoice), ("packing_list", packing_list))
            if not doc
        ]
        return {
            "status": "INSUFFICIENT_DATA",
            "consistent": False,
            "missing_documents": missing,
            "comparisons": [],
            "blocking_mismatches": [],
            "advisory_mismatches": [],
            "summary": f"Cannot reconcile: missing {', '.join(missing)}.",
        }

    comparisons = [
        _compare_party(invoice, packing_list),
        _compare_product(invoice, packing_list),
        _compare_quantity(invoice, packing_list),
        _compare_reference(invoice, packing_list),
    ]

    blocking = [c.field for c in comparisons if not c.match and c.severity == "blocking"]
    advisory = [c.field for c in comparisons if not c.match and c.severity == "advisory"]

    if blocking:
        summary = (
            f"{len(blocking)} field(s) disagree across the documents: "
            f"{', '.join(blocking)}."
        )
    elif advisory:
        summary = "Core fields agree; " + "; ".join(
            c.note for c in comparisons if not c.match
        )
    else:
        summary = "All compared fields agree across both documents."

    return {
        "status": "EVALUATED",
        "consistent": not blocking,
        "missing_documents": [],
        "comparisons": [c.to_dict() for c in comparisons],
        "blocking_mismatches": blocking,
        "advisory_mismatches": advisory,
        "summary": summary,
    }
