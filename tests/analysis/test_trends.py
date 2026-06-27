from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.trends import TrendItem, compute_trends


def test_pct_change_per_metric():
    cur = NormalizedFinancials(
        revenue=1200.0,
        net_profit=100.0,
        total_assets=2000.0,
        equity=800.0,
    )
    prior = NormalizedFinancials(
        revenue=1000.0,
        net_profit=200.0,
        total_assets=2000.0,
        equity=400.0,
    )
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == 0.2
    assert items["net_profit"].pct_change == -0.5
    assert items["total_assets"].pct_change == 0.0
    assert items["equity"].pct_change == 1.0
    assert isinstance(items["revenue"], TrendItem)


def test_missing_or_zero_prior_yields_none():
    cur = NormalizedFinancials(revenue=1200.0, equity=10.0)
    prior = NormalizedFinancials(revenue=None, equity=0.0)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change is None
    assert items["equity"].pct_change is None
