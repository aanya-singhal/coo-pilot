#!/usr/bin/env python3
"""Demonstrate that the audit log is tamper-evident.

Writes a short audit trail, verifies it, edits one past entry the way an
insider would, then verifies again and shows the chain break.

Run it with:
    .venv/bin/python scripts/tamper_demo.py          (macOS / Linux)
    .venv\\Scripts\\python scripts\\tamper_demo.py     (Windows)

Uses the in-memory database, so it touches nothing in Supabase and is safe to
run in front of an audience as often as you like.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import InMemoryDatabase  # noqa: E402
from backend.services import hashing  # noqa: E402

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

TRAIL = [
    ("claim_created", {"claim_id": "COO-2026-001"}),
    ("document_uploaded", {"document": "sample_invoice.png"}),
    ("document_uploaded", {"document": "packing_list_clean.png"}),
    ("extraction_completed", {"fields": 6}),
    ("reconciliation_completed", {"conflicts": 0}),
    ("processing_completed", {"decision": "APPROVED", "rvc": 42.86}),
    ("approved", {"reviewer": "Officer A", "comments": "Documents consistent."}),
]

TAMPERED_INDEX = 6


def show(report: dict) -> None:
    for entry in report["entries"]:
        mark = f"{GREEN}OK    {OFF}" if entry["status"] == "ok" else f"{RED}BROKEN{OFF}"
        digest = (entry["entry_hash"] or "-")[:16]
        print(f"   {entry['index']}  {mark}  {entry['action']:<26} {DIM}{digest}{OFF}")
    print()
    if report["intact"]:
        print(f"   {GREEN}{BOLD}CHAIN INTACT{OFF} - {report['checked']} entries verified\n")
    else:
        print(f"   {RED}{BOLD}CHAIN BROKEN{OFF} at entry {report['broken_at_index']}")
        print(f"   {report['reason']}\n")


def main() -> None:
    db = InMemoryDatabase()
    for action, details in TRAIL:
        db.write_audit_log(claim_id="COO-2026-001", action=action, details=details)

    print(f"\n{BOLD}1. The audit trail as written{OFF}\n")
    show(hashing.verify_chain_report(db.list_all_audit_logs()))

    input(f"   {DIM}Press Enter to tamper with the officer's decision...{OFF}\n")

    row = db.audit[TAMPERED_INDEX]
    original = row["details"]["comments"]
    row["details"]["comments"] = "Approved without review."

    print(f"{BOLD}2. Someone edits entry {TAMPERED_INDEX} directly in the database{OFF}\n")
    print(f"   was:  {DIM}{original}{OFF}")
    print(f"   now:  {RED}{row['details']['comments']}{OFF}\n")
    print("   The row still looks perfectly ordinary. Nothing about it")
    print("   reveals that it was changed after the fact.\n")

    input(f"   {DIM}Press Enter to verify the chain again...{OFF}\n")

    print(f"{BOLD}3. Verification{OFF}\n")
    show(hashing.verify_chain_report(db.list_all_audit_logs()))

    print(f"   {DIM}The edit changed the entry's contents, so its recomputed hash no")
    print(f"   longer matches the hash stored when it was written. Hiding the edit")
    print(f"   would mean rewriting every entry that follows it.{OFF}\n")


if __name__ == "__main__":
    main()