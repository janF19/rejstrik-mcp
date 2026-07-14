from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.contracts import ContractReport
from rejstrik.registry.subsidies import SubsidyReport
from rejstrik.service import analyze_statements


def test_report_model_holds_all_analysis_layers():
    report = CompanyFinancialReport(
        company_name="Test s.r.o.",
        ico="00006947",
        period_year=2023,
        currency="CZK",
        statement=FinancialStatement(period_year=2023),
        normalized=NormalizedFinancials(total_assets=1000.0),
        ratios=Ratios(equity_ratio=0.4),
        red_flags=[
            RedFlag(
                code="low_liquidity",
                severity="warning",
                message="Current ratio below 1.",
            )
        ],
        trends=[
            TrendItem(metric="revenue", current=1200.0, prior=1000.0, pct_change=0.2)
        ],
        source_filing_title="Účetní závěrka 2023",
    )
    assert report.normalized.total_assets == 1000.0
    assert report.ratios.equity_ratio == 0.4
    assert report.red_flags[0].code == "low_liquidity"
    assert report.trends[0].metric == "revenue"


def _stmt(year, revenue, equity):
    return FinancialStatement(
        company_name="Y s.r.o.",
        ico="00006947",
        period_year=year,
        currency="CZK",
        balance_sheet=[Figure(label="Vlastní kapitál", value=equity)],
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def test_report_yearly_is_current_first():
    report = analyze_statements([_stmt(2022, 100.0, 40.0), _stmt(2023, 120.0, 50.0)])
    assert [y.period_year for y in report.yearly] == [2023, 2022]
    assert isinstance(report.yearly[0], YearlyFigures)
    assert report.yearly[0].revenue == 120.0
    assert report.yearly[1].equity == 40.0


def test_report_public_money_populated_when_checks_supplied():
    report = analyze_statements(
        [_stmt(2023, 1000.0, 500.0)],
        ico="00006947",
        insolvency_check=lambda ico: _NoInsolvency(),
        vat_check=lambda ico: _ReliableVat(),
        subsidy_check=lambda ico: SubsidyReport(ico=ico, total_amount=200.0),
        contract_check=lambda ico: ContractReport(ico=ico, total_value=50.0),
    )
    assert report.subsidies_total == 200.0
    assert report.contracts_total == 50.0
    assert report.public_money_ratio == 0.25


def test_report_public_money_none_without_checks():
    report = analyze_statements([_stmt(2023, 1000.0, 500.0)])
    assert report.subsidies_total is None
    assert report.contracts_total is None
    assert report.public_money_ratio is None


class _NoInsolvency:
    checked = True
    in_insolvency = False


class _ReliableVat:
    is_unreliable = False
