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

from dataclasses import dataclass
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


REGISTRY: dict[str, OriginCriteria] = {
    c.code: c for c in (AIFTA, SAFTA_NON_LDC, SAFTA_LDC)
}

#: Used when the claim does not name an agreement.
DEFAULT_AGREEMENT = AIFTA.code


def get_criteria(code: str | None) -> OriginCriteria | None:
    """Look up an agreement's criteria by code, case-insensitively."""
    if not code:
        return None
    return REGISTRY.get(code.strip().upper())
