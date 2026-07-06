import asyncio
from unittest.mock import patch

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp import server

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(),
    red_flags=[],
    source_filing_title="Ucetni zaverka 2023",
)


def test_card_tool_in_exposed_names():
    assert "analyze_company_card" in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 10


def test_card_tool_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "analyze_company_card" in names


def test_card_tool_returns_ui_resource():
    with patch.object(server, "_analyze_company_financials", return_value=REPORT):
        result = server.analyze_company_card("Test")
    assert isinstance(result, list) and len(result) == 1
    dumped = result[0].model_dump() if hasattr(result[0], "model_dump") else result[0]
    assert "ui://rejstrik/report" in str(dumped)
