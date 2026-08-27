"""Pipeline endpoint: extraction -> rules -> stored verification result."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.database import Database, get_database
from backend.models import ProcessResponse, ReconciliationResponse
from backend.services import audit, claims as claims_service
from backend.services import pipeline as pipeline_service
from backend.services import reconciliation as reconciliation_service
from backend.services.claims import ClaimNotFoundError
from backend.services.pipeline import NoDocumentsError
from backend.services.storage import Storage, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["pipeline"])

DatabaseDep = Annotated[Database, Depends(get_database)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def _run_pipeline(
    db: Database, storage: Storage, claim_id: str
) -> ProcessResponse:
    try:
        result = pipeline_service.process_claim(db, storage, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    except NoDocumentsError:
        raise HTTPException(
            status_code=400,
            detail="Claim has no documents. Upload documents before processing.",
        )
    except Exception:
        # The cause is logged and audited; callers get no internals.
        logger.exception("Verification failed for claim %s", claim_id)
        raise HTTPException(
            status_code=500, detail="Verification failed. See server logs."
        )
    return ProcessResponse(**result)


@router.post("/{claim_id}/verify", response_model=ProcessResponse)
def verify_claim(
    claim_id: str, db: DatabaseDep, storage: StorageDep
) -> ProcessResponse:
    """Run the full verification pipeline and store the result.

    extraction -> reconciliation -> rules -> risk -> decision -> database.
    Runs synchronously, which is fine at prototype scale. Read
    ``GET /claims/{claim_id}/result`` afterwards for the full payload.
    """
    return _run_pipeline(db, storage, claim_id)


@router.post("/{claim_id}/process", response_model=ProcessResponse)
def process_claim(
    claim_id: str, db: DatabaseDep, storage: StorageDep
) -> ProcessResponse:
    """Alias of ``/verify``, kept because existing callers use this path."""
    return _run_pipeline(db, storage, claim_id)


@router.post("/{claim_id}/reconcile", response_model=ReconciliationResponse)
def reconcile_claim(claim_id: str, db: DatabaseDep) -> ReconciliationResponse:
    """Compare the claim's already-extracted documents against each other.

    Deterministic field comparison over stored extraction results - it does
    not re-run extraction and never calls a model.
    """
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    rows = db.list_extracted_data(claim_id)
    if not rows:
        raise HTTPException(
            status_code=400,
            detail=(
                "No extraction results for this claim. Run extraction before "
                "reconciling."
            ),
        )

    documents = reconciliation_service.documents_from_extraction(
        rows, db.list_documents(claim_id)
    )
    result = reconciliation_service.reconcile_documents(
        documents.get("invoice"), documents.get("packing_list")
    )

    audit.log_action(
        db,
        claim_id=claim_id,
        action=audit.RECONCILIATION_COMPLETED,
        details={
            "status": result["status"],
            "mismatch_count": len(result["mismatches"]),
        },
    )
    return ReconciliationResponse(**result)
