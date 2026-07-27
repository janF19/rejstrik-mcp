import asyncio
from types import SimpleNamespace

from rejstrik.analysis.valuation import ValuationAssumptions
from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement
from rejstrik.mcp import server
from rejstrik.mcp.server import estimate_valuation


def _statement(
    year=2023,
    revenue=3_886_882.0,
    operating_profit=903_044.0,
    net_profit=752_222.0,
    da=62_144.0,
    ocf=362_734.0,
    total_assets=3_541_478.0,
    total_liabilities=499_199.0,
    equity=3_039_871.0,
):
    return FinancialStatement(
        company_name="ROBE lighting s.r.o.",
        ico="64088791",
        period_year=year,
        unit="thousands_czk",
        canonical=CanonicalFigures(
            total_assets=Figure(label="Aktiva celkem", value=total_assets),
            equity=Figure(label="Vlastní kapitál", value=equity),
            total_liabilities=Figure(label="Cizí zdroje", value=total_liabilities),
            revenue=Figure(label="Tržby", value=revenue),
            operating_profit=Figure(label="Provozní VH", value=operating_profit),
            net_profit=Figure(label="VH za účetní období", value=net_profit),
            operating_cash_flow=Figure(label="Provozní CF", value=ocf),
            depreciation_amortization=Figure(label="Odpisy", value=da),
        ),
    )


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
    assert result.industry_key == "machinery"


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
    assert result.industry_key == "machinery"
    assert any("NACE 28" in c for c in result.caveats)


def test_agent_supplied_key_is_high_confidence():
    result = estimate_valuation([_statement()], industry_key="electrical_equipment")
    assert result.adjustment_factors["data_confidence"] == 1.00
    assert result.industry_key == "electrical_equipment"


def test_nace_derived_key_is_medium_confidence(monkeypatch):
    monkeypatch.setattr(
        "rejstrik.mcp.server._find_company",
        lambda ico: SimpleNamespace(nace_codes=["471", "261", "952"]),
    )
    result = estimate_valuation([_statement()], ico="64088791")
    assert result.industry_key == "electronics_general"
    assert result.adjustment_factors["data_confidence"] == 0.95


def test_no_classification_is_low_confidence():
    result = estimate_valuation([_statement()])
    assert result.industry_key == "total_market_ex_financials"
    assert result.adjustment_factors["data_confidence"] == 0.85


def test_explicit_multiple_overrides_sector():
    result = estimate_valuation(
        [_statement()],
        assumptions=ValuationAssumptions(ebitda_multiple=6.0),
        industry_key="electrical_equipment",
    )
    assert result.final_multiple == 6.0
