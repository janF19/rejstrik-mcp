from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp.card import render_report_card

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
