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
