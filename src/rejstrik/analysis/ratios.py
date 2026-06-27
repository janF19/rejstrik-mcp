from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials


class Ratios(BaseModel):
    current_ratio: float | None = None
    equity_ratio: float | None = None
    debt_to_equity: float | None = None
    net_margin: float | None = None
    return_on_equity: float | None = None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_ratios(financials: NormalizedFinancials) -> Ratios:
    return Ratios(
        current_ratio=_div(
            financials.current_assets,
            financials.current_liabilities,
        ),
        equity_ratio=_div(financials.equity, financials.total_assets),
        debt_to_equity=_div(financials.total_liabilities, financials.equity),
        net_margin=_div(financials.net_profit, financials.revenue),
        return_on_equity=_div(financials.net_profit, financials.equity),
    )
