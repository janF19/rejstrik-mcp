from rejstrik.analysis.in05 import IN05Result
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp.card import render_report_card, render_report_markdown

REPORT = CompanyFinancialReport(
    company_name="Test & Co s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.5, equity_ratio=0.4),
    red_flags=[
        RedFlag(
            code="low_liquidity",
            severity="warning",
            message="Current ratio below 1.",
        )
    ],
    source_filing_title="Ucetni zaverka 2023",
)


def test_card_is_self_contained_html():
    html = render_report_card(REPORT)
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "<style" in html
    assert "http://" not in html and "https://" not in html


def test_card_includes_report_content():
    html = render_report_card(REPORT)
    assert "00006947" in html
    assert "current_ratio" in html
    assert "Current ratio below 1." in html
    assert "Ucetni zaverka 2023" in html


def test_card_escapes_company_name():
    html = render_report_card(REPORT)
    assert "Test &amp; Co s.r.o." in html
    assert "Test & Co" not in html


RICH_REPORT = CompanyFinancialReport(
    company_name="Test & Co s.r.o.",
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


def test_card_shows_multi_year_table():
    html = render_report_card(RICH_REPORT)
    assert "2023" in html and "2022" in html
    assert "120" in html and "100" in html


def test_card_ratios_have_plain_language():
    html = render_report_card(RICH_REPORT)
    assert "liquid assets" in html


def test_card_flags_sorted_critical_first():
    html = render_report_card(RICH_REPORT)
    assert html.index("Appears in ISIR.") < html.index("Current ratio below 1.")


def test_card_shows_public_money_section():
    html = render_report_card(RICH_REPORT)
    assert "30%" in html
    assert "Public money" in html


def test_card_footer_notes_thousands_czk():
    html = render_report_card(RICH_REPORT)
    assert "thousands of CZK" in html


IN05_REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(interest_coverage=4.0),
    in05=IN05Result(value=1.457, zone="grey"),
    source_filing_title="Ucetni zaverka 2023",
)


def test_card_shows_in05_section_html():
    html = render_report_card(IN05_REPORT)
    assert "IN05" in html
    assert "grey" in html


def test_card_shows_in05_section_markdown():
    md = render_report_markdown(IN05_REPORT)
    assert "IN05" in md
    assert "grey" in md


def test_card_new_ratio_has_blurb():
    html = render_report_card(IN05_REPORT)
    assert "interest" in html.lower()
