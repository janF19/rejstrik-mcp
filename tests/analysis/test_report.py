from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement


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
