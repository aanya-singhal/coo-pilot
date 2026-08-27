"""Claim endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.database import Database, get_database
from backend.models import (
    AuditLogResponse,
    ClaimCreateRequest,
    ClaimResponse,
    ClaimStatus,
    ClaimResultResponse,
    OriginDeclarationRequest,
    OriginDeclarationResponse,
)
from backend.services import audit, claims as claims_service, pipeline
from backend.services.claims import ClaimNotFoundError

router = APIRouter(prefix="/claims", tags=["claims"])

DatabaseDep = Annotated[Database, Depends(get_database)]


@router.post("", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim(payload: ClaimCreateRequest, db: DatabaseDep) -> ClaimResponse:
    """Create a Certificate of Origin verification case."""
    claim = claims_service.create_claim(
        db,
        reference=payload.reference,
        exporter=payload.exporter,
        metadata=payload.metadata,
    )
    return ClaimResponse(**claim)


@router.get("", response_model=list[ClaimResponse])
def list_claims(
    db: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[
        list[ClaimStatus] | None,
        Query(description="Filter by status. Repeat the parameter to pass several."),
    ] = None,
) -> list[ClaimResponse]:
    """List recent claims, newest first, optionally filtered by status."""
    statuses = [str(s) for s in status] if status else None
    rows = claims_service.list_claims(db, limit=limit, statuses=statuses)
    return [ClaimResponse(**c) for c in rows]


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


@router.put(
    "/{claim_id}/origin-declaration", response_model=OriginDeclarationResponse
)
def set_origin_declaration(
    claim_id: str, payload: OriginDeclarationRequest, db: DatabaseDep
) -> OriginDeclarationResponse:
    """Attach the cost statement the rules engine needs to evaluate origin.

    An invoice and a packing list cannot establish origin on their own; the
    engine needs the FOB value and the value and classification of each
    non-originating material. Setting this again replaces the previous one.
    """
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    row = claims_service.set_origin_declaration(
        db, claim_id, payload.model_dump(mode="json")
    )
    return OriginDeclarationResponse(**row)


@router.get(
    "/{claim_id}/origin-declaration", response_model=OriginDeclarationResponse
)
def get_origin_declaration(claim_id: str, db: DatabaseDep) -> OriginDeclarationResponse:
    row = claims_service.get_origin_declaration(db, claim_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No origin declaration for claim '{claim_id}'"
        )
    return OriginDeclarationResponse(**row)


@router.get("/{claim_id}/audit", response_model=list[AuditLogResponse])
def get_claim_audit(claim_id: str, db: DatabaseDep) -> list[AuditLogResponse]:
    """Audit trail for one claim."""
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return [AuditLogResponse(**row) for row in audit.list_for_claim(db, claim_id)]
