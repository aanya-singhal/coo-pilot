"""Document upload endpoints.

Uploads are stored only. Extraction happens in the pipeline, which calls
Person 1's module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.config import MAX_UPLOAD_BYTES
from backend.database import Database, get_database
from backend.models import DocumentResponse, DocumentType, ExtractionResponse
from backend.services import claims as claims_service
from backend.services import pipeline as pipeline_service
from backend.services.claims import ClaimNotFoundError, InvalidFileTypeError
from backend.services.storage import Storage, get_storage

router = APIRouter(prefix="/claims", tags=["documents"])

DatabaseDep = Annotated[Database, Depends(get_database)]
StorageDep = Annotated[Storage, Depends(get_storage)]


@router.post(
    "/{claim_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    claim_id: str,
    db: DatabaseDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="PDF, PNG, JPG or JPEG")],
    doc_type: Annotated[DocumentType, Form()] = DocumentType.INVOICE,
) -> DocumentResponse:
    """Upload one document and attach it to a claim."""
    filename = file.filename or ""
    try:
        claims_service.validate_upload(filename, file.content_type)
    except InvalidFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Reject oversized uploads before reading them into memory where the
    # client declared a size.
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )

    try:
        document = claims_service.add_document(
            db,
            storage,
            claim_id=claim_id,
            filename=filename,
            content=content,
            content_type=file.content_type or "application/octet-stream",
            doc_type=doc_type,
        )
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    return DocumentResponse(**document)


@router.post(
    "/{claim_id}/documents/{document_id}/extract",
    response_model=ExtractionResponse,
)
def extract_document(
    claim_id: str, document_id: str, db: DatabaseDep, storage: StorageDep
) -> ExtractionResponse:
    """Run Person 1's extractor over one stored document and save the result.

    An extraction failure is stored and returned with
    ``extraction_status: FAILED`` rather than raised, so the reason survives
    in the database instead of vanishing into a 500.
    """
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    document = db.get_document(document_id)
    if document is None or document["claim_id"] != claim_id:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found on claim '{claim_id}'",
        )

    row = pipeline_service.extract_document(db, storage, document)
    return ExtractionResponse(**row)


@router.get("/{claim_id}/documents", response_model=list[DocumentResponse])
def list_documents(claim_id: str, db: DatabaseDep) -> list[DocumentResponse]:
    """List the documents attached to a claim."""
    try:
        claims_service.get_claim(db, claim_id)
    except ClaimNotFoundError:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return [
        DocumentResponse(**doc) for doc in claims_service.list_documents(db, claim_id)
    ]
