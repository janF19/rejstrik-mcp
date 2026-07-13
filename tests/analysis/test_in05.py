import pytest

from rejstrik.analysis.in05 import IN05Result, compute_in05
from rejstrik.analysis.normalize import NormalizedFinancials


def _full(**overrides) -> NormalizedFinancials:
    base = dict(
        total_assets=1000.0,
        total_liabilities=500.0,
        operating_profit=100.0,
        interest_expense=20.0,
        revenue=2000.0,
        current_assets=600.0,
        current_liabilities=300.0,
    )
    base.update(overrides)
    return NormalizedFinancials(**base)


def test_in05_hand_computed_grey_zone():
    result = compute_in05(_full())
    # 0.13*2 + 0.04*5 + 3.97*0.1 + 0.21*2 + 0.09*2 = 1.457
    assert result.value == pytest.approx(1.457)
    assert result.zone == "grey"
    assert result.missing_inputs == []


def test_in05_ebit_interest_cap_pushes_value_creating():
    # EBIT/U = 100/1 = 100 -> capped at 9 -> 0.04*9 = 0.36
    result = compute_in05(_full(interest_expense=1.0))
    assert result.value == pytest.approx(1.617)
    assert result.zone == "value_creating"


def test_in05_zero_interest_uses_cap():
    result = compute_in05(_full(interest_expense=0.0))
    assert result.value == pytest.approx(1.617)


def test_in05_distress_zone():
    result = compute_in05(
        _full(operating_profit=-100.0, revenue=100.0, total_liabilities=2000.0)
    )
    assert result.value < 0.9
    assert result.zone == "distress"


def test_in05_missing_input_returns_miss_list():
    result = compute_in05(_full(interest_expense=None))
    assert isinstance(result, IN05Result)
    assert result.value is None
    assert result.zone is None
    assert "interest_expense" in result.missing_inputs


def test_in05_zero_denominator_reported():
    result = compute_in05(_full(total_assets=0.0))
    assert result.value is None
    assert "total_assets" in result.missing_inputs
