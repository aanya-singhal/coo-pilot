"""Pipeline endpoint: extraction -> rules -> stored verification result."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.database import Database, get_database
from backend.models import ProcessResponse
from backend.services import pipeline as pipeline_service
from backend.services.claims import ClaimNotFoundError
from backend.services.pipeline import NoDocumentsError
from backend.services.storage import Storage, get_storage

router = APIRouter(prefix="/claims", tags=["pipeline"])

DatabaseDep = Annotated[Database, Depends(get_database)]
StorageDep = Annotated[Storage, Depends(get_storage)]


@router.post("/{claim_id}/process", response_model=ProcessResponse)
def process_claim(
    claim_id: str, db: DatabaseDep, storage: StorageDep
) -> ProcessResponse:
    """Run the pipeline over the claim's documents and store the result.

    Runs synchronously - fine at prototype scale. Poll
    ``GET /claims/{claim_id}/result`` afterwards for the full payload.
    """
    try:
        result = pipeline_service.process_claim(db, storage, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    except NoDocumentsError:
        raise HTTPException(
            status_code=400,
            detail="Claim has no documents. Upload documents before processing.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")

    return ProcessResponse(**result)
