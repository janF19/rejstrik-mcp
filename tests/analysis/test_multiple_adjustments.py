import pytest

from rejstrik.analysis.industry_multiples import get_industry_multiple
from rejstrik.analysis.multiple_adjustments import (
    AdjustedMultiple,
    cash_conversion_factor,
    data_confidence_factor,
    growth_factor,
    profitability_factor,
    resolve_adjusted_multiple,
)


@pytest.mark.parametrize(
    "revenue, ebitda, net_profit, expected",
    [
        (1000.0, 200.0, 100.0, 1.10),  # EBITDA margin .20 >= .17
        (1000.0, 50.0, 40.0, 0.85),  # EBITDA margin .05 < .08
        (1000.0, 120.0, 100.0, 1.00),  # between thresholds
        (1000.0, 200.0, 20.0, 0.90),  # net margin .02 < .03 caps 1.10 -> .90
        (1000.0, 200.0, 40.0, 0.95),  # net margin .04 < .05 caps 1.10 -> .95
        (None, 200.0, 100.0, 0.95),  # no revenue
        (0.0, 200.0, 100.0, 0.95),  # zero revenue
    ],
)
def test_profitability_factor(revenue, ebitda, net_profit, expected):
    assert profitability_factor(revenue, ebitda, net_profit) == expected


@pytest.mark.parametrize(
    "growth, expected",
    [
        (0.15, 1.12),
        (0.10, 1.05),
        (0.03, 1.00),
        (0.0, 1.00),
        (-0.05, 0.82),
        (None, 0.95),
    ],
)
def test_growth_factor(growth, expected):
    assert growth_factor(growth) == expected


@pytest.mark.parametrize(
    "ebitda, ocf, expected",
    [
        (100.0, 90.0, 1.00),
        (100.0, 60.0, 0.95),
        (100.0, 30.0, 0.90),
        (100.0, 10.0, 0.82),
        (100.0, -5.0, 0.75),
        (None, 50.0, 0.95),
        (-10.0, 50.0, 0.95),
        (100.0, None, 0.95),
    ],
)
def test_cash_conversion_factor(ebitda, ocf, expected):
    assert cash_conversion_factor(ebitda, ocf) == expected


@pytest.mark.parametrize(
    "confidence, expected",
    [("high", 1.00), ("medium", 0.95), ("low", 0.85), ("nonsense", 0.85)],
)
def test_data_confidence_factor(confidence, expected):
    assert data_confidence_factor(confidence) == expected


def test_robe_chain_matches_spec():
    """ROBE lighting 2023, agent-classified as electrical_equipment."""
    base = get_industry_multiple("electrical_equipment")
    adjusted = resolve_adjusted_multiple(
        base,
        "high",
        revenue=3_886_882.0,
        ebitda=965_188.0,
        net_profit=752_222.0,
        operating_cash_flow=362_734.0,
        revenue_growth=None,
    )
    assert isinstance(adjusted, AdjustedMultiple)
    assert adjusted.base_multiple == pytest.approx(18.9445, rel=1e-4)
    assert adjusted.final_multiple == 14.05
    assert adjusted.factors == {
        "country": 0.83,
        "private_liquidity": 0.95,
        "size": 1.00,
        "profitability": 1.10,
        "growth": 0.95,
        "cash_conversion": 0.90,
        "quality": 1.00,
        "data_confidence": 1.00,
    }
    assert adjusted.source_industry == "Electrical Equipment"
    assert adjusted.classification_confidence == "high"


def test_multiple_clamped_to_ceiling():
    base = get_industry_multiple("electrical_equipment")  # 18.94x
    adjusted = resolve_adjusted_multiple(
        base,
        "high",
        revenue=1000.0,
        ebitda=250.0,  # margin .25 -> 1.10
        net_profit=200.0,
        operating_cash_flow=225.0,  # ocf/ebitda .9 -> 1.00
        revenue_growth=0.20,  # -> 1.12
    )
    assert adjusted.final_multiple == 18.0


def test_multiple_clamped_to_floor():
    base = get_industry_multiple("telecom_services")  # ~7.19x
    adjusted = resolve_adjusted_multiple(
        base,
        "low",
        revenue=1000.0,
        ebitda=50.0,  # margin .05 -> 0.85
        net_profit=10.0,
        operating_cash_flow=-5.0,  # -> 0.75
        revenue_growth=-0.10,  # -> 0.82
    )
    assert adjusted.final_multiple == 3.0


def test_provenance_carried_from_base():
    base = get_industry_multiple("machinery")
    adjusted = resolve_adjusted_multiple(
        base,
        "medium",
        revenue=1000.0,
        ebitda=200.0,
        net_profit=100.0,
        operating_cash_flow=180.0,
        revenue_growth=0.05,
    )
    assert adjusted.industry_key == "machinery"
    assert adjusted.source_url == base.source_url
    assert adjusted.as_of == base.as_of
