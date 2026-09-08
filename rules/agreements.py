"""Rules-of-origin criteria per trade agreement.

Every threshold here is recorded with its source so it can be checked rather
than trusted. These values were confirmed against the sources listed on
2026-08-27.

IMPORTANT: agreements are amended, and product-specific rules (PSRs) override
the general rule for many tariff lines. Verify against the current gazette
notification before relying on any of this operationally. The engine reports
which criterion it applied so a reviewing officer can check it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ChangeInTariffClassification(StrEnum):
    """Level at which non-originating materials must change classification."""

    CC = "CC"      # Chapter, 2-digit
    CTH = "CTH"    # Heading, 4-digit
    CTSH = "CTSH"  # Sub-heading, 6-digit


#: HS digits compared for each CTC level.
CTC_DIGITS: dict[ChangeInTariffClassification, int] = {
    ChangeInTariffClassification.CC: 2,
    ChangeInTariffClassification.CTH: 4,
    ChangeInTariffClassification.CTSH: 6,
}


@dataclass(frozen=True)
class OriginCriteria:
    """The general rule of origin for one agreement."""

    code: str
    name: str
    value_content_min_percent: float
    value_content_basis: str
    ctc_rule: ChangeInTariffClassification
    requires_both: bool
    citation: str
    source_url: str
    verified_on: str = "2026-08-27"

    #: Version of this rule. Agreements are amended, so a threshold is only
    #: meaningful alongside the period it applied to. A decision records the
    #: version it was made under, and stays explainable under that version
    #: even after a later version supersedes it.
    version: int = 1
    #: Date this version took effect (ISO 8601).
    effective_from: str = "2009-12-31"
    #: Why this version exists. Empty for an original rule.
    amendment_note: str = ""

    @property
    def ctc_digits(self) -> int:
        return CTC_DIGITS[self.ctc_rule]

    def describe(self) -> str:
        joiner = "and" if self.requires_both else "or"
        return (
            f"{self.name}: value content ≥ {self.value_content_min_percent}% "
            f"of {self.value_content_basis} {joiner} {self.ctc_rule.value} "
            f"({self.ctc_digits}-digit HS)"
        )


AIFTA = OriginCriteria(
    code="AIFTA",
    name="ASEAN-India Free Trade Agreement",
    value_content_min_percent=35.0,
    value_content_basis="FOB value",
    ctc_rule=ChangeInTariffClassification.CTSH,
    requires_both=True,
    citation=(
        "AIFTA Rules of Origin, Rule 4 (general rule): AIFTA content not less "
        "than 35% of FOB value AND change in tariff sub-heading at the 6-digit "
        "HS level. Given effect in India by Notification 189/2009-Cus (NT), "
        "31.12.2009."
    ),
    source_url="https://fta.miti.gov.my/index.php/pages/view/asean-india",
)

SAFTA_NON_LDC = OriginCriteria(
    code="SAFTA",
    name="South Asian Free Trade Area (non-LDC member)",
    value_content_min_percent=40.0,
    value_content_basis="FOB value",
    ctc_rule=ChangeInTariffClassification.CTH,
    requires_both=True,
    citation=(
        "SAFTA Rules of Origin: twin criteria of change of tariff heading at "
        "the 4-digit HS level AND domestic value content of 40% for non-LDC "
        "contracting states (30% for LDCs)."
    ),
    source_url="https://www.un.org/ldcportal/content/south-asian-free-trade-area-safta",
)

SAFTA_LDC = OriginCriteria(
    code="SAFTA_LDC",
    name="South Asian Free Trade Area (LDC member)",
    value_content_min_percent=30.0,
    value_content_basis="FOB value",
    ctc_rule=ChangeInTariffClassification.CTH,
    requires_both=True,
    citation=(
        "SAFTA Rules of Origin: LDC contracting states face a value-content "
        "requirement 10 percentage points below the non-LDC threshold, "
        "alongside the same 4-digit CTH requirement."
    ),
    source_url="https://www.un.org/ldcportal/content/south-asian-free-trade-area-safta",
)


#: Every known version of every agreement, oldest first per code.
REGISTRY: dict[str, list[OriginCriteria]] = {
    c.code: [c] for c in (AIFTA, SAFTA_NON_LDC, SAFTA_LDC)
}

#: Used when the claim does not name an agreement.
DEFAULT_AGREEMENT = AIFTA.code


def get_criteria(code: str | None, version: int | None = None) -> OriginCriteria | None:
    """Look up an agreement's criteria by code, case-insensitively.

    With no ``version`` this returns the current rule, which is what a new
    claim should be judged against. Passing a ``version`` returns that exact
    version, which is how a decision made months ago stays explainable after
    the rule has been amended.
    """
    if not code:
        return None
    versions = REGISTRY.get(code.strip().upper())
    if not versions:
        return None
    if version is None:
        return versions[-1]
    for criteria in versions:
        if criteria.version == version:
            return criteria
    return None


def list_versions(code: str) -> list[OriginCriteria]:
    """Every version of one agreement, oldest first."""
    return list(REGISTRY.get(code.strip().upper(), []))


def register_version(criteria: OriginCriteria) -> OriginCriteria:
    """Add a new version of an existing rule.

    Amending a rule never edits the old one: a decision already taken under
    the previous version must remain reproducible. The new version becomes
    current for claims evaluated from now on.
    """
    versions = REGISTRY.setdefault(criteria.code, [])
    if any(v.version == criteria.version for v in versions):
        raise ValueError(
            f"{criteria.code} version {criteria.version} already exists"
        )
    if versions and criteria.version <= versions[-1].version:
        raise ValueError(
            f"{criteria.code} version {criteria.version} does not follow "
            f"the current version {versions[-1].version}"
        )
    versions.append(criteria)
    return criteria


def amend(
    code: str,
    *,
    value_content_min_percent: float | None = None,
    ctc_rule: ChangeInTariffClassification | None = None,
    effective_from: str,
    amendment_note: str,
    citation: str | None = None,
) -> OriginCriteria:
    """Create and register the next version of an existing rule."""
    current = get_criteria(code)
    if current is None:
        raise ValueError(f"Unknown agreement '{code}'")
    return register_version(
        replace(
            current,
            value_content_min_percent=(
                current.value_content_min_percent
                if value_content_min_percent is None
                else value_content_min_percent
            ),
            ctc_rule=current.ctc_rule if ctc_rule is None else ctc_rule,
            citation=current.citation if citation is None else citation,
            version=current.version + 1,
            effective_from=effective_from,
            amendment_note=amendment_note,
        )
    )