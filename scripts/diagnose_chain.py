#!/usr/bin/env python3
"""Diagnose a broken audit chain.

A chain that verifies in memory but breaks against a real database usually
means a stored field is coming back in a different form from the one that was
hashed - a timestamp reformatted, a number normalised, a dict re-encoded.
That is a false positive, and it is worse than no tamper detection at all,
because it cries wolf.

This finds the offending entry and reports exactly which component of the
hash no longer reproduces, instead of just saying "broken".

Run it with the backend's environment (so it talks to the same database):
    .venv/bin/python scripts/diagnose_chain.py
    .venv\\Scripts\\python scripts\\diagnose_chain.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_database  # noqa: E402
from backend.services import hashing  # noqa: E402

RED, GREEN, DIM, BOLD, OFF = "\033[31m", "\033[32m", "\033[2m", "\033[1m", "\033[0m"


def main() -> None:
    db = get_database()
    rows = db.list_all_audit_logs()
    print(f"\n{BOLD}Audit entries read from storage: {len(rows)}{OFF}\n")

    if not rows:
        print("  Nothing stored yet. Run a case first.\n")
        return

    previous_hash = None
    broken = 0

    for index, row in enumerate(rows):
        stored = row.get("entry_hash")
        if not stored:
            print(f"  {index:>3}  {DIM}unhashed (written before chaining existed){OFF}")
            continue

        recorded_previous = row.get("previous_entry_hash")
        payload = row.get("details", {}) or {}
        recomputed = hashing.compute_entry_hash(
            entry_id=row["id"],
            timestamp=str(row["created_at"]),
            action=row["action"],
            claim_id=row.get("claim_id"),
            payload_hash=hashing.compute_payload_hash(payload),
            previous_entry_hash=recorded_previous,
        )

        contents_ok = recomputed == stored
        link_ok = recorded_previous == previous_hash
        previous_hash = stored

        if contents_ok and link_ok:
            print(f"  {index:>3}  {GREEN}ok    {OFF} {row['action']}")
            continue

        broken += 1
        print(f"\n  {index:>3}  {RED}BROKEN{OFF} {BOLD}{row['action']}{OFF}")

        if not link_ok:
            print(f"       {RED}link mismatch{OFF} - this entry does not point at the previous one")
            print(f"         previous entry's hash : {DIM}{previous_hash}{OFF}")
            print(f"         this row records      : {DIM}{recorded_previous}{OFF}")
            print(f"       {DIM}Usually means the read order differs from the write order.{OFF}")

        if not contents_ok:
            print(f"       {RED}content mismatch{OFF} - a stored field differs from what was hashed")
            print(f"         stored hash     : {DIM}{stored}{OFF}")
            print(f"         recomputed hash : {DIM}{recomputed}{OFF}")
            print(f"\n       {BOLD}Fields as they came back from storage:{OFF}")
            ts = str(row["created_at"])
            print(f"         id           : {row['id']!r}")
            print(f"         created_at   : {ts!r}")
            print(f"         canonicalised: {hashing._canonical_timestamp(ts)!r}")
            print(f"         action       : {row['action']!r}")
            print(f"         claim_id     : {row.get('claim_id')!r}")
            print(f"         details      : {json.dumps(payload, sort_keys=True)}")
            print(f"\n       {DIM}Compare 'created_at' and 'canonicalised'. If the database")
            print(f"       reformatted the timestamp and canonicalisation did not undo it,")
            print(f"       that is the cause. Otherwise the details payload re-encoded.{OFF}")

    print()
    if broken:
        print(f"  {RED}{BOLD}{broken} entry/entries did not reproduce.{OFF}")
        print(f"  {DIM}If nobody edited the database, this is a false positive and the")
        print(f"  hashing needs to canonicalise whatever field is shown above.{OFF}\n")
    else:
        print(f"  {GREEN}{BOLD}Every entry reproduced. Chain intact.{OFF}\n")


if __name__ == "__main__":
    main()