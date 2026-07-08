import argparse
import base64
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    TextContent,
    ToolAnnotations,
)
from mcp_ui_server import UIResource, create_ui_resource

from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.answer import Answer
from rejstrik.documents.ask import ask_filing as _ask_filing
from rejstrik.documents.config import has_llm_key
from rejstrik.documents.extract import extract_financials as _extract_financials
from rejstrik.documents.schema import FinancialStatement
from rejstrik.filings.justice import list_filings as _list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company as _find_company
from rejstrik.registry.contracts import ContractReport, get_contracts as _get_contracts
from rejstrik.registry.isir import (
    InsolvencyStatus,
    check_insolvency as _check_insolvency,
)
from rejstrik.registry.models import Company
from rejstrik.registry.statutory import (
    Officer,
    get_statutory_bodies as _get_statutory_bodies,
)
from rejstrik.registry.subsidies import SubsidyReport, get_subsidies as _get_subsidies
from rejstrik.registry.vat import VatStatus, check_vat as _check_vat
from rejstrik.mcp.card import render_report_card
from rejstrik.service import (
    analyze_company_financials as _analyze_company_financials,
    analyze_statements as _analyze_statements,
    fetch_filing as _fetch_filing,
    resolve_statement_source,
)

mcp = FastMCP("rejstrik", stateless_http=True, json_response=True)

_MAX_EMBED_BYTES = int(os.environ.get("REJSTRIK_MAX_EMBED_BYTES", "15000000"))

EXPOSED_TOOL_NAMES = [
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
]


def _ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True, openWorldHint=True)


class MissingApiKey(Exception):
    pass


_KEYLESS_HINT = (
    "This tool runs a model inside the server and needs ANTHROPIC_API_KEY or "
    "OPENAI_API_KEY set where rejstrik-mcp runs. Keyless alternative: call "
    "get_filing to fetch the statement PDF, read it yourself, then pass the "
    "extracted figures to analyze_financials (and render_card for the UI card)."
)


def _require_llm_key() -> None:
    if not has_llm_key():
        raise MissingApiKey(_KEYLESS_HINT)


@mcp.tool(annotations=_ro("Find Czech company"))
def find_company(query: str) -> Company:
    """Resolve a Czech company by name or IČO via the ARES registry."""
    return _find_company(query)


@mcp.tool(annotations=_ro("List Sbírka listin filings"))
def list_filings(ico: str) -> list[Filing]:
    """List a company's Sbírka listin documents."""
    return _list_filings(ico)


@mcp.tool(annotations=_ro("Extract financial statement"))
def extract_financials(
    ico: str, year: int | None = None, filing_id: str | None = None
) -> FinancialStatement:
    """Extract structured financials from a statement PDF (latest, or by year /
    filing id). Requires a server-side API key; without one, use get_filing +
    analyze_financials."""
    _require_llm_key()
    _company, _filing, source = resolve_statement_source(
        ico, year=year, filing_id=filing_id
    )
    return _extract_financials(source)


@mcp.tool(annotations=_ro("Ask about a filing"))
def ask_filing(
    ico: str, question: str, year: int | None = None, filing_id: str | None = None
) -> Answer:
    """Answer a question about a statement with page citations (latest, or by
    year / filing id). Requires a server-side API key; without one, use
    get_filing + analyze_financials."""
    _require_llm_key()
    _company, _filing, source = resolve_statement_source(
        ico, year=year, filing_id=filing_id
    )
    return _ask_filing(source, question)


@mcp.tool(annotations=_ro("Analyze company financials"))
def analyze_company_financials(query: str, years: int = 1) -> CompanyFinancialReport:
    """Full financial report for a company over the last `years` (1-5) years,
    with year-over-year trends when years > 1. Requires a server-side API key;
    without one, use get_filing + analyze_financials."""
    _require_llm_key()
    return _analyze_company_financials(query, years=years)


@mcp.tool(annotations=_ro("Analyze company card"))
def analyze_company_card(query: str, years: int = 1) -> list[UIResource]:
    """Full financial report as an interactive HTML card, over the last `years`
    (1-5) years. Requires a server-side API key; without one, use get_filing +
    analyze_financials + render_card."""
    _require_llm_key()
    report = _analyze_company_financials(query, years=years)
    return [
        create_ui_resource(
            {
                "uri": "ui://rejstrik/report",
                "content": {
                    "type": "rawHtml",
                    "htmlString": render_report_card(report),
                },
                "encoding": "text",
            }
        )
    ]


