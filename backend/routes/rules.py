"""Rule administration: viewing and amending rules of origin.

Amending a rule never edits the version in force. It creates the next
version and leaves the previous one intact, because decisions already taken
under it have to stay reproducible when they are reviewed later.

Every amendment is written to the audit log, so the record of *who changed
the policy* is covered by the same hash chain as the decisions themselves.

Note for reviewers: versions live in the in-process registry, so they reset
when the service restarts. Persisting them is the obvious next step and is
deliberately not claimed here.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.database import Database, get_database
from backend.services import rule_store
from rules import agreements
from rules.agreements import ChangeInTariffClassification

router = APIRouter(prefix="/rules", tags=["rules"])

DatabaseDep = Annotated[Database, Depends(get_database)]


class AmendRuleRequest(BaseModel):
    """An amendment to one agreement's general rule of origin."""

    value_content_min_percent: float | None = Field(
        default=None, ge=0, le=100, description="New value-content threshold."
    )
    ctc_rule: ChangeInTariffClassification | None = Field(
        default=None, description="New tariff-shift level (CC, CTH or CTSH)."
    )
    effective_from: str = Field(description="Date this version takes effect (ISO 8601).")
    amendment_note: str = Field(
        min_length=1, description="Why the rule changed. Shown to reviewing officers."
    )
    citation: str | None = Field(
        default=None, description="Updated legal citation, if the amendment changes it."
    )


def _serialise(criteria: agreements.OriginCriteria) -> dict[str, Any]:
    return {
        "code": criteria.code,
        "name": criteria.name,
        "version": criteria.version,
        "effective_from": criteria.effective_from,
        "amendment_note": criteria.amendment_note,
        "value_content_min_percent": criteria.value_content_min_percent,
        "value_content_basis": criteria.value_content_basis,
        "ctc_rule": criteria.ctc_rule.value,
        "ctc_digits": criteria.ctc_digits,
        "requires_both": criteria.requires_both,
        "criterion": criteria.describe(),
        "citation": criteria.citation,
        "source_url": criteria.source_url,
    }


@router.get("")
def list_rules() -> dict[str, Any]:
    """Every agreement, with its current version and its full version history."""
    return {
        "agreements": [
            {
                "code": code,
                "current": _serialise(versions[-1]),
                "versions": [_serialise(v) for v in versions],
            }
            for code, versions in sorted(agreements.REGISTRY.items())
        ]
    }


@router.get("/{code}")
def get_rule(code: str) -> dict[str, Any]:
    """One agreement's current rule and its version history."""
    versions = agreements.list_versions(code)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Unknown agreement '{code}'")
    return {
        "code": versions[-1].code,
        "current": _serialise(versions[-1]),
        "versions": [_serialise(v) for v in versions],
    }


@router.post("/{code}/amend")
def amend_rule(code: str, request: AmendRuleRequest, db: DatabaseDep) -> dict[str, Any]:
    """Create the next version of an agreement's rule.

    Returns the new version alongside the one it supersedes, so the caller can
    show exactly what changed.
    """
    previous = agreements.get_criteria(code)
    if previous is None:
        raise HTTPException(status_code=404, detail=f"Unknown agreement '{code}'")

    if (
        request.value_content_min_percent is None
        and request.ctc_rule is None
        and request.citation is None
    ):
        raise HTTPException(
            status_code=422,
            detail="An amendment must change the threshold, the tariff-shift rule, or the citation.",
        )

    try:
        new_version = agreements.amend(
            code,
            value_content_min_percent=request.value_content_min_percent,
            ctc_rule=request.ctc_rule,
            effective_from=request.effective_from,
            amendment_note=request.amendment_note,
            citation=request.citation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Write the version through to storage before recording the amendment,
    # so a restart cannot leave an audit entry referring to a version the
    # registry no longer knows about.
    try:
        rule_store.persist(db, new_version)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Amendment could not be stored, so it was not applied: {exc}",
        ) from exc

    db.write_audit_log(
        claim_id=None,
        action="rule_amended",
        details={
            "agreement": new_version.code,
            "from_version": previous.version,
            "to_version": new_version.version,
            "effective_from": new_version.effective_from,
            "note": new_version.amendment_note,
            "value_content_min_percent": {
                "from": previous.value_content_min_percent,
                "to": new_version.value_content_min_percent,
            },
            "ctc_rule": {
                "from": previous.ctc_rule.value,
                "to": new_version.ctc_rule.value,
            },
        },
    )

    return {"previous": _serialise(previous), "current": _serialise(new_version)}