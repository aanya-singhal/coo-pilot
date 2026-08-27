"""Audit logging for backend actions.

Never log credentials. ``details`` should hold identifiers and counts, not
API keys, tokens, or file contents.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from backend.database import Database

logger = logging.getLogger(__name__)

CLAIM_CREATED: Final = "claim_created"
DOCUMENT_UPLOADED: Final = "document_uploaded"
ORIGIN_DECLARATION_SET: Final = "origin_declaration_set"
PROCESSING_STARTED: Final = "processing_started"
PROCESSING_COMPLETED: Final = "processing_completed"
PROCESSING_FAILED: Final = "processing_failed"

#: Keys stripped from ``details`` before persisting, as a safety net.
_REDACTED_KEYS: frozenset[str] = frozenset(
    {"api_key", "apikey", "gemini_api_key", "supabase_key", "password", "token", "secret"}
)


def _sanitize(details: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in details.items() if k.lower() not in _REDACTED_KEYS}


def log_action(
    db: Database,
    *,
    claim_id: str | None,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Write an audit row. Never raises - audit failure must not break a request."""
    try:
        db.write_audit_log(
            claim_id=claim_id, action=action, details=_sanitize(details or {})
        )
    except Exception:
        logger.exception("Failed to write audit log action=%s claim=%s", action, claim_id)


def list_for_claim(db: Database, claim_id: str) -> list[dict[str, Any]]:
    return db.list_audit_logs(claim_id)
