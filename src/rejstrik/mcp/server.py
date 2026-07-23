import argparse
import base64
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextContent,
    ToolAnnotations,
)
from mcp_ui_server import UIResource, create_ui_resource
from pydantic import BaseModel

from rejstrik import __version__
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.pdftext import PageText, extract_pages_text, parse_page_range
from rejstrik.documents.pdfimages import render_page_images
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
from rejstrik.analysis.industry import industry_key_for_nace
from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    estimate_valuation as _estimate_valuation,
)
from rejstrik.mcp.card import render_report_card, render_report_markdown
from rejstrik.service import (
    analyze_statements as _analyze_statements,
    count_pdf_pages,
    fetch_filing as _fetch_filing,
)

mcp = FastMCP("rejstrik", stateless_http=True, json_response=True)
# FastMCP has no version kwarg; without this, serverInfo.version reports the MCP
# SDK version instead of ours. Pin it to the package version so hosts show the package version.
mcp._mcp_server.version = __version__

_MAX_EMBED_BYTES = int(os.environ.get("REJSTRIK_MAX_EMBED_BYTES", "25000000"))

_UI_URI = "ui://rejstrik/report"
# SEP-1865 (MCP Apps, 2026-01-26) _meta UI declaration. The host reads
# _meta.ui.resourceUri, so the top-level meta key is "ui". The capability the
# host must advertise is "io.modelcontextprotocol/ui" (see _apps_capability),
# runtime-overridable via REJSTRIK_APPS_CAPABILITY_KEY. Interactive rendering is
# gated upstream: Claude negotiates the capability but does not yet render the
# iframe (ext-apps#671), so markdown remains the default output.
_UI_META = {"ui": {"resourceUri": _UI_URI}}


def _apps_capability(experimental: dict | None) -> bool:
    if not experimental:
        return False
    key = os.environ.get("REJSTRIK_APPS_CAPABILITY_KEY", "io.modelcontextprotocol/ui")
    return key in experimental


def _host_supports_apps() -> bool:
    try:
        ctx = mcp.get_context()
        experimental = ctx.session.client_params.capabilities.experimental
    except Exception:
        return False
    return _apps_capability(experimental)


def _card_ui_resource(report: CompanyFinancialReport) -> UIResource:
    resource = create_ui_resource(
        {
            "uri": _UI_URI,
            "content": {
                "type": "rawHtml",
                "htmlString": render_report_card(report),
            },
            "encoding": "text",
        }
    )
    # create_ui_resource emits text/html; SEP-1865 requires the mcp-app profile.
    resource.resource.mimeType = "text/html;profile=mcp-app"
    return resource


def _render_card_output(
    report: CompanyFinancialReport, *, apps_supported: bool
) -> list[TextContent | UIResource]:
    if apps_supported:
        return [_card_ui_resource(report)]
    return [TextContent(type="text", text=render_report_markdown(report))]


EXPOSED_TOOL_NAMES = [
    "find_company",
    "list_filings",
    "check_insolvency",
    "get_statutory_bodies",
    "check_vat",
    "get_filing",
    "analyze_financials",
    "render_card",
    "get_subsidies",
    "get_contracts",
    "read_filing_text",
    "read_filing_page_images",
    "estimate_valuation",
]


def _ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True, openWorldHint=True)


@mcp.tool(annotations=_ro("Find Czech company"))
def find_company(query: str) -> Company:
    """Resolve a Czech company by name or IČO via the ARES registry."""
    return _find_company(query)


@mcp.tool(annotations=_ro("List Sbírka listin filings"))
def list_filings(ico: str) -> list[Filing]:
    """List a company's Sbírka listin documents."""
    return _list_filings(ico)


