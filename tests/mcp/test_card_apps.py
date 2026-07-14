import asyncio

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


def test_apps_capability_detects_key():
    assert server._apps_capability({"mcp-apps": {}}) is True
    assert server._apps_capability({}) is False
    assert server._apps_capability(None) is False


def test_render_output_markdown_when_no_apps():
    out = server._render_card_output(REPORT, apps_supported=False)
    assert len(out) == 1
    assert isinstance(out[0], TextContent)
    assert "Test s.r.o." in out[0].text
    assert "<" not in out[0].text


def test_render_output_uiresource_when_apps():
    out = server._render_card_output(REPORT, apps_supported=True)
    assert len(out) == 1
    assert isinstance(out[0], UIResource)
    assert "ui://rejstrik/report" in str(out[0].model_dump())


def test_host_supports_apps_false_without_context():
    # No active request context → defensive False (Claude Code path).
    assert server._host_supports_apps() is False


def test_card_resource_registered():
    resources = asyncio.run(server.mcp.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "ui://rejstrik/report" in uris
