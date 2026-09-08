"""Hash-chaining for tamper-evident audit logs.

Each audit log entry's hash covers its own content plus the previous
entry's hash. Editing any past entry changes its hash, which then no
longer matches what the next entry recorded as "previous_entry_hash" -
so tampering anywhere in history is detectable by re-walking the chain.

Timestamps are canonicalized before hashing: Postgres may reformat a
timestamp's string representation on round-trip (trimming trailing
zeros, changing timezone notation) without changing the actual instant
in time. Hashing the raw string would treat that reformatting as
tampering; parsing and reserializing first avoids false positives.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def _canonical_timestamp(ts: Any) -> str:
    """Normalize a timestamp to one consistent string form before hashing."""
    if isinstance(ts, str):
        normalized = ts.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).isoformat()
        except ValueError:
            return ts
    return str(ts)


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Hash a payload dict deterministically (sorted keys, no whitespace)."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_entry_hash(
    entry_id: str,
    timestamp: str,
    action: str,
    claim_id: str | None,
    payload_hash: str,
    previous_entry_hash: str | None,
) -> str:
    """Compute the chained hash for one audit log entry."""
    content = "|".join([
        str(entry_id),
        _canonical_timestamp(timestamp),
        str(action),
        str(claim_id or ""),
        str(payload_hash),
        str(previous_entry_hash or ""),
    ])
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_chain(entries: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """
    Walk a list of audit log entries (oldest first) and verify the hash chain.
    Returns (is_valid, first_broken_index). first_broken_index is None if valid.
    """
    previous_hash = None
    for i, entry in enumerate(entries):
        payload = entry.get("details", {}) or {}
        expected_payload_hash = compute_payload_hash(payload)
        expected_entry_hash = compute_entry_hash(
            entry_id=entry["id"],
            timestamp=str(entry["created_at"]),
            action=entry["action"],
            claim_id=entry.get("claim_id"),
            payload_hash=expected_payload_hash,
            previous_entry_hash=previous_hash,
        )
        if entry.get("entry_hash") != expected_entry_hash:
            return False, i
        previous_hash = entry["entry_hash"]
    return True, None


def verify_chain_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify the chain and return a full report suitable for an API or UI.

    ``verify_chain`` answers "is it intact"; this answers "what exactly is
    wrong, and where", which is what an officer reviewing an audit trail
    needs. It distinguishes the two ways a chain breaks:

    * the entry's own contents were edited, so its hash no longer matches;
    * the entry no longer links to its predecessor, meaning an earlier entry
      was deleted or reordered.

    Entries written before hash-chaining existed carry no ``entry_hash``.
    They are reported as ``unhashed`` and skipped rather than counted as
    tampering, so switching the feature on does not invalidate old rows.
    """
    entries_out: list[dict[str, Any]] = []
    previous_hash: str | None = None
    checked = 0
    unhashed = 0
    broken_index: int | None = None
    broken_id: str | None = None
    reason: str | None = None

    for index, entry in enumerate(entries):
        stored = entry.get("entry_hash")
        action = entry.get("action")

        if not stored:
            unhashed += 1
            entries_out.append(
                {
                    "index": index,
                    "id": entry.get("id"),
                    "action": action,
                    "created_at": entry.get("created_at"),
                    "entry_hash": None,
                    "status": "unhashed",
                }
            )
            continue

        recorded_previous = entry.get("previous_entry_hash")
        expected = compute_entry_hash(
            entry_id=entry["id"],
            timestamp=str(entry["created_at"]),
            action=entry["action"],
            claim_id=entry.get("claim_id"),
            payload_hash=compute_payload_hash(entry.get("details", {}) or {}),
            previous_entry_hash=recorded_previous,
        )

        contents_ok = stored == expected
        link_ok = recorded_previous == previous_hash
        ok = contents_ok and link_ok

        if not ok and broken_index is None:
            broken_index = index
            broken_id = entry.get("id")
            reason = (
                f"Entry {index} ({action}) has been altered since it was written: "
                "its contents no longer match its recorded hash."
                if not contents_ok
                else f"Entry {index} ({action}) does not link to the entry before "
                "it: an earlier entry was removed or reordered."
            )

        entries_out.append(
            {
                "index": index,
                "id": entry.get("id"),
                "action": action,
                "created_at": entry.get("created_at"),
                "entry_hash": stored,
                "status": "ok" if ok else "broken",
            }
        )
        checked += 1
        previous_hash = stored

    return {
        "intact": broken_index is None,
        "checked": checked,
        "unhashed": unhashed,
        "broken_at_index": broken_index,
        "broken_at_id": broken_id,
        "reason": reason,
        "entries": entries_out,
    }