@mcp.resource(_UI_URI, mime_type="text/html;profile=mcp-app", meta=_UI_META)
def report_card_ui() -> str:
    """The financial report card's self-contained HTML shell (MCP Apps template)."""
    return render_report_card(
        CompanyFinancialReport(
            statement=FinancialStatement(),
            normalized=NormalizedFinancials(),
            ratios=Ratios(),
        )
    )


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
    note pointing to read_filing_page_images or filesystem reading — never a
    silent empty string."""
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


@mcp.tool(annotations=_ro("Read filing page images"), structured_output=False)
def read_filing_page_images(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    pages: str = "1-5",
) -> list[TextContent | ImageContent]:
    """Rasterize statement PDF pages to PNG images — keyless, no LLM, no OCR.
    For SCANNED filings with no text layer (read_filing_text reports
    has_text=false) on hosts WITHOUT filesystem access: this delivers legible
    page images the host model can read directly. Page grammar: "3", "1-5",
    "1-3,5" (default "1-5"). At most 5 pages per call (images are token-heavy);
    request later ranges for the rest. Returns one metadata text block, then one
    PNG image per rendered page."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    page_count = doc.page_count or count_pdf_pages(source.data) or 0
    requested, message = parse_page_range(pages, page_count=page_count, max_pages=5)
    images = render_page_images(source.data, requested)
    meta = {
        "ico": doc.ico,
        "year": doc.year,
        "page_count": page_count,
        "rendered_pages": [im.page for im in images],
        "message": message,
    }
    parts: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(meta, indent=2))
    ]
    for im in images:
        parts.append(
            ImageContent(type="image", data=im.png_base64, mimeType="image/png")
        )
    return parts


@mcp.tool(annotations=_ro("Analyze extracted financials"))
def analyze_financials(
    statements: list[FinancialStatement], ico: str | None = None
) -> CompanyFinancialReport:
    """Deterministic financial report from statements YOU extracted from the
    get_filing PDF(s): normalize → ratios → red flags → trends (with 2+ years).
    Record figures verbatim as printed and set each statement's unit field
    ("czk" | "thousands_czk" | "millions_czk") to the scale the statement
    declares (usually 'v celých tisících Kč' → thousands_czk); the server
    converts everything to thousands of CZK, so multi-year trends stay
    comparable. Pass the ico to enrich red flags with insolvency and
    unreliable-VAT-payer checks."""
    return _analyze_statements(statements, ico=ico)


@mcp.tool(annotations=_ro("Estimate indicative valuation"))
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    ico: str | None = None,
) -> ValuationEstimate:
    """Indicative, deterministic valuation from statements YOU extracted: book
    value, capitalized earnings, generic EV/EBIT and price/revenue multiples,
    and — when an industry is known — a Damodaran Europe EV/EBITDA multiple
    (EBITDA = operating profit + depreciation/amortization). Provide `ico` to let
    the server map the company's CZ-NACE to a Damodaran industry, or pass
    `industry_key` directly (you know the business better than a registry code).
    Precedence: explicit `assumptions` > `industry_key` > NACE-derived > generic
    defaults. Set each statement's unit field ("czk" | "thousands_czk" | "millions_czk")
    and pass figures verbatim as printed; results are in thousands of CZK.
    Book values are not market values. NOT investment advice."""
    resolved_key: str | None = None
    reason: str | None = None
    if assumptions is None:
        if industry_key:
            resolved_key = industry_key
            reason = f"industry_key '{industry_key}' given by caller"
        elif ico:
            company = _find_company(ico)
            resolved_key, reason = industry_key_for_nace(company.nace_codes)
    return _estimate_valuation(
        statements,
        assumptions,
        industry_key=resolved_key,
        industry_reason=reason,
    )


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
   pull the text layer in digestible slices. If read_filing_text reports
   has_text=false (a scanned filing) and you cannot read local files, call
   read_filing_page_images(ico, year=..., pages="1-5") to get the pages as PNGs.
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema. Cover the balance sheet (rozvaha), income statement (výkaz zisku a ztráty),
   cash flow if present, and the narrative notes (příloha). Record every
   figure verbatim as printed — never rescale or convert. Statements
   declare their scale near the top of the rozvaha (usually 'v celých
   tisících Kč'); set the `unit` field to match: thousands_czk for 'v tisících Kč', czk for plain Kč, millions_czk for 'v milionech Kč'.
   Set currency to "CZK"; set period_year to the statement year; cite
   source_page for every figure (1-indexed). If a value is not present,
   leave it null rather than guessing. ALSO fill the `canonical`
   object: each of its fields' descriptions names the exact Czech statutory line
   that feeds it (e.g. total_assets ← "Aktiva celkem", net_profit ← "Výsledek
   hospodaření za účetní období") — this is what makes the analysis reliable:
{schema}
5. Call analyze_financials(statements=[...], ico=ico) with ALL extracted
   statements in one call to get ratios, red flags, the IN05 distress index,
   and year-over-year trends.
6. Optionally call estimate_valuation(statements=[...]) for an indicative
   valuation range (book value, capitalized earnings, generic multiples) — it
   is not investment advice.
7. If your client renders MCP UI resources, also call render_card(report).
8. Summarize: overall health, notable trends, every red flag with its
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
