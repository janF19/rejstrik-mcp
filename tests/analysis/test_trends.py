import pytest

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.trends import (
    TrendItem,
    TrendSeriesItem,
    compute_trend_series,
    compute_trends,
    suspected_unit_mismatch,
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


def test_uniform_thousandfold_shift_suppresses_pct_change():
    cur = NormalizedFinancials(
        revenue=3_647_852.0,
        net_profit=356_318.0,
        total_assets=5_408_329.0,
        equity=4_398_302.0,
    )
    prior = NormalizedFinancials(
        revenue=3_666_523_000.0,
        net_profit=371_051_000.0,
        total_assets=5_754_734_000.0,
        equity=4_549_753_000.0,
    )
    assert suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert all(t.pct_change is None for t in items.values())
    # raw values stay visible — suppression must be honest, not silent
    assert items["revenue"].current == 3_647_852.0
    assert items["revenue"].prior == 3_666_523_000.0


def test_single_metric_thousandfold_move_is_not_suppressed():
    cur = NormalizedFinancials(revenue=1_000.0)
    prior = NormalizedFinancials(revenue=1_000_000.0)
    assert not suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == pytest.approx(-0.999)


def test_large_but_divergent_moves_are_not_suppressed():
    cur = NormalizedFinancials(revenue=5_000.0, net_profit=50.0)
    prior = NormalizedFinancials(revenue=1_000.0, net_profit=200.0)
    assert not suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == pytest.approx(4.0)


def test_series_cagr_suppressed_on_adjacent_unit_mismatch():
    consistent = NormalizedFinancials(
        period_year=2021, revenue=100.0, total_assets=200.0
    )
    also_consistent = NormalizedFinancials(
        period_year=2022, revenue=120.0, total_assets=210.0
    )
    scaled_up = NormalizedFinancials(
        period_year=2023, revenue=144_000.0, total_assets=220_000.0
    )
    series = compute_trend_series([consistent, also_consistent, scaled_up])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None
    assert revenue.values == [100.0, 120.0, 144_000.0]
