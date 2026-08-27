"""Backend pipeline orchestration.

    documents -> Person 1 extraction -> Person 2 rules -> database -> frontend

This module only sequences the calls and persists what comes back. It
contains no AI logic and no business rules.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.database import Database
from backend.models import ClaimStatus
from backend.services import audit, claims as claims_service
from backend.services.extraction_adapter import extract_document_bytes
from backend.services.rules_adapter import run_rules
from backend.services.storage import Storage

logger = logging.getLogger(__name__)


class NoDocumentsError(Exception):
    """Raised when a claim has no uploaded documents to process."""


def extraction_status_of(result: dict[str, Any]) -> str:
    """Classify an extraction result without interpreting its contents."""
    if result.get("error"):
        return "FAILED"
    if result.get("skipped"):
        return "SKIPPED"
    return "SUCCESS"


def extract_document(
    db: Database, storage: Storage, document: dict[str, Any]
) -> dict[str, Any]:
    """Run Person 1's extractor over one stored document and persist the result.

    Returns the stored ``extracted_data`` row. Never raises for an extraction
    failure - the failure is recorded so the reason survives in the database.
    """
    claim_id = document["claim_id"]
    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.EXTRACTION_STARTED,
        details={"document_id": document["id"], "doc_type": document["doc_type"]},
    )

    try:
        content = storage.download(document["storage_path"])
    except Exception as exc:
        logger.exception("Could not download %s", document["storage_path"])
        result: dict[str, Any] = {"error": f"Could not read stored file: {exc}"}
    else:
        result = extract_document_bytes(
            content=content,
            filename=document["filename"],
            doc_type=document["doc_type"],
        )

    status = extraction_status_of(result)
    row = db.save_extracted_data(
        claim_id=claim_id,
        document_id=document["id"],
        data=result,
        extraction_status=status,
    )

    audit.log_action(
        db,
        claim_id=claim_id,
        action=(
            audit.EXTRACTION_FAILED
            if status == "FAILED"
            else audit.EXTRACTION_COMPLETED
        ),
        details={"document_id": document["id"], "extraction_status": status},
    )
    return row


def _extract_all(
    db: Database, storage: Storage, claim_id: str, documents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run Person 1's extractor over every document and persist each result.

    Returns ``{"<doc_type>": {...}}`` - the payload handed to Person 2. Every
    result is persisted per document; if a claim carries two documents of the
    same type, the last one wins in the payload handed to the rules engine.
    A per-document failure is recorded and does not abort the run.
    """
    extraction: dict[str, Any] = {}
    for document in documents:
        row = extract_document(db, storage, document)
        extraction[document["doc_type"]] = row["data"]
    return extraction


def process_claim(db: Database, storage: Storage, claim_id: str) -> dict[str, Any]:
    """Run the full pipeline for a claim and store the verification result."""
    claims_service.get_claim(db, claim_id)  # raises ClaimNotFoundError

    documents = db.list_documents(claim_id)
    if not documents:
        raise NoDocumentsError(claim_id)

    claims_service.set_status(db, claim_id, ClaimStatus.PROCESSING)
    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.PROCESSING_STARTED,
        details={"document_count": len(documents)},
    )

    try:
        extraction = _extract_all(db, storage, claim_id, documents)

        # The rules engine needs a cost statement to evaluate origin; the
        # documents alone cannot supply one. Absent, the engine reports
        # insufficient data rather than guessing.
        declaration_row = db.get_origin_declaration(claim_id)
        rules_payload = dict(extraction)
        if declaration_row:
            rules_payload["origin_declaration"] = declaration_row["declaration"]

        rules_result = run_rules(rules_payload)
    except Exception as exc:
        logger.exception("Pipeline failed for claim %s", claim_id)
        claims_service.set_status(db, claim_id, ClaimStatus.FAILED)
        audit.log_action(
            db,
            claim_id=claim_id,
            action=audit.PROCESSING_FAILED,
            details={"error": str(exc)},
        )
        raise

    result = {
        "extraction": extraction,
        "reconciliation": rules_result.get("reconciliation"),
        "rules": rules_result.get("rules"),
        "risk": rules_result.get("risk"),
        "decision": rules_result.get("decision"),
        "raw": rules_result.get("raw"),
    }
    decision = str(result["decision"] or ClaimStatus.PENDING_REVIEW)

    db.save_verification_result(claim_id=claim_id, result=result, decision=decision)

    # The decision comes from Person 2's engine. The backend only mirrors it
    # onto the claim when it names a known status, and otherwise leaves the
    # claim awaiting human review - it never derives a verdict itself.
    try:
        status = ClaimStatus(decision)
    except ValueError:
        status = ClaimStatus.PENDING_REVIEW
    claims_service.set_status(db, claim_id, status)

    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.PROCESSING_COMPLETED,
        details={"decision": decision, "documents_processed": len(documents)},
    )

    return {
        "claim_id": claim_id,
        "status": status,
        "decision": decision,
        "documents_processed": len(documents),
    }


def get_result(db: Database, claim_id: str) -> dict[str, Any]:
    """Assemble everything the dashboard needs for one claim."""
    claim = claims_service.get_claim(db, claim_id)
    documents = db.list_documents(claim_id)
    verification = db.get_verification_result(claim_id)
    result: dict[str, Any] = (verification or {}).get("result") or {}

    return {
        "claim": claim,
        "documents": documents,
        "extraction": result.get("extraction") or {},
        "reconciliation": result.get("reconciliation"),
        "rules": result.get("rules"),
        "risk": result.get("risk"),
        "decision": result.get("decision"),
        "decisions": db.list_decisions(claim_id),
        "status": claim["status"],
        "processed_at": (verification or {}).get("created_at"),
    }
