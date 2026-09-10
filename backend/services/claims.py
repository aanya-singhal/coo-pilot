"""Claim and document persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from backend.config import ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS
from backend.database import Database
from backend.models import ClaimStatus, DocumentType, ReviewAction
from backend.services import audit
from backend.services.storage import Storage, build_storage_path

#: Audit action recorded for each reviewer disposition.
_REVIEW_AUDIT_ACTIONS: dict[ReviewAction, str] = {
    ReviewAction.APPROVED: audit.APPROVED,
    ReviewAction.REJECTED: audit.REJECTED,
    ReviewAction.REQUESTED_INFO: audit.INFORMATION_REQUESTED,
}


class ClaimNotFoundError(Exception):
    """Raised when a claim id does not exist."""


class InvalidFileTypeError(Exception):
    """Raised when an uploaded file is not a PDF/PNG/JPG/JPEG."""


def generate_claim_number() -> str:
    """Human-facing identifier, e.g. ``CLM-2026-4F3A9C``.

    Random rather than sequential so it needs no database counter and stays
    the same under both storage backends.
    """
    return (
        f"CLM-{datetime.now(timezone.utc).year}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )


def create_claim(
    db: Database,
    *,
    reference: str | None,
    metadata: dict[str, Any],
    exporter: str | None = None,
) -> dict[str, Any]:
    claim = db.create_claim(
        claim_number=generate_claim_number(),
        reference=reference,
        exporter=exporter,
        metadata=metadata,
    )
    audit.log_action(
        db,
        claim_id=claim["id"],
        action=audit.CLAIM_CREATED,
        details={
            "claim_number": claim.get("claim_number"),
            "reference": reference,
            "exporter": exporter,
        },
    )
    return claim


def record_review_decision(
    db: Database,
    claim_id: str,
    *,
    action: ReviewAction,
    reviewer: str,
    comments: str | None,
) -> dict[str, Any]:
    """Apply a reviewer's decision: update status, record it, audit it."""
    get_claim(db, claim_id)  # raises ClaimNotFoundError

    decision = db.create_decision(
        claim_id=claim_id,
        decision=str(action),
        reviewer=reviewer,
        comments=comments,
    )
    db.update_claim_status(claim_id, str(action))

    audit.log_action(
        db,
        claim_id=claim_id,
        action=_REVIEW_AUDIT_ACTIONS[action],
        details={"reviewer": reviewer, "comments": comments},
    )
    return decision


def list_decisions(db: Database, claim_id: str) -> list[dict[str, Any]]:
    return db.list_decisions(claim_id)


def get_claim(db: Database, claim_id: str) -> dict[str, Any]:
    claim = db.get_claim(claim_id)
    if claim is None:
        raise ClaimNotFoundError(claim_id)
    return claim


def list_claims(
    db: Database, *, limit: int = 50, statuses: list[str] | None = None
) -> list[dict[str, Any]]:
    return db.list_claims(limit=limit, statuses=statuses)


def set_status(db: Database, claim_id: str, status: ClaimStatus) -> dict[str, Any] | None:
    return db.update_claim_status(claim_id, str(status))


def validate_upload(filename: str, content_type: str | None) -> None:
    """Reject anything that is not a PDF/PNG/JPG/JPEG.

    Both the extension and the declared content type must be acceptable; a
    missing content type is tolerated because some clients omit it.
    """
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"Unsupported file extension '{suffix or filename}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise InvalidFileTypeError(
            f"Unsupported content type '{content_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )


def add_document(
    db: Database,
    storage: Storage,
    *,
    claim_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    doc_type: DocumentType,
) -> dict[str, Any]:
    """Upload the original file to storage and record its metadata.

    No extraction happens here - that is Person 1's module, invoked by the
    pipeline via ``POST /claims/{claim_id}/process``.
    """
    get_claim(db, claim_id)  # raises ClaimNotFoundError

    # The id is generated here so the storage path and the database row agree
    # without needing a second write.
    document_id = str(uuid.uuid4())
    storage_path = build_storage_path(claim_id, document_id, filename)
    storage.upload(path=storage_path, content=content, content_type=content_type)

    document = db.create_document(
        document_id=document_id,
        claim_id=claim_id,
        filename=filename,
        doc_type=str(doc_type),
        content_type=content_type,
        size_bytes=len(content),
        storage_path=storage_path,
    )

    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.DOCUMENT_UPLOADED,
        details={
            "document_id": document["id"],
            "doc_type": str(doc_type),
            "filename": filename,
            "size_bytes": len(content),
            "storage_path": storage_path,
        },
    )
    return document


def set_origin_declaration(
    db: Database, claim_id: str, declaration: dict[str, Any]
) -> dict[str, Any]:
    """Store the cost statement backing a preferential claim."""
    row = db.save_origin_declaration(claim_id=claim_id, declaration=declaration)
    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.ORIGIN_DECLARATION_SET,
        details={
            "agreement": declaration.get("agreement"),
            "hs_code": declaration.get("hs_code"),
            "material_count": len(declaration.get("non_originating_materials") or []),
        },
    )
    return row


def get_origin_declaration(db: Database, claim_id: str) -> dict[str, Any] | None:
    return db.get_origin_declaration(claim_id)


def list_documents(db: Database, claim_id: str) -> list[dict[str, Any]]:
    return db.list_documents(claim_id)
