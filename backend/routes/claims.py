"""Claim endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.database import Database, get_database
from backend.models import (
    AuditLogResponse,
    ClaimCreateRequest,
    ClaimResponse,
    ClaimResultResponse,
)
from backend.services import audit, claims as claims_service, pipeline
from backend.services.claims import ClaimNotFoundError

router = APIRouter(prefix="/claims", tags=["claims"])

DatabaseDep = Annotated[Database, Depends(get_database)]


@router.post("", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(payload: ClaimCreateRequest, db: DatabaseDep) -> ClaimResponse:
    """Create a Certificate of Origin verification case."""
    claim = claims_service.create_claim(
        db, reference=payload.reference, metadata=payload.metadata
    )
    return ClaimResponse(**claim)


@router.get("", response_model=list[ClaimResponse])
def list_claims(
    db: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ClaimResponse]:
    """List recent claims, newest first (convenience for the dashboard)."""
    return [ClaimResponse(**c) for c in claims_service.list_claims(db, limit=limit)]


@router.get("/{claim_id}", response_model=ClaimResponse)
def get_claim(claim_id: str, db: DatabaseDep) -> ClaimResponse:
    try:
        claim = claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return ClaimResponse(**claim)


@router.get("/{claim_id}/result", response_model=ClaimResultResponse)
def get_claim_result(claim_id: str, db: DatabaseDep) -> ClaimResultResponse:
    """Everything the dashboard needs: claim, documents, and all module results.

    Available before processing too - the result fields are simply empty.
    """
    try:
        result = pipeline.get_result(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return ClaimResultResponse(**result)


@router.get("/{claim_id}/audit", response_model=list[AuditLogResponse])
def get_claim_audit(claim_id: str, db: DatabaseDep) -> list[AuditLogResponse]:
    """Audit trail for one claim."""
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return [AuditLogResponse(**row) for row in audit.list_for_claim(db, claim_id)]
