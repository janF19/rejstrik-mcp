from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp.card import render_report_markdown

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.8, equity_ratio=0.4),
    red_flags=[
        RedFlag(
            code="low_liquidity", severity="warning", message="Current ratio below 1."
        ),
        RedFlag(code="insolvency", severity="critical", message="Appears in ISIR."),
    ],
    trends=[TrendItem(metric="revenue", current=120.0, prior=100.0, pct_change=0.2)],
    yearly=[
        YearlyFigures(
            period_year=2023,
            revenue=120.0,
            net_profit=10.0,
            total_assets=200.0,
            equity=80.0,
        ),
        YearlyFigures(
            period_year=2022,
            revenue=100.0,
            net_profit=8.0,
            total_assets=180.0,
            equity=72.0,
        ),
    ],
    public_money_ratio=0.3,
    source_filing_title="Ucetni zaverka 2023",
)


def test_markdown_has_no_html_tags():
    md = render_report_markdown(REPORT)
    assert "<" not in md and ">" not in md


def test_markdown_has_header_and_source():
    md = render_report_markdown(REPORT)
    assert "Test s.r.o." in md
    assert "00006947" in md
    assert "2023" in md
    assert "Ucetni zaverka 2023" in md


def test_markdown_multi_year_table_present():
    md = render_report_markdown(REPORT)
    assert "| 2023 |" in md
    assert "| 2022 |" in md
    assert "120" in md and "100" in md


def test_markdown_ratios_have_plain_language():
    md = render_report_markdown(REPORT)
    assert "current_ratio" in md
    assert "0.8" in md
    assert "liquid assets" in md  # plain-language one-liner


def test_markdown_flags_sorted_critical_first():
    md = render_report_markdown(REPORT)
    assert md.index("Appears in ISIR.") < md.index("Current ratio below 1.")
    assert "CRITICAL" in md and "WARNING" in md


def test_markdown_public_money_line():
    md = render_report_markdown(REPORT)
    assert "30%" in md  # public money share of revenue
