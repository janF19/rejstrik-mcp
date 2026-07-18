import asyncio

from rejstrik.mcp import server


def test_exposed_tool_names():
    assert server.EXPOSED_TOOL_NAMES == [
        "find_company",
        "list_filings",
        "check_insolvency",
        "get_statutory_bodies",
        "check_vat",
        "get_filing",
        "analyze_financials",
        "render_card",
        "get_subsidies",
        "get_contracts",
        "read_filing_text",
        "read_filing_page_images",
        "estimate_valuation",
    ]
    assert len(server.EXPOSED_TOOL_NAMES) == 13


def test_tools_registered_on_server():
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert set(server.EXPOSED_TOOL_NAMES) <= names


def test_main_is_callable():
    assert callable(server.main)


def test_server_reports_package_version():
    from rejstrik import __version__
    from rejstrik.mcp.server import mcp

    assert mcp._mcp_server.version == __version__


def test_analyze_company_prompt_carries_extraction_guidance():
    prompt = server.analyze_company_prompt("Test Company", years=2)

    assert "rozvaha" in prompt
    assert "výkaz zisku a ztráty" in prompt
    assert "příloha" in prompt
    assert "never rescale or convert" in prompt
    assert "millions_czk for 'v milionech Kč'" in prompt
    assert "czk for plain Kč" in prompt
    assert "null rather than guessing" in prompt
