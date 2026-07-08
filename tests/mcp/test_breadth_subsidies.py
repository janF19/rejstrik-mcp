import asyncio

from rejstrik.mcp import server


def test_breadth_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"get_subsidies", "get_contracts"} <= names


def test_breadth_tools_in_exposed_list():
    assert "get_subsidies" in server.EXPOSED_TOOL_NAMES
    assert "get_contracts" in server.EXPOSED_TOOL_NAMES
