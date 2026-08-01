import pytest

from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ebitda_stable,
    estimate_valuation,
    normalize_ebitda,
)
from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement


def _fig(label, value):
    return Figure(label=label, value=value)


def _statement(
    year=2023,
    revenue=3_886_882.0,
    operating_profit=903_044.0,
    net_profit=752_222.0,
    da=62_144.0,
    ocf=362_734.0,
    total_assets=3_541_478.0,
    total_liabilities=499_199.0,
    equity=3_039_871.0,
):
    return FinancialStatement(
        company_name="ROBE lighting s.r.o.",
        ico="64088791",
        period_year=year,
        unit="thousands_czk",
        canonical=CanonicalFigures(
            total_assets=_fig("Aktiva celkem", total_assets),
            equity=_fig("Vlastní kapitál", equity),
            total_liabilities=_fig("Cizí zdroje", total_liabilities),
            revenue=_fig("Tržby", revenue),
            operating_profit=_fig("Provozní VH", operating_profit),
            net_profit=_fig("VH za účetní období", net_profit),
            operating_cash_flow=_fig("Provozní CF", ocf),
            depreciation_amortization=_fig("Odpisy", da),
        ),
    )


def test_robe_single_year_point_estimate():
    result = estimate_valuation(
        [_statement()],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    assert result.primary_method == "multiples"
    assert result.ebitda == pytest.approx(965_188.0)
    assert result.ebitda_basis == "latest-year"
    assert result.final_multiple == 14.05
    assert result.base_multiple == pytest.approx(18.9445, rel=1e-4)
    assert result.point_estimate == pytest.approx(965_188.0 * 14.05)
    # one filed year + specific sector -> medium -> +-25%
    assert result.confidence == "medium"
    assert result.value_low == pytest.approx(result.point_estimate * 0.75)
    assert result.value_high == pytest.approx(result.point_estimate * 1.25)


def test_two_stable_years_give_high_confidence_and_narrow_band():
    latest = _statement(year=2023)
    prior = _statement(
        year=2022, operating_profit=880_000.0, da=60_000.0, revenue=3_600_000.0
    )
    result = estimate_valuation(
        [latest, prior],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    assert result.ebitda_basis == "recency-weighted"
    assert result.confidence == "high"
    assert result.value_low == pytest.approx(result.point_estimate * 0.85)
    assert result.value_high == pytest.approx(result.point_estimate * 1.15)


def test_fallback_sector_lowers_confidence():
    result = estimate_valuation([_statement()])  # no industry key at all
    assert result.confidence == "low"
    assert result.value_low == pytest.approx(result.point_estimate * 0.60)
    assert result.value_high == pytest.approx(result.point_estimate * 1.40)


def test_negative_ebitda_falls_back_to_net_assets():
    result = estimate_valuation(
        [_statement(operating_profit=-500_000.0, da=1_000.0, net_profit=-400_000.0)],
        industry_key="electrical_equipment",
    )
    assert result.primary_method == "asset"
    assert result.point_estimate == pytest.approx(3_541_478.0 - 499_199.0)
    assert result.confidence == "low"
    assert result.value_low == pytest.approx(result.point_estimate * 0.85)
    assert result.value_high == pytest.approx(result.point_estimate * 1.15)
    assert result.final_multiple is None


def test_insufficient_data_when_nothing_usable():
    statement = FinancialStatement(
        company_name="Prázdná s.r.o.",
        ico="00000000",
        period_year=2023,
        unit="thousands_czk",
        canonical=CanonicalFigures(),
    )
    result = estimate_valuation([statement])
    assert result.primary_method == "insufficient_data"
    assert result.point_estimate is None
    assert result.value_low is None
    assert result.value_high is None


def test_explicit_multiple_override_wins():
    result = estimate_valuation(
        [_statement()],
        assumptions=ValuationAssumptions(ebitda_multiple=8.0),
        industry_key="electrical_equipment",
    )
    assert result.final_multiple == 8.0
    assert result.point_estimate == pytest.approx(965_188.0 * 8.0)


def test_sales_anchor_blends_down_an_inflated_ebitda_value():
    # anchor = revenue * 1.0 = 1000; ebitda value = 200 * 18 = 3600 > 1250
    # blended = 0.7 * 1000 + 0.3 * 3600 = 1780
    result = estimate_valuation(
        [
            _statement(
                revenue=1000.0,
                operating_profit=200.0,
                net_profit=180.0,
                da=0.0,
                ocf=190.0,
                total_assets=900.0,
                total_liabilities=100.0,
                equity=800.0,
            )
        ],
        assumptions=ValuationAssumptions(
            ebitda_multiple=18.0, ev_sales_anchor_multiple=1.0
        ),
        industry_key="electrical_equipment",
    )
    assert result.sales_anchor_applied is True
    assert result.point_estimate == pytest.approx(0.7 * 1000.0 + 0.3 * 3600.0)


def test_removed_legacy_fields_are_gone():
    result = estimate_valuation([_statement()], industry_key="machinery")
    for gone in ("capitalized_earnings", "ev_ebit_multiple", "price_revenue_multiple"):
        assert not hasattr(result, gone)


def test_caveats_keep_damodaran_provenance_and_disclaimer():
    result = estimate_valuation(
        [_statement()],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    joined = " ".join(result.caveats)
    assert "Damodaran" in joined
    assert "Electrical Equipment" in joined
    assert "not investment advice" in joined.lower()


def test_empty_statements_raises_valueerror():
    with pytest.raises(ValueError):
        estimate_valuation([])


# --- Kept from the old five-method suite: still-relevant behavior, adapted to
# the new fixtures/branches since the old minimal `_stmt` fixture (net_profit
# only, no operating figures) now lands in `insufficient_data`, which doesn't
# carry the dispersion flag.


def test_valuation_flags_high_earnings_dispersion():
    latest = _statement(year=2023, net_profit=10_000.0)
    prior = _statement(year=2022, net_profit=700_000.0)
    result = estimate_valuation([latest, prior], industry_key="electrical_equipment")
    assert result.primary_method == "multiples"
    assert result.earnings_dispersion_flag is True


def test_valuation_empty_statements_raises_valueerror():
    with pytest.raises(ValueError, match="at least one FinancialStatement"):
        estimate_valuation([])


# --- Task 2: normalize_ebitda / ebitda_stable (unchanged)


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
