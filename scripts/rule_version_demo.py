#!/usr/bin/env python3
"""Demonstrate versioned rules of origin.

Shows that amending a rule changes how new claims are judged without changing
a decision already taken: the old case remains explainable under the version
that was in force when it was decided.

Run it with:
    .venv/bin/python scripts/rule_version_demo.py          (macOS / Linux)
    .venv\\Scripts\\python scripts\\rule_version_demo.py     (Windows)

Runs entirely in memory. Nothing is written to a database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rules import agreements  # noqa: E402
from rules.engine import evaluate  # noqa: E402

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

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
        {"description": "Raw cotton yarn (imported)", "hs_code": "5205.11", "value": 2400.0}
    ],
}


def run(declaration: dict) -> dict:
    return evaluate(
        {
            "invoice": INVOICE,
            "packing_list": PACKING_LIST,
            "origin_declaration": declaration,
        }
    )


def show(label: str, result: dict) -> None:
    origin = result["rules"]["origin"]
    value = origin["value_content"]
    decision = result["decision"]
    colour = GREEN if decision == "APPROVED" else RED
    print(f"   {BOLD}{label}{OFF}")
    print(
        f"      rule version {origin['rule_version']}"
        f"  {DIM}(effective {origin['effective_from']}){OFF}"
    )
    print(
        f"      RVC {value['regional_value_content_percent']}%"
        f"  against threshold {value['threshold_percent']}%"
    )
    print(f"      decision: {colour}{decision}{OFF}\n")


def main() -> None:
    print(f"\n{BOLD}1. A claim assessed under the rule as it stands today{OFF}\n")
    print(f"   {DIM}Same documents throughout: 500 sets, USD 4,200 FOB,")
    print(f"   USD 2,400 of imported yarn. The goods never change.{OFF}\n")
    before = run(DECLARATION)
    show("Claim COO-2026-001", before)

    input(f"   {DIM}Press Enter to amend the AIFTA threshold...{OFF}\n")

    print(f"{BOLD}2. A policy officer raises the AIFTA value-content threshold{OFF}\n")
    new_version = agreements.amend(
        "AIFTA",
        value_content_min_percent=45.0,
        effective_from="2026-10-01",
        amendment_note="Threshold raised from 35% to 45% by gazette notification.",
    )
    print(f"   Created version {new_version.version}, effective {new_version.effective_from}")
    print(f"   {DIM}{new_version.amendment_note}{OFF}")
    print(f"   Versions on record: {[v.version for v in agreements.list_versions('AIFTA')]}\n")
    print("   The previous version was not edited. It cannot be: decisions")
    print("   already taken under it have to stay reproducible.\n")

    input(f"   {DIM}Press Enter to re-run both the new and the old claim...{OFF}\n")

    print(f"{BOLD}3. The amendment applies going forward, not backward{OFF}\n")
    show("A NEW claim, judged under the current rule", run(DECLARATION))
    show(
        "The OLD claim, still judged under version 1",
        run({**DECLARATION, "rule_version": 1}),
    )

    print(f"   {DIM}Identical goods, opposite outcomes - because the rule changed,")
    print(f"   not the evidence. An officer reviewing the old decision sees the")
    print(f"   threshold that actually applied on the day it was made.{OFF}\n")


if __name__ == "__main__":
    main()