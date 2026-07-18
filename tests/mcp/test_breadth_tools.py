import asyncio
from unittest.mock import patch

from rejstrik.mcp import server
from rejstrik.registry.models import Company


def test_breadth_tools_in_exposed_names():
    for name in ("check_insolvency", "get_statutory_bodies", "check_vat"):
        assert name in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 13


def test_breadth_tools_registered():
    names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert {"check_insolvency", "get_statutory_bodies", "check_vat"} <= names


def test_to_ico_resolves_names_and_zero_pads_numbers():
    assert server._to_ico("1234567") == "01234567"
    with patch.object(
        server, "_find_company", return_value=Company(ico="00006947", name="Test")
    ):
        assert server._to_ico("Test company") == "00006947"
