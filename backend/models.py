"""Pydantic request/response models for the backend API.

These are the API contract for Person 4's frontend. They are deliberately
separate from the root ``schema.py`` (Person 1/2's domain models) so that
changes on either side do not break the other.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ClaimStatus(StrEnum):
    """Lifecycle of a Certificate of Origin verification case."""

    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class DocumentType(StrEnum):
    """Type of an uploaded document, supplied by the caller at upload time."""

    INVOICE = "invoice"
    PACKING_LIST = "packing_list"
    CERTIFICATE_OF_ORIGIN = "certificate_of_origin"
    OTHER = "other"


# --- requests --------------------------------------------------------


class ClaimCreateRequest(BaseModel):
    reference: str | None = Field(
        default=None,
        max_length=200,
        description="Optional human-facing reference, e.g. an exporter case number.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form JSON stored alongside the claim.",
    )


# --- responses -------------------------------------------------------


class ClaimResponse(BaseModel):
    id: str
    reference: str | None = None
    status: ClaimStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class DocumentResponse(BaseModel):
    id: str
    claim_id: str
    filename: str
    doc_type: DocumentType
    content_type: str
    size_bytes: int
    storage_path: str
    created_at: str | None = None


class ExtractedDataResponse(BaseModel):
    id: str
    document_id: str
    data: dict[str, Any]
    created_at: str | None = None


class VerificationResult(BaseModel):
    """Result returned by the other modules, stored verbatim by the backend."""

    extraction: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any] | None = None
    rules: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    decision: str = ClaimStatus.PENDING_REVIEW
    raw: dict[str, Any] | None = None


class ProcessResponse(BaseModel):
    claim_id: str
    status: ClaimStatus
    decision: str
    documents_processed: int


class ClaimResultResponse(BaseModel):
    """Everything the dashboard needs to render one claim."""

    claim: ClaimResponse
    documents: list[DocumentResponse] = Field(default_factory=list)
    extraction: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any] | None = None
    rules: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    decision: str | None = None
    status: ClaimStatus
    processed_at: str | None = None


class AuditLogResponse(BaseModel):
    id: str
    claim_id: str | None = None
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class HealthResponse(BaseModel):
    status: str
    supabase_configured: bool


class RootResponse(BaseModel):
    service: str
    version: str
    docs: str
