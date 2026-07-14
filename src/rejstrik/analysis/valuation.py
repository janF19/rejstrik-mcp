from statistics import fmean, pstdev

from pydantic import BaseModel, Field

from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Multiples are generic defaults, not industry-calibrated.",
    "Minority and marketability discounts are not applied.",
    "This is an indicative estimate, not investment advice.",
]


class ValuationAssumptions(BaseModel):
    capitalization_rate: float = 0.12
    ebit_multiple: float = 5.0
    revenue_multiple: float = 0.5
    dispersion_threshold: float = 0.5


class ValuationEstimate(BaseModel):
    book_value: float | None = None
    capitalized_earnings: float | None = None
    ev_ebit_multiple: float | None = None
    price_revenue_multiple: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    earnings_dispersion_flag: bool = False
    assumptions: ValuationAssumptions
    caveats: list[str] = Field(default_factory=lambda: list(_CAVEATS))


def _mul(factor: float, value: float | None) -> float | None:
    if value is None:
        return None
    return factor * value


def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
) -> ValuationEstimate:
    assumptions = assumptions or ValuationAssumptions()
    if not statements:
        raise ValueError(
            "statements must contain at least one FinancialStatement "
            "(extract it from the PDF returned by get_filing)"
        )
    normalized = [normalize(s) for s in statements]
    ordered = sorted(
        normalized, key=lambda n: (n.period_year is None, -(n.period_year or 0))
    )
    latest = ordered[0]

    book_value = latest.equity
    ev = _mul(assumptions.ebit_multiple, latest.operating_profit)
    price = _mul(assumptions.revenue_multiple, latest.revenue)

    earnings = [n.net_profit for n in normalized if n.net_profit is not None]
    capitalized = None
    dispersion_flag = False
    if earnings and assumptions.capitalization_rate != 0:
        mean = fmean(earnings)
        capitalized = mean / assumptions.capitalization_rate
        if len(earnings) > 1 and mean != 0:
            cv = pstdev(earnings) / abs(mean)
            dispersion_flag = cv > assumptions.dispersion_threshold

    methods = [v for v in (book_value, capitalized, ev, price) if v is not None]
    value_low = min(methods) if methods else None
    value_high = max(methods) if methods else None

    return ValuationEstimate(
        book_value=book_value,
        capitalized_earnings=capitalized,
        ev_ebit_multiple=ev,
        price_revenue_multiple=price,
        value_low=value_low,
        value_high=value_high,
        earnings_dispersion_flag=dispersion_flag,
        assumptions=assumptions,
    )
