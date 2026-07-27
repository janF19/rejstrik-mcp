import pytest

from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    ebitda_stable,
    estimate_valuation,
    normalize_ebitda,
)
from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement


def _stmt(year, *, equity=None, ebit=None, revenue=None, net_profit=None):
    return FinancialStatement(
        period_year=year,
        canonical=CanonicalFigures(
            equity=None
            if equity is None
            else Figure(label="Vlastní kapitál", value=equity),
            operating_profit=None
            if ebit is None
            else Figure(label="Provozní VH", value=ebit),
            revenue=None if revenue is None else Figure(label="Tržby", value=revenue),
            net_profit=None
            if net_profit is None
            else Figure(label="VH za účetní období", value=net_profit),
        ),
    )


def test_valuation_methods_hand_computed():
    result = estimate_valuation(
        [
            _stmt(2022, net_profit=80.0),
            _stmt(2023, equity=800.0, ebit=100.0, revenue=2000.0, net_profit=120.0),
        ]
    )
    assert isinstance(result, ValuationEstimate)
    assert result.book_value == 800.0
    assert result.capitalized_earnings == pytest.approx(833.333, rel=1e-3)  # 100/0.12
    assert result.ev_ebit_multiple == 500.0  # 5 * 100
    assert result.price_revenue_multiple == 1000.0  # 0.5 * 2000
    assert result.value_low == 500.0
    assert result.value_high == 1000.0
    assert result.earnings_dispersion_flag is False
    assert result.caveats[-1].endswith("not investment advice.")


def test_valuation_assumption_overrides():
    result = estimate_valuation(
        [_stmt(2023, ebit=100.0, revenue=2000.0, net_profit=120.0)],
        ValuationAssumptions(ebit_multiple=6.0, capitalization_rate=0.10),
    )
    assert result.ev_ebit_multiple == 600.0
    assert result.capitalized_earnings == pytest.approx(1200.0)  # 120/0.10


def test_valuation_flags_high_earnings_dispersion():
    result = estimate_valuation(
        [_stmt(2022, net_profit=10.0), _stmt(2023, net_profit=190.0)]
    )
    assert result.earnings_dispersion_flag is True


def test_valuation_missing_inputs_stay_none():
    result = estimate_valuation([_stmt(2023)])
    assert result.book_value is None
    assert result.capitalized_earnings is None
    assert result.value_low is None
    assert result.value_high is None


def test_valuation_empty_statements_raises_valueerror():
    with pytest.raises(ValueError, match="at least one FinancialStatement"):
        estimate_valuation([])


def _stmt_da(year, *, equity=None, ebit=None, revenue=None, net_profit=None, da=None):
    return FinancialStatement(
        period_year=year,
        canonical=CanonicalFigures(
            equity=None
            if equity is None
            else Figure(label="Vlastní kapitál", value=equity),
            operating_profit=None
            if ebit is None
            else Figure(label="Provozní VH", value=ebit),
            revenue=None if revenue is None else Figure(label="Tržby", value=revenue),
            net_profit=None
            if net_profit is None
            else Figure(label="VH za účetní období", value=net_profit),
            depreciation_amortization=None
            if da is None
            else Figure(label="Úpravy hodnot v provozní oblasti", value=da),
        ),
    )


def test_statements_only_output_unchanged_by_industry_feature():
    result = estimate_valuation([_stmt_da(2023, equity=800.0, ebit=100.0)])
    assert result.ev_ebitda_multiple is None
    assert result.ebitda is None
    assert result.industry_multiple_applied is None
    assert result.caveats == [
        "Figures are in thousands of CZK as filed.",
        "Book values are not market values.",
        "Multiples are generic defaults, not industry-calibrated.",
        "Minority and marketability discounts are not applied.",
        "This is an indicative estimate, not investment advice.",
    ]


def test_industry_key_applies_ev_ebitda_when_da_present():
    from rejstrik.analysis.industry_multiples import get_industry_multiple

    result = estimate_valuation(
        [_stmt_da(2023, ebit=100.0, da=50.0)],
        industry_key="total_market_ex_financials",
        industry_reason="NACE 10 → food_processing",
    )
    im = get_industry_multiple("total_market_ex_financials")
    assert result.ebitda == 150.0
    assert result.ev_ebitda_multiple == pytest.approx(im.ev_ebitda * 150.0)
    assert result.industry_multiple_applied == "total_market_ex_financials"
    assert result.value_high == pytest.approx(im.ev_ebitda * 150.0)
    provenance = " ".join(result.caveats)
    assert "NACE 10" in provenance
    assert im.source_url in provenance
    assert str(im.firms) in provenance
    assert "generic defaults" not in provenance


def test_industry_key_without_da_does_not_apply_ebitda_multiple():
    result = estimate_valuation(
        [_stmt_da(2023, ebit=100.0)],  # no D&A
        industry_key="machinery",
    )
    assert result.ev_ebitda_multiple is None
    assert result.ev_ebit_multiple == 500.0  # generic EBIT multiple retained
    assert any("EBITDA multiple not applied" in c for c in result.caveats)


def test_normalize_ebitda_recency_weighted():
    # newest first: (2*300 + 150) / 3
    assert normalize_ebitda([300.0, 150.0]) == (250.0, "recency-weighted")


def test_normalize_ebitda_single_year():
    assert normalize_ebitda([300.0]) == (300.0, "latest-year")


def test_normalize_ebitda_skips_non_positive_years():
    assert normalize_ebitda([300.0, -20.0, 150.0]) == (250.0, "recency-weighted")


def test_normalize_ebitda_all_negative_returns_none():
    assert normalize_ebitda([-50.0, -20.0]) == (None, None)


def test_normalize_ebitda_empty_returns_none():
    assert normalize_ebitda([]) == (None, None)


def test_ebitda_stable_true_for_flat_series():
    assert ebitda_stable([100.0, 100.0]) is True


def test_ebitda_stable_false_for_volatile_series():
    assert ebitda_stable([300.0, 50.0]) is False


def test_ebitda_stable_false_for_single_year():
    assert ebitda_stable([100.0]) is False
