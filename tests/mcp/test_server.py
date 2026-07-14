import asyncio

from rejstrik.mcp import server


def test_exposed_tool_names():
    assert server.EXPOSED_TOOL_NAMES == [
        "find_company",
        "list_filings",
        "extract_financials",
        "ask_filing",
        "analyze_company_financials",
        "check_insolvency",
        "get_statutory_bodies",
        "check_vat",
        "analyze_company_card",
        "get_filing",
        "analyze_financials",
        "render_card",
        "get_subsidies",
        "get_contracts",
        "read_filing_text",
        "read_filing_page_images",
        "estimate_valuation",
    ]


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
