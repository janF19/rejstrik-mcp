from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_METRICS = ("revenue", "net_profit", "total_assets", "equity")


def suspected_unit_mismatch(
    current: NormalizedFinancials, prior: NormalizedFinancials
) -> bool:
    """True when every headline metric present in both years moved >=100x in
    the same direction — the signature of statements read at different scales
    (CZK vs thousands of CZK), not of a real business event. Requires at
    least two comparable metrics so a genuine single-line collapse is never
    suppressed."""
    ratios: list[float] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        if (
            current_value is not None
            and prior_value is not None
            and current_value > 0
            and prior_value > 0
        ):
            ratios.append(current_value / prior_value)
    if len(ratios) < 2:
        return False
    return all(r >= 100 for r in ratios) or all(r <= 0.01 for r in ratios)


class TrendItem(BaseModel):
    metric: str
    current: float | None = None
    prior: float | None = None
    pct_change: float | None = None


class TrendSeriesItem(BaseModel):
    metric: str
    years: list[int | None] = []
    values: list[float | None] = []
    cagr: float | None = None


def compute_trends(
    current: NormalizedFinancials,
    prior: NormalizedFinancials,
) -> list[TrendItem]:
    mismatch = suspected_unit_mismatch(current, prior)
    items: list[TrendItem] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        pct_change = None
        if (
            not mismatch
            and current_value is not None
            and prior_value is not None
            and prior_value != 0
        ):
            pct_change = (current_value - prior_value) / abs(prior_value)
        items.append(
            TrendItem(
                metric=metric,
                current=current_value,
                prior=prior_value,
                pct_change=pct_change,
            )
        )
    return items


def _cagr(values: list[float | None]) -> float | None:
    if len(values) < 3:
        return None
    start, end = values[0], values[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    periods = len(values) - 1
    return (end / start) ** (1 / periods) - 1


def compute_trend_series(
    chronological: list[NormalizedFinancials],
) -> list[TrendSeriesItem]:
    """Full year-by-year series per metric. Input is oldest-first."""
    mismatch = any(
        suspected_unit_mismatch(newer, older)
        for older, newer in zip(chronological, chronological[1:])
    )
    items: list[TrendSeriesItem] = []
    for metric in _METRICS:
        values = [getattr(n, metric) for n in chronological]
        items.append(
            TrendSeriesItem(
                metric=metric,
                years=[n.period_year for n in chronological],
                values=values,
                cagr=None if mismatch else _cagr(values),
            )
        )
    return items
