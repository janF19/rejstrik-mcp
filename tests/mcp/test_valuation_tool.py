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


def test_industry_key_flows_through_tool():
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation([stmt], industry_key="machinery")
    assert result.industry_multiple_applied == "machinery"


def test_ico_resolves_nace_to_industry(monkeypatch):
    from rejstrik.registry.models import Company

    monkeypatch.setattr(
        server,
        "_find_company",
        lambda q: Company(ico="00000001", name="X", nace_codes=["28150"]),
    )
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation([stmt], ico="00000001")
    assert result.industry_multiple_applied == "machinery"
    assert any("NACE 28" in c for c in result.caveats)


def test_explicit_assumptions_take_precedence_over_industry():
    from rejstrik.analysis.valuation import ValuationAssumptions

    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation(
        [stmt],
        assumptions=ValuationAssumptions(ebit_multiple=6.0),
        industry_key="machinery",
    )
    assert result.industry_multiple_applied is None
    assert result.ev_ebit_multiple == 600.0
