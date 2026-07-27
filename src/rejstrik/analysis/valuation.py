from pydantic import BaseModel, Field

from rejstrik.analysis.industry_multiples import (
    FALLBACK_INDUSTRY_KEY,
    get_industry_multiple,
)
from rejstrik.analysis.multiple_adjustments import resolve_adjusted_multiple
from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_DISCLAIMER = "This is an indicative estimate, not investment advice."
_BASE_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Minority and marketability discounts are not applied.",
    _DISCLAIMER,
]
_CONFIDENCE_BAND = {"high": 0.15, "medium": 0.25, "low": 0.40}
_ASSET_BAND = 0.15


class ValuationAssumptions(BaseModel):
    """Caller overrides. Leave unset to use the sector-derived multiple."""

    ebitda_multiple: float | None = None
    ev_sales_anchor_multiple: float | None = None
    dispersion_threshold: float = 0.5


class ValuationEstimate(BaseModel):
    point_estimate: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    primary_method: str = "insufficient_data"
    # Data sufficiency / sector fit, not industry-classification certainty.
    confidence: str = "low"
    book_value: float | None = None
    ebitda: float | None = None
    ebitda_basis: str | None = None
    base_multiple: float | None = None
    final_multiple: float | None = None
    adjustment_factors: dict[str, float] = Field(default_factory=dict)
    industry_key: str | None = None
    source_industry: str | None = None
    sales_anchor_applied: bool = False
    earnings_dispersion_flag: bool = False
    as_of_year: int | None = None
    assumptions: ValuationAssumptions
    caveats: list[str] = Field(default_factory=lambda: list(_BASE_CAVEATS))


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


def _ebitda_of(normalized) -> float | None:
    if normalized.operating_profit is None:
        return None
    return normalized.operating_profit + (normalized.depreciation_amortization or 0.0)


def _revenue_growth(ordered) -> float | None:
    if len(ordered) < 2:
        return None
    latest, prior = ordered[0].revenue, ordered[1].revenue
    if latest is None or prior is None or prior <= 0:
        return None
    return latest / prior - 1


def _band(point: float, confidence: str) -> tuple[float, float]:
    spread = _CONFIDENCE_BAND.get(confidence, 0.40)
    return point * (1 - spread), point * (1 + spread)


def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    industry_reason: str | None = None,
    classification_confidence: str | None = None,
) -> ValuationEstimate:
    """Indicative enterprise value from a sector multiple adjusted for a Czech
    private SME. One primary method: EV/EBITDA for going concerns, net assets
    as fallback."""
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

    series = [e for e in (_ebitda_of(n) for n in ordered) if e is not None]
    representative, basis = normalize_ebitda(series)

    net_assets = None
    if latest.total_assets is not None and latest.total_liabilities is not None:
        net_assets = max(0.0, latest.total_assets - latest.total_liabilities)

    earnings = [n.net_profit for n in normalized if n.net_profit is not None]
    dispersion_flag = False
    if len(earnings) > 1:
        mean = sum(earnings) / len(earnings)
        if mean != 0:
            variance = sum((e - mean) ** 2 for e in earnings) / len(earnings)
            dispersion_flag = (variance**0.5) / abs(
                mean
            ) > assumptions.dispersion_threshold

    base = get_industry_multiple(industry_key)
    specific_sector = base.industry_key != FALLBACK_INDUSTRY_KEY
    confidence_in = classification_confidence or ("high" if industry_key else "low")
    adjusted = resolve_adjusted_multiple(
        base,
        confidence_in,
        revenue=latest.revenue,
        ebitda=representative,
        net_profit=latest.net_profit,
        operating_cash_flow=latest.operating_cash_flow,
        revenue_growth=_revenue_growth(ordered),
    )

    caveats = list(_BASE_CAVEATS)

    if representative is not None and representative > 0:
        multiple_caveats = list(_BASE_CAVEATS)
        multiple_caveats.insert(
            1,
            f"Base EV/EBITDA {adjusted.base_multiple:.2f}x for "
            f"'{adjusted.source_industry}' adjusted to {adjusted.final_multiple:.2f}x "
            f"for a Czech private company. Damodaran {base.region}, {base.firms} firms, "
            f"as of {base.as_of}. Source: {base.source_url}",
        )
        if industry_reason:
            multiple_caveats.insert(2, f"Industry chosen: {industry_reason}.")
        multiple = (
            assumptions.ebitda_multiple
            if assumptions.ebitda_multiple is not None
            else adjusted.final_multiple
        )
        point = representative * multiple
        anchor_applied = False
        anchor_multiple = assumptions.ev_sales_anchor_multiple
        if anchor_multiple and latest.revenue and latest.revenue > 0:
            anchor = latest.revenue * anchor_multiple
            if point > anchor * 1.25:
                point = anchor * 0.70 + point * 0.30
                anchor_applied = True

        positives = [v for v in series if v > 0]
        if len(positives) >= 2:
            confidence = (
                "high" if (ebitda_stable(series) and specific_sector) else "medium"
            )
        else:
            confidence = "medium" if specific_sector else "low"

        low, high = _band(point, confidence)
        return ValuationEstimate(
            point_estimate=point,
            value_low=low,
            value_high=high,
            primary_method="multiples",
            confidence=confidence,
            book_value=book_value,
            ebitda=representative,
            ebitda_basis=basis,
            base_multiple=adjusted.base_multiple,
            final_multiple=multiple,
            adjustment_factors=adjusted.factors,
            industry_key=adjusted.industry_key,
            source_industry=adjusted.source_industry,
            sales_anchor_applied=anchor_applied,
            earnings_dispersion_flag=dispersion_flag,
            as_of_year=latest.period_year,
            assumptions=assumptions,
            caveats=multiple_caveats,
        )

    if net_assets is not None and net_assets > 0:
        return ValuationEstimate(
            point_estimate=net_assets,
            value_low=net_assets * (1 - _ASSET_BAND),
            value_high=net_assets * (1 + _ASSET_BAND),
            primary_method="asset",
            confidence="low",
            book_value=book_value,
            ebitda=representative,
            ebitda_basis=basis,
            earnings_dispersion_flag=dispersion_flag,
            as_of_year=latest.period_year,
            assumptions=assumptions,
            caveats=caveats,
        )

    return ValuationEstimate(
        primary_method="insufficient_data",
        confidence="low",
        book_value=book_value,
        as_of_year=latest.period_year,
        assumptions=assumptions,
        caveats=caveats,
    )
