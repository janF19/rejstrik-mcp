import pytest

from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.vat import VatStatus
from rejstrik.service import analyze_statements


def _statement(year: int, revenue: float) -> FinancialStatement:
    return FinancialStatement(
        company_name="Budvar",
        ico="00514152",
        period_year=year,
        currency="CZK",
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def _no_insolvency(ico):
    return InsolvencyStatus(ico=ico, checked=True, in_insolvency=False)


def _clean_vat(ico):
    return VatStatus(ico=ico, is_vat_payer=True, dic="CZ00514152", is_unreliable=False)


def test_analyze_statements_single_year(monkeypatch):
    report = analyze_statements(
        [_statement(2024, 1000.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert report.period_year == 2024
    assert report.trends == []
    assert report.ico == "00514152"


def test_analyze_statements_two_years_computes_trends():
    report = analyze_statements(
        [_statement(2023, 800.0), _statement(2024, 1000.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert report.period_year == 2024
    revenue = next(t for t in report.trends if t.metric == "revenue")
    assert revenue.current == 1000.0
    assert revenue.prior == 800.0
    assert revenue.pct_change == pytest.approx(0.25)


def test_analyze_statements_without_ico_skips_registry_checks():
    stmt = _statement(2024, 1000.0)
    stmt.ico = None

    def boom(ico):
        raise AssertionError("registry check must not run without an ICO")

    report = analyze_statements([stmt], insolvency_check=boom, vat_check=boom)
    assert report.ico is None


def test_analyze_statements_empty_raises():
    with pytest.raises(ValueError):
        analyze_statements([])


def test_analyze_statements_public_money_flag():
    from rejstrik.registry.subsidies import SubsidyReport
    from rejstrik.registry.contracts import ContractReport

    stmt = _statement(2024, 1000.0)  # revenue 1000 via income_statement helper
    report = analyze_statements(
        [stmt],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
        subsidy_check=lambda ico: SubsidyReport(ico=ico, total_amount=400.0, count=2),
        contract_check=lambda ico: ContractReport(ico=ico, total_value=200.0, count=1),
    )
    assert any(f.code == "public_money_dependence" for f in report.red_flags)
