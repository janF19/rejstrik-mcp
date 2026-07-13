from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_METRICS = ("revenue", "net_profit", "total_assets", "equity")


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
    items: list[TrendItem] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        pct_change = None
        if current_value is not None and prior_value is not None and prior_value != 0:
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
    items: list[TrendSeriesItem] = []
    for metric in _METRICS:
        values = [getattr(n, metric) for n in chronological]
        items.append(
            TrendSeriesItem(
                metric=metric,
                years=[n.period_year for n in chronological],
                values=values,
                cagr=_cagr(values),
            )
        )
    return items
