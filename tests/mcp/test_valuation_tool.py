import asyncio

from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement
from rejstrik.mcp import server


def test_valuation_tool_exposed():
    assert "estimate_valuation" in server.EXPOSED_TOOL_NAMES
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "estimate_valuation" in names


def test_valuation_tool_runs_keyless():
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            equity=Figure(label="Vlastní kapitál", value=800.0),
        ),
    )
    result = server.estimate_valuation([stmt])
    assert result.book_value == 800.0
    assert result.caveats[-1].endswith("not investment advice.")
