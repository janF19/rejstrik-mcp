import asyncio

from rejstrik.mcp import server


def test_all_tools_are_read_only_and_open_world():
    tools = asyncio.run(server.mcp.list_tools())
    exposed = {t.name: t for t in tools if t.name in server.EXPOSED_TOOL_NAMES}
    assert len(exposed) == len(server.EXPOSED_TOOL_NAMES)
    for name, tool in exposed.items():
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is True, f"{name} not marked read-only"
        assert tool.annotations.openWorldHint is True, f"{name} not marked open-world"
        assert tool.annotations.title, f"{name} missing title"
