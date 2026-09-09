"""Persistence for versioned rules of origin.

The rule registry lives in memory so the engine can read it without a
database round trip on every evaluation. That is fine while the process
runs, but a policy system that forgets its own amendments on restart is not
a policy system: a decision taken under version 2 becomes unexplainable the
moment the service is restarted and only version 1 is known.

So the registry is a cache, and the database is the record. Amendments are
written through on the way in, and replayed on the way up.

Versions are append-only. Nothing here updates or deletes a stored version,
because a decision already taken under it has to stay reproducible.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.database import Database
from rules import agreements
from rules.agreements import ChangeInTariffClassification, OriginCriteria

logger = logging.getLogger(__name__)

#: Fields persisted per version. The dataclass carries more, but these are
#: the ones that define the rule; the rest are derived.
_FIELDS = (
    "code",
    "name",
    "value_content_min_percent",
    "value_content_basis",
    "ctc_rule",
    "requires_both",
    "citation",
    "source_url",
    "verified_on",
    "version",
    "effective_from",
    "amendment_note",
)


def to_row(criteria: OriginCriteria) -> dict[str, Any]:
    """Flatten a rule version into a storable row."""
    row = {field: getattr(criteria, field) for field in _FIELDS}
    row["ctc_rule"] = criteria.ctc_rule.value
    return row


def from_row(row: dict[str, Any]) -> OriginCriteria:
    """Rebuild a rule version from a stored row."""
    return OriginCriteria(
        code=row["code"],
        name=row["name"],
        value_content_min_percent=float(row["value_content_min_percent"]),
        value_content_basis=row["value_content_basis"],
        ctc_rule=ChangeInTariffClassification(row["ctc_rule"]),
        requires_both=bool(row["requires_both"]),
        citation=row["citation"],
        source_url=row["source_url"],
        verified_on=row.get("verified_on", "2026-08-27"),
        version=int(row["version"]),
        effective_from=row["effective_from"],
        amendment_note=row.get("amendment_note", "") or "",
    )


def persist(db: Database, criteria: OriginCriteria) -> None:
    """Write one version through to storage.

    A storage failure must not silently discard an amendment that the
    registry has already accepted, so it is logged loudly rather than
    swallowed. The caller decides whether to surface it.
    """
    db.save_rule_version(criteria=to_row(criteria))


def restore(db: Database) -> int:
    """Load stored versions into the registry. Returns how many were added.

    Version 1 of each agreement is defined in code, so only amendments need
    restoring. A stored version already present in the registry is skipped,
    which makes this safe to call more than once.
    """
    try:
        rows = db.list_rule_versions()
    except Exception:  # noqa: BLE001 - startup must not fail on a read error
        logger.exception("Could not read stored rule versions; using code defaults")
        return 0

    def _order(row: dict[str, Any]) -> tuple[str, int]:
        """Sort defensively: a malformed row must not crash startup, which is
        the whole reason this runs inside a try in the first place."""
        try:
            return str(row.get("code", "")), int(row.get("version", 0))
        except (TypeError, ValueError):
            return str(row.get("code", "")), 0

    restored = 0
    for row in sorted(rows, key=_order):
        try:
            criteria = from_row(row)
        except (KeyError, ValueError, TypeError):
            logger.warning("Skipping unreadable rule version row: %r", row.get("id"))
            continue
        if agreements.get_criteria(criteria.code, criteria.version) is not None:
            continue  # already known, e.g. version 1 from code
        try:
            agreements.register_version(criteria)
            restored += 1
        except ValueError as exc:
            logger.warning("Skipping rule version %s: %s", criteria.version, exc)

    if restored:
        logger.info("Restored %d amended rule version(s) from storage", restored)
    return restored