from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_METRICS = ("revenue", "net_profit", "total_assets", "equity")


class TrendItem(BaseModel):
    metric: str
    current: float | None = None
    prior: float | None = None
    pct_change: float | None = None


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
