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
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.answer import Answer
from rejstrik.documents.ask import ask_filing as _ask_filing
from rejstrik.documents.config import has_llm_key
from rejstrik.documents.extract import extract_financials as _extract_financials
from rejstrik.documents.pdftext import PageText, extract_pages_text, parse_page_range
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
from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    estimate_valuation as _estimate_valuation,
)
from rejstrik.mcp.card import render_report_card, render_report_markdown
from rejstrik.service import (
    analyze_company_financials as _analyze_company_financials,
    analyze_statements as _analyze_statements,
    count_pdf_pages,
    fetch_filing as _fetch_filing,
    resolve_statement_source,
)

mcp = FastMCP("rejstrik", stateless_http=True, json_response=True)

_MAX_EMBED_BYTES = int(os.environ.get("REJSTRIK_MAX_EMBED_BYTES", "25000000"))

_UI_URI = "ui://rejstrik/report"
# ext-apps _meta UI declaration. VERIFY the exact key against the MCP Apps spec
# (blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps) on the implementation
# day — the ecosystem moves monthly. Override at runtime via REJSTRIK_APPS_CAPABILITY_KEY.
_UI_META = {"mcp/ui": {"resourceUri": _UI_URI}}


def _apps_capability(experimental: dict | None) -> bool:
    if not experimental:
        return False
    key = os.environ.get("REJSTRIK_APPS_CAPABILITY_KEY", "mcp-apps")
    return key in experimental


def _host_supports_apps() -> bool:
    try:
        ctx = mcp.get_context()
        experimental = ctx.session.client_params.capabilities.experimental
    except Exception:
        return False
    return _apps_capability(experimental)


def _card_ui_resource(report: CompanyFinancialReport) -> UIResource:
    return create_ui_resource(
        {
            "uri": _UI_URI,
            "content": {
                "type": "rawHtml",
                "htmlString": render_report_card(report),
            },
            "encoding": "text",
        }
    )


def _render_card_output(
    report: CompanyFinancialReport, *, apps_supported: bool
) -> list[TextContent | UIResource]:
    if apps_supported:
        return [_card_ui_resource(report)]
    return [TextContent(type="text", text=render_report_markdown(report))]


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
    "read_filing_text",
    "estimate_valuation",
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


@mcp.resource(_UI_URI, mime_type="text/html", meta=_UI_META)
def report_card_ui() -> str:
    """The financial report card's self-contained HTML shell (MCP Apps template)."""
    return render_report_card(
        CompanyFinancialReport(
            statement=FinancialStatement(),
            normalized=NormalizedFinancials(),
            ratios=Ratios(),
        )
    )


@mcp.tool(
    annotations=_ro("Analyze company card"), meta=_UI_META, structured_output=False
)
def analyze_company_card(query: str, years: int = 1) -> list[TextContent | UIResource]:
    """Full financial report as a card, over the last `years` (1-5) years. Hosts
    that negotiate the MCP Apps capability get an interactive HTML card; others
    get a compact markdown summary. Requires a server-side API key; without one,
    use get_filing + analyze_financials + render_card."""
    _require_llm_key()
    report = _analyze_company_financials(query, years=years)
    return _render_card_output(report, apps_supported=_host_supports_apps())


@mcp.tool(annotations=_ro("Get filing PDF"), structured_output=False)
def get_filing(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    embed: str = "auto",
) -> list[TextContent | EmbeddedResource]:
    """Download a financial statement PDF from Sbírka listin (latest, or by
    year / filing id from list_filings). Returns filing metadata with a local
    file_path and page_count, and — depending on `embed` — the PDF bytes.

    embed:
      - "auto" (default): embed only if the PDF fits the server's size cap.
      - "never": metadata + file_path only. FILESYSTEM-CAPABLE HOSTS (Claude
        Code, Codex, Desktop with fs access) SHOULD pass embed="never" and read
        the PDF from file_path — filed statements are routinely 20-25 MB and the
        path is strictly better than putting ~33 MB of base64 in context.
      - "always": embed regardless (still hard-capped; an honest message is
        returned instead of silently dropping an over-cap PDF).

    Read the PDF yourself (or call read_filing_text for a page range), then pass
    extracted figures to analyze_financials — no server-side API key needed."""
    if embed not in ("auto", "always", "never"):
        raise ValueError('embed must be "auto", "always", or "never"')
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    parts: list[TextContent | EmbeddedResource] = [
        TextContent(type="text", text=doc.model_dump_json(indent=2))
    ]
    if embed == "never":
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"Not embedding by request (embed=never). "
                    f"Read the PDF from file_path: {doc.file_path}"
                ),
            )
        )
        return parts

    over_cap = doc.size_bytes > _MAX_EMBED_BYTES
    if embed == "auto" and over_cap:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — over the {_MAX_EMBED_BYTES}-byte "
                    f"embed cap. Read it from file_path: {doc.file_path} "
                    f"(or call read_filing_text for a page range)."
                ),
            )
        )
        return parts
    if embed == "always" and over_cap:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — too large to embed even with "
                    f"embed=always (cap {_MAX_EMBED_BYTES} bytes). "
                    f"Read it from file_path: {doc.file_path}"
                ),
            )
        )
        return parts

    try:
        uri = Path(doc.file_path).as_uri()
    except ValueError:
        uri = None
    if uri is not None:
        parts.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=uri,
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
                    f"PDF at {doc.file_path} could not be embedded "
                    f"(path is not absolute). Read it from that path."
                ),
            )
        )
    return parts


