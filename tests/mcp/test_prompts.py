import asyncio

from rejstrik.mcp import server


def test_prompts_registered():
    prompts = asyncio.run(server.mcp.list_prompts())
    names = {p.name for p in prompts}
    assert {"analyze-company", "company-health-check"} <= names


def test_analyze_company_prompt_mentions_tools_and_schema():
    text = server.analyze_company_prompt("Budvar", years=3)
    for needle in (
        "find_company",
        "list_filings",
        "get_filing",
        "analyze_financials",
        "render_card",
        "thousands of CZK",
        "period_year",
        "Budvar",
        "3",
        "read_filing_text",
        'embed="never"',
    ):
        assert needle in text


def test_health_check_prompt_mentions_breadth_tools():
    text = server.company_health_check_prompt("Budvar")
    for needle in ("check_insolvency", "check_vat", "get_statutory_bodies", "Budvar"):
        assert needle in text
