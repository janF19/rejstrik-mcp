import pytest

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.trends import (
    TrendItem,
    TrendSeriesItem,
    compute_trend_series,
    compute_trends,
)


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


def _n(year, revenue):
    return NormalizedFinancials(period_year=year, revenue=revenue)


def test_series_lists_years_and_values_oldest_first():
    series = compute_trend_series([_n(2021, 100.0), _n(2022, 120.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert isinstance(revenue, TrendSeriesItem)
    assert revenue.years == [2021, 2022, 2023]
    assert revenue.values == [100.0, 120.0, 144.0]


def test_series_cagr_three_years_positive_endpoints():
    series = compute_trend_series([_n(2021, 100.0), _n(2022, 120.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr == pytest.approx(0.2)  # (144/100)**(1/2) - 1


def test_series_cagr_none_for_two_years():
    series = compute_trend_series([_n(2022, 100.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None


def test_series_cagr_none_for_nonpositive_endpoint():
    series = compute_trend_series([_n(2021, -10.0), _n(2022, 50.0), _n(2023, 100.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None
