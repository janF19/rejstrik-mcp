import asyncio
from unittest.mock import patch

from mcp.types import TextContent
from mcp_ui_server import UIResource

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
    assert "render_card" in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 13


def test_card_tool_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "render_card" in names


def test_render_card_returns_markdown_by_default():
    with patch.object(server, "_host_supports_apps", return_value=False):
        result = server.render_card(REPORT)
    assert isinstance(result, list) and len(result) == 1
    assert isinstance(result[0], TextContent)
    assert "Test s.r.o." in result[0].text


def test_render_card_returns_ui_resource_when_apps_supported():
    with patch.object(server, "_host_supports_apps", return_value=True):
        result = server.render_card(REPORT)
    assert isinstance(result, list) and len(result) == 1
    assert isinstance(result[0], UIResource)
    dumped = str(result[0].model_dump())
    assert "ui://rejstrik/report" in dumped
    assert "Test s.r.o." in dumped
