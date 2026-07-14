import pytest

from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    estimate_valuation,
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
