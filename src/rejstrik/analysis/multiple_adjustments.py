from __future__ import annotations

from dataclasses import dataclass

from rejstrik.analysis.industry_multiples import IndustryMultiple

# Ported verbatim from obchodni-rejstrik-ai's multiple_adjustments.py, which
# calibrates them against the identical Damodaran Europe base table vendored
# in data/industry_multiples.json. The base is a *listed European* multiple;
# these factors carry it to a Czech private SME.
COUNTRY_FACTOR = 0.83
PRIVATE_LIQUIDITY_FACTOR = 0.95
SIZE_FACTOR = 1.00
QUALITY_FACTOR = 1.00

MULTIPLE_FLOOR = 3.0
MULTIPLE_CEILING = 18.0


@dataclass(frozen=True)
class AdjustedMultiple:
    base_multiple: float
    final_multiple: float
    factors: dict[str, float]
    industry_key: str
    source_industry: str
    source: str
    source_url: str
    as_of: str
    classification_confidence: str


def profitability_factor(
    revenue: float | None, ebitda: float | None, net_profit: float | None
) -> float:
    if not revenue or revenue <= 0:
        return 0.95
    ebitda_margin = (ebitda or 0.0) / revenue
    net_margin = (net_profit or 0.0) / revenue
    factor = 1.0
    if ebitda_margin >= 0.17:
        factor = 1.10
    elif ebitda_margin < 0.08:
        factor = 0.85
    if net_margin < 0.03:
        factor = min(factor, 0.90)
    elif net_margin < 0.05:
        factor = min(factor, 0.95)
    return factor


def growth_factor(revenue_growth: float | None) -> float:
    if revenue_growth is None:
        return 0.95
    if revenue_growth > 0.12:
        return 1.12
    if revenue_growth > 0.07:
        return 1.05
    if revenue_growth >= 0:
        return 1.00
    return 0.82


def cash_conversion_factor(
    ebitda: float | None, operating_cash_flow: float | None
) -> float:
    if ebitda is None or ebitda <= 0 or operating_cash_flow is None:
        return 0.95
    ratio = operating_cash_flow / ebitda
    if ratio < 0:
        return 0.75
    if ratio < 0.20:
        return 0.82
    if ratio < 0.50:
        return 0.90
    if ratio < 0.80:
        return 0.95
    return 1.00


def data_confidence_factor(classification_confidence: str) -> float:
    if classification_confidence == "high":
        return 1.00
    if classification_confidence == "medium":
        return 0.95
    return 0.85


def resolve_adjusted_multiple(
    base: IndustryMultiple,
    classification_confidence: str,
    *,
    revenue: float | None,
    ebitda: float | None,
    net_profit: float | None,
    operating_cash_flow: float | None,
    revenue_growth: float | None,
) -> AdjustedMultiple:
    factors = {
        "country": COUNTRY_FACTOR,
        "private_liquidity": PRIVATE_LIQUIDITY_FACTOR,
        "size": SIZE_FACTOR,
        "profitability": profitability_factor(revenue, ebitda, net_profit),
        "growth": growth_factor(revenue_growth),
        "cash_conversion": cash_conversion_factor(ebitda, operating_cash_flow),
        "quality": QUALITY_FACTOR,
        "data_confidence": data_confidence_factor(classification_confidence),
    }
    final = base.ev_ebitda
    for value in factors.values():
        final *= value
    final = max(MULTIPLE_FLOOR, min(MULTIPLE_CEILING, final))
    return AdjustedMultiple(
        base_multiple=base.ev_ebitda,
        final_multiple=round(final, 2),
        factors=factors,
        industry_key=base.industry_key,
        source_industry=base.source_industry,
        source=base.source,
        source_url=base.source_url,
        as_of=base.as_of,
        classification_confidence=classification_confidence,
    )