@mcp.tool(annotations=_ro("Get filing PDF"), structured_output=False)
def get_filing(
    ico: str, year: int | None = None, filing_id: str | None = None
) -> list[TextContent | EmbeddedResource]:
    """Download a financial statement PDF from Sbírka listin (latest, or by
    year / filing id from list_filings). Returns filing metadata with a local
    file_path, plus the PDF itself as an embedded resource. Read the PDF with
    your own capabilities, then pass extracted figures to analyze_financials —
    no server-side API key needed."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    parts: list[TextContent | EmbeddedResource] = [
        TextContent(type="text", text=doc.model_dump_json(indent=2))
    ]
    if doc.size_bytes <= _MAX_EMBED_BYTES:
        parts.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=Path(doc.file_path).as_uri(),
                    mimeType="application/pdf",
                    blob=base64.standard_b64encode(source.data).decode(),
                ),
            )
        )
    else:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — too large to embed. "
                    f"Read it from file_path: {doc.file_path}"
                ),
            )
        )
    return parts


@mcp.tool(annotations=_ro("Analyze extracted financials"))
def analyze_financials(
    statements: list[FinancialStatement], ico: str | None = None
) -> CompanyFinancialReport:
    """Deterministic financial report from statements YOU extracted from the
    get_filing PDF(s): normalize → ratios → red flags → trends (with 2+ years).
    Amounts in Czech statements are usually thousands of CZK. Pass the ico to
    enrich red flags with insolvency and unreliable-VAT-payer checks."""
    return _analyze_statements(statements, ico=ico)


@mcp.tool(annotations=_ro("Render report card"))
def render_card(report: CompanyFinancialReport) -> list[UIResource]:
    """Render a CompanyFinancialReport (from analyze_financials) as an
    interactive HTML card for MCP UI hosts."""
    return [
        create_ui_resource(
            {
                "uri": "ui://rejstrik/report",
                "content": {
                    "type": "rawHtml",
                    "htmlString": render_report_card(report),
                },
                "encoding": "text",
            }
        )
    ]


def _to_ico(value: str) -> str:
    """Accept an IČO directly, otherwise resolve a name via ARES."""
    candidate = value.strip()
    return candidate.zfill(8) if candidate.isdigit() else _find_company(candidate).ico


@mcp.tool(annotations=_ro("Check insolvency"))
def check_insolvency(ico: str) -> InsolvencyStatus:
    """Check the Czech insolvency register (ISIR) by IČO or company name."""
    return _check_insolvency(_to_ico(ico))


@mcp.tool(annotations=_ro("Get statutory bodies"))
def get_statutory_bodies(ico: str) -> list[Officer]:
    """List statutory body members from the ARES public-register extract."""
    return _get_statutory_bodies(_to_ico(ico))


@mcp.tool(annotations=_ro("Check VAT status"))
def check_vat(ico: str) -> VatStatus:
    """Report VAT registration and DIČ from the ARES detail record."""
    return _check_vat(_to_ico(ico))


@mcp.tool(annotations=_ro("Get state subsidies"))
def get_subsidies(ico: str) -> SubsidyReport:
    """State subsidies received by a company (IS ReD / former CEDR), by IČO or name."""
    return _get_subsidies(_to_ico(ico))


@mcp.tool(annotations=_ro("Get public contracts"))
def get_contracts(ico: str) -> ContractReport:
    """Public contracts involving a company (Registr smluv), by IČO or name."""
    return _get_contracts(_to_ico(ico))


@mcp.prompt(name="analyze-company")
def analyze_company_prompt(company: str, years: int = 1) -> str:
    """Guide the host model through keyless company financial analysis."""
    schema = json.dumps(FinancialStatement.model_json_schema(), indent=2)
    return f"""Analyze the financials of the Czech company "{company}" over the
last {years} year(s), using only your own reading of the filed statements.

Follow these steps exactly:
1. Call find_company("{company}") to resolve the IČO.
2. Call list_filings(ico) and identify the financial statements for the
   {years} most recent year(s).
3. For each year, call get_filing(ico, year=...). Read the returned PDF
   (use the local file_path if you can read files, otherwise the embedded
   resource).
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema (amounts in Czech statements are usually reported in thousands of CZK
   — keep them as printed and set currency to "CZK"; set period_year to the
   statement year; cite source_page for every figure):
{schema}
5. Call analyze_financials(statements=[...], ico=ico) with ALL extracted
   statements in one call to get ratios, red flags, and year-over-year trends.
6. If your client renders MCP UI resources, also call render_card(report).
7. Summarize: overall health, notable trends, every red flag with its
   severity, and page citations for key numbers."""


@mcp.prompt(name="company-health-check")
def company_health_check_prompt(company: str) -> str:
    """Guide the host model through a full registry + financials health check."""
    return f"""Run a full health check on the Czech company "{company}".

1. Call find_company("{company}") to resolve the IČO.
2. In parallel where possible, call check_insolvency(ico), check_vat(ico),
   and get_statutory_bodies(ico).
3. Follow the analyze-company recipe for the latest financial year
   (list_filings → get_filing → extract figures → analyze_financials).
4. Report: registry status (insolvency, VAT reliability, who runs the
   company), financial health (ratios, red flags), and an overall verdict
   with the caveats an accountant would add."""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rejstrik-mcp")
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve streamable HTTP on /mcp instead of stdio",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
