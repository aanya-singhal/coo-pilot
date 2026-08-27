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
    REQUESTED_INFO = "REQUESTED_INFO"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReviewAction(StrEnum):
    """A reviewer's disposition of a claim."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUESTED_INFO = "REQUESTED_INFO"


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
    exporter: str | None = Field(
        default=None, max_length=300, description="Exporter named on the claim."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form JSON stored alongside the claim.",
    )


class ReviewDecisionRequest(BaseModel):
    """A human reviewer's decision on a claim."""

    reviewer: str = Field(min_length=1, max_length=200)
    comments: str | None = Field(default=None, max_length=4000)


# --- responses -------------------------------------------------------


class NonOriginatingMaterial(BaseModel):
    """One input the exporter did not originate."""

    description: str | None = Field(default=None, max_length=300)
    hs_code: str | None = Field(default=None, max_length=20)
    value: float | None = Field(default=None, ge=0)


class OriginDeclarationRequest(BaseModel):
    """Cost statement backing a preferential claim (CAROTAR 2020 Form I).

    The backend stores this verbatim and hands it to the rules engine; it
    does not evaluate or validate the criteria itself. ``agreement`` is not
    checked against a registry here - the rules engine owns which agreements
    exist.
    """

    agreement: str = Field(default="AIFTA", max_length=40)
    hs_code: str | None = Field(default=None, max_length=20)
    fob_value: float | None = Field(default=None, ge=0)
    wholly_obtained: bool = False
    non_originating_materials: list[NonOriginatingMaterial] = Field(
        default_factory=list, max_length=200
    )


class OriginDeclarationResponse(BaseModel):
    claim_id: str
    declaration: dict[str, Any]
    created_at: str | None = None


class ClaimResponse(BaseModel):
    id: str
    claim_number: str | None = None
    reference: str | None = None
    exporter: str | None = None
    status: ClaimStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class DecisionResponse(BaseModel):
    id: str
    claim_id: str
    decision: ReviewAction
    reviewer: str
    comments: str | None = None
    created_at: str | None = None


class DashboardResponse(BaseModel):
    """Counts for the dashboard. Person 4 renders these; the backend counts."""

    total: int
    created: int
    processing: int
    pending_review: int
    approved: int
    rejected: int
    failed: int
    requested_info: int


class ReconciliationResponse(BaseModel):
    """Deterministic cross-document comparison result."""

    status: str
    matches: list[dict[str, Any]] = Field(default_factory=list)
    mismatches: list[dict[str, Any]] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    summary: str | None = None


class ExtractionResponse(BaseModel):
    id: str
    claim_id: str
    document_id: str
    extraction_status: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


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
    decisions: list[DecisionResponse] = Field(
        default_factory=list, description="Human review decisions, newest last."
    )
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
