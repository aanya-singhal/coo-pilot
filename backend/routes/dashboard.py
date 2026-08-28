"""Dashboard statistics.

The backend counts; Person 4's dashboard renders. This exists so the
frontend never needs direct database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.database import Database, get_database
from backend.models import ClaimStatus, DashboardResponse

router = APIRouter(tags=["dashboard"])

DatabaseDep = Annotated[Database, Depends(get_database)]


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: DatabaseDep) -> DashboardResponse:
    """Claim counts by status."""
    counts = db.count_claims_by_status()

    def n(status: ClaimStatus) -> int:
        return counts.get(str(status), 0)

    return DashboardResponse(
        total=sum(counts.values()),
        created=n(ClaimStatus.CREATED),
        processing=n(ClaimStatus.PROCESSING),
        pending_review=n(ClaimStatus.PENDING_REVIEW),
        approved=n(ClaimStatus.APPROVED),
        rejected=n(ClaimStatus.REJECTED),
        failed=n(ClaimStatus.FAILED),
        requested_info=n(ClaimStatus.REQUESTED_INFO),
    )
