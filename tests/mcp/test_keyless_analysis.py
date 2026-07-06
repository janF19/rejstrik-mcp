import asyncio

from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.mcp import server


def _statement(year: int, revenue: float) -> FinancialStatement:
    return FinancialStatement(
        company_name="Budvar",
        period_year=year,
        currency="CZK",
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def test_analyze_financials_two_years():
    report = server.analyze_financials(
        [_statement(2023, 800.0), _statement(2024, 1000.0)]
    )
    assert isinstance(report, CompanyFinancialReport)
    assert report.period_year == 2024
    assert any(t.metric == "revenue" and t.pct_change for t in report.trends)


def test_render_card_returns_ui_resource():
    report = server.analyze_financials([_statement(2024, 1000.0)])
    resources = server.render_card(report)
    assert str(resources[0].resource.uri) == "ui://rejstrik/report"
    assert "Budvar" in resources[0].resource.text


def test_new_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"analyze_financials", "render_card"} <= names
