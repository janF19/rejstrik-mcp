from typing import Literal

from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_EBIT_INTEREST_CAP = 9.0

_REQUIRED = (
    "total_assets",
    "total_liabilities",
    "operating_profit",
    "interest_expense",
    "revenue",
    "current_assets",
    "current_liabilities",
)

# Denominators that must be non-zero to form the required ratios.
_NONZERO_DENOMINATORS = ("total_assets", "total_liabilities", "current_liabilities")


class IN05Result(BaseModel):
    value: float | None = None
    zone: Literal["distress", "grey", "value_creating"] | None = None
    missing_inputs: list[str] = []


def compute_in05(financials: NormalizedFinancials) -> IN05Result:
    missing = [name for name in _REQUIRED if getattr(financials, name) is None]
    if missing:
        return IN05Result(missing_inputs=missing)

    a = financials.total_assets
    cz = financials.total_liabilities
    ebit = financials.operating_profit
    u = financials.interest_expense
    vyn = financials.revenue
    oa = financials.current_assets
    kz = financials.current_liabilities

    zero_denominators = [
        name for name in _NONZERO_DENOMINATORS if getattr(financials, name) == 0
    ]
    if zero_denominators:
        return IN05Result(missing_inputs=zero_denominators)

    ebit_interest = _EBIT_INTEREST_CAP if u == 0 else min(ebit / u, _EBIT_INTEREST_CAP)
    value = (
        0.13 * (a / cz)
        + 0.04 * ebit_interest
        + 3.97 * (ebit / a)
        + 0.21 * (vyn / a)
        + 0.09 * (oa / kz)
    )
    if value < 0.9:
        zone: Literal["distress", "grey", "value_creating"] = "distress"
    elif value > 1.6:
        zone = "value_creating"
    else:
        zone = "grey"
    return IN05Result(value=value, zone=zone)
