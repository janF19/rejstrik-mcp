from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials


class Ratios(BaseModel):
    current_ratio: float | None = None
    equity_ratio: float | None = None
    debt_to_equity: float | None = None
    net_margin: float | None = None
    return_on_equity: float | None = None
    quick_ratio: float | None = None
    return_on_assets: float | None = None
    asset_turnover: float | None = None
    interest_coverage: float | None = None
    operating_margin: float | None = None
    ocf_to_liabilities: float | None = None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_ratios(financials: NormalizedFinancials) -> Ratios:
    if financials.current_assets is not None and financials.inventories is not None:
        quick_num: float | None = financials.current_assets - financials.inventories
    else:
        quick_num = None
    return Ratios(
        current_ratio=_div(
            financials.current_assets,
            financials.current_liabilities,
        ),
        equity_ratio=_div(financials.equity, financials.total_assets),
        debt_to_equity=_div(financials.total_liabilities, financials.equity),
        net_margin=_div(financials.net_profit, financials.revenue),
        return_on_equity=_div(financials.net_profit, financials.equity),
        quick_ratio=_div(quick_num, financials.current_liabilities),
        return_on_assets=_div(financials.net_profit, financials.total_assets),
        asset_turnover=_div(financials.revenue, financials.total_assets),
        interest_coverage=_div(
            financials.operating_profit, financials.interest_expense
        ),
        operating_margin=_div(financials.operating_profit, financials.revenue),
        ocf_to_liabilities=_div(
            financials.operating_cash_flow, financials.total_liabilities
        ),
    )
