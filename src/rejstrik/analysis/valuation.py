from statistics import fmean, pstdev

from pydantic import BaseModel, Field

from rejstrik.analysis.industry_multiples import get_industry_multiple
from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Multiples are generic defaults, not industry-calibrated.",
    "Minority and marketability discounts are not applied.",
    "This is an indicative estimate, not investment advice.",
]
_GENERIC_MULTIPLES_CAVEAT = "Multiples are generic defaults, not industry-calibrated."


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
    ebitda: float | None = None
    ev_ebitda_multiple: float | None = None
    industry_multiple_applied: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    earnings_dispersion_flag: bool = False
    assumptions: ValuationAssumptions
    caveats: list[str] = Field(default_factory=lambda: list(_CAVEATS))


def _mul(factor: float, value: float | None) -> float | None:
    if value is None:
        return None
    return factor * value


def normalize_ebitda(series: list[float]) -> tuple[float | None, str | None]:
    """Recency-weighted representative EBITDA over positive years.

    `series` is ordered newest first. Damps a single outlier year without
    discarding history."""
    positives = [v for v in (series or []) if isinstance(v, (int, float)) and v > 0]
    if not positives:
        return None, None
    if len(positives) >= 2:
        latest, prior = positives[0], positives[1]
        return (2 * latest + prior) / 3, "recency-weighted"
    return positives[0], "latest-year"


def ebitda_stable(series: list[float]) -> bool:
    """True when positive EBITDA years vary by less than 35% of their mean."""
    positives = [v for v in (series or []) if isinstance(v, (int, float)) and v > 0]
    if len(positives) < 2:
        return False
    mean = sum(positives) / len(positives)
    if mean <= 0:
        return False
    variance = sum((v - mean) ** 2 for v in positives) / len(positives)
    return (variance**0.5) / mean < 0.35


def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    industry_reason: str | None = None,
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

    caveats = list(_CAVEATS)
    ebitda: float | None = None
    ev_ebitda: float | None = None
    industry_applied: str | None = None
    if industry_key:
        im = get_industry_multiple(industry_key)
        reason = industry_reason or f"industry_key '{industry_key}'"
        if (
            latest.operating_profit is not None
            and latest.depreciation_amortization is not None
        ):
            ebitda = latest.operating_profit + latest.depreciation_amortization
            ev_ebitda = im.ev_ebitda * ebitda
            industry_applied = im.industry_key
            caveats = [c for c in caveats if c != _GENERIC_MULTIPLES_CAVEAT]
            caveats.insert(
                2,
                f"Industry EV/EBITDA {im.ev_ebitda:.1f}x applied to EBITDA {ebitda:.0f} "
                f"(chosen: {reason}); Damodaran industry '{im.source_industry}', "
                f"{im.firms} firms, as of {im.as_of}. Source: {im.source_url}",
            )
        else:
            caveats.insert(
                2,
                f"EBITDA multiple not applied for '{im.source_industry}': operating "
                f"profit and/or depreciation & amortization missing. Kept the generic "
                f"EV/EBIT multiple instead.",
            )

    methods = [
        v for v in (book_value, capitalized, ev, price, ev_ebitda) if v is not None
    ]
    value_low = min(methods) if methods else None
    value_high = max(methods) if methods else None

    return ValuationEstimate(
        book_value=book_value,
        capitalized_earnings=capitalized,
        ev_ebit_multiple=ev,
        price_revenue_multiple=price,
        ebitda=ebitda,
        ev_ebitda_multiple=ev_ebitda,
        industry_multiple_applied=industry_applied,
        value_low=value_low,
        value_high=value_high,
        earnings_dispersion_flag=dispersion_flag,
        assumptions=assumptions,
        caveats=caveats,
    )
