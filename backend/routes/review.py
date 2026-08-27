"""Human review endpoints and the review queue.

An automated decision never closes a case on its own - a reviewer approves,
rejects, or asks for more information, and each disposition is recorded and
audited.

This router is included before the claims router so that ``/claims/review``
is matched as a literal path rather than captured as a ``claim_id``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import Database, get_database
from backend.models import (
    ClaimResponse,
    ClaimResultResponse,
    DecisionResponse,
    ReviewAction,
    ReviewDecisionRequest,
)
from backend.services import claims as claims_service, pipeline
from backend.services.claims import ClaimNotFoundError

router = APIRouter(prefix="/claims", tags=["review"])

DatabaseDep = Annotated[Database, Depends(get_database)]

#: Statuses that put a claim in front of a human.
REVIEW_STATUSES = ["PENDING_REVIEW", "FAILED", "REQUESTED_INFO"]


@router.get("/review", response_model=list[ClaimResponse])
def review_queue(
    db: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ClaimResponse]:
    """Claims awaiting human attention, newest first."""
    rows = claims_service.list_claims(db, limit=limit, statuses=REVIEW_STATUSES)
    return [ClaimResponse(**row) for row in rows]


@router.get("/{claim_id}/review", response_model=ClaimResultResponse)
def review_detail(claim_id: str, db: DatabaseDep) -> ClaimResultResponse:
    """Everything a reviewer needs to decide, including prior decisions."""
    try:
        result = pipeline.get_result(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return ClaimResultResponse(**result)


def _decide(
    db: Database, claim_id: str, action: ReviewAction, payload: ReviewDecisionRequest
) -> DecisionResponse:
    try:
        decision = claims_service.record_review_decision(
            db,
            claim_id,
            action=action,
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return DecisionResponse(**decision)


@router.post("/{claim_id}/approve", response_model=DecisionResponse)
def approve_claim(
    claim_id: str, payload: ReviewDecisionRequest, db: DatabaseDep
) -> DecisionResponse:
    """Approve a claim. Sets status to APPROVED."""
    return _decide(db, claim_id, ReviewAction.APPROVED, payload)


@router.post("/{claim_id}/reject", response_model=DecisionResponse)
def reject_claim(
    claim_id: str, payload: ReviewDecisionRequest, db: DatabaseDep
) -> DecisionResponse:
    """Reject a claim. Sets status to REJECTED."""
    return _decide(db, claim_id, ReviewAction.REJECTED, payload)


@router.post("/{claim_id}/request-info", response_model=DecisionResponse)
def request_information(
    claim_id: str, payload: ReviewDecisionRequest, db: DatabaseDep
) -> DecisionResponse:
    """Ask the importer for more information. Sets status to REQUESTED_INFO."""
    return _decide(db, claim_id, ReviewAction.REQUESTED_INFO, payload)


@router.get("/{claim_id}/decisions", response_model=list[DecisionResponse])
def list_decisions(claim_id: str, db: DatabaseDep) -> list[DecisionResponse]:
    """Decision history for one claim."""
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return [
        DecisionResponse(**row) for row in claims_service.list_decisions(db, claim_id)
    ]