class FilingText(BaseModel):
    ico: str
    year: int | None = None
    page_count: int
    requested_pages: list[int]
    pages: list[PageText]
    message: str | None = None


@mcp.tool(annotations=_ro("Read filing text"))
def read_filing_text(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    pages: str = "1-10",
) -> FilingText:
    """Extract the embedded text layer of a statement PDF for a page range —
    keyless, no LLM, no OCR. Page grammar: "3", "1-5", "1-3,7" (default "1-10").
    At most 20 pages per call. Czech filings are often scanned images with no
    text layer; pages without text are reported honestly (has_text=false) with a
    note pointing to extract_financials or filesystem reading — never a silent
    empty string."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    page_count = doc.page_count or count_pdf_pages(source.data) or 0
    requested, message = parse_page_range(pages, page_count=page_count)
    page_texts = extract_pages_text(source.data, requested)
    return FilingText(
        ico=doc.ico,
        year=doc.year,
        page_count=page_count,
        requested_pages=requested,
        pages=page_texts,
        message=message,
    )


@mcp.tool(annotations=_ro("Analyze extracted financials"))
def analyze_financials(
    statements: list[FinancialStatement], ico: str | None = None
) -> CompanyFinancialReport:
    """Deterministic financial report from statements YOU extracted from the
    get_filing PDF(s): normalize → ratios → red flags → trends (with 2+ years).
    Amounts in Czech statements are usually thousands of CZK. Pass the ico to
    enrich red flags with insolvency and unreliable-VAT-payer checks."""
    return _analyze_statements(statements, ico=ico)


@mcp.tool(annotations=_ro("Estimate indicative valuation"))
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
) -> ValuationEstimate:
    """Indicative, deterministic valuation from statements YOU extracted:
    book value, capitalized earnings, and generic EV/EBIT and price/revenue
    multiples, with an overall range and the assumptions used. Amounts are
    thousands of CZK as filed. Multiples are generic, not industry-calibrated;
    book values are not market values. This is NOT investment advice."""
    return _estimate_valuation(statements, assumptions)


@mcp.tool(annotations=_ro("Render report card"), meta=_UI_META, structured_output=False)
def render_card(report: CompanyFinancialReport) -> list[TextContent | UIResource]:
    """Render a CompanyFinancialReport (from analyze_financials) as a card. Hosts
    that negotiate MCP Apps get interactive HTML; others get a compact markdown
    summary suitable for Claude Code and other text-only hosts."""
    return _render_card_output(report, apps_supported=_host_supports_apps())


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
3. For each year, call get_filing(ico, year=...). If you can read local files
   (Claude Code, Codex, Desktop with filesystem access), pass embed="never" and
   read the PDF from the returned file_path — filed statements are routinely
   20-25 MB and the path is strictly better than embedding. Otherwise use the
   embedded resource, or call read_filing_text(ico, year=..., pages="1-10") to
   pull the text layer in digestible slices.
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
   get_statutory_bodies(ico), get_subsidies(ico), and get_contracts(ico).
3. Follow the analyze-company recipe for the latest financial year
   (list_filings → get_filing → extract figures → analyze_financials).
4. Report: registry status (insolvency, VAT reliability, who runs the
   company), financial health (ratios, red flags), public-money
   dependence (subsidies and contracts relative to revenue), and an
   overall verdict with the caveats an accountant would add."""


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
