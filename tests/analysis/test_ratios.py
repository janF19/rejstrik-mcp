from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios, compute_ratios


def test_computes_all_ratios():
    n = NormalizedFinancials(
        total_assets=1000.0,
        equity=400.0,
        current_assets=600.0,
        current_liabilities=300.0,
        total_liabilities=600.0,
        revenue=2000.0,
        net_profit=150.0,
    )
    r = compute_ratios(n)
    assert isinstance(r, Ratios)
    assert r.current_ratio == 2.0
    assert r.equity_ratio == 0.4
    assert r.debt_to_equity == 1.5
    assert r.net_margin == 0.075
    assert r.return_on_equity == 0.375


def test_missing_inputs_yield_none():
    r = compute_ratios(NormalizedFinancials(equity=400.0))
    assert r.current_ratio is None
    assert r.return_on_equity is None


def test_zero_denominator_is_none():
    r = compute_ratios(
        NormalizedFinancials(current_assets=10.0, current_liabilities=0.0)
    )
    assert r.current_ratio is None
