import base64
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import BlobResourceContents, EmbeddedResource, TextContent
from mcp_ui_server import UIResource, create_ui_resource

from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.answer import Answer
from rejstrik.documents.ask import ask_filing as _ask_filing
from rejstrik.documents.extract import extract_financials as _extract_financials
from rejstrik.documents.schema import FinancialStatement
from rejstrik.filings.justice import list_filings as _list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company as _find_company
from rejstrik.registry.isir import (
    InsolvencyStatus,
    check_insolvency as _check_insolvency,
)
from rejstrik.registry.models import Company
from rejstrik.registry.statutory import (
    Officer,
    get_statutory_bodies as _get_statutory_bodies,
)
from rejstrik.registry.vat import VatStatus, check_vat as _check_vat
from rejstrik.mcp.card import render_report_card
from rejstrik.service import (
    analyze_company_financials as _analyze_company_financials,
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
]


@mcp.tool()
def find_company(query: str) -> Company:
    """Resolve a Czech company by name or IČO via the ARES registry."""
    return _find_company(query)


@mcp.tool()
def list_filings(ico: str) -> list[Filing]:
    """List a company's Sbírka listin documents."""
    return _list_filings(ico)


@mcp.tool()
def extract_financials(ico: str) -> FinancialStatement:
    """Extract structured financials from the latest statement PDF."""
    _company, _filing, source = resolve_statement_source(ico)
    return _extract_financials(source)


@mcp.tool()
def ask_filing(ico: str, question: str) -> Answer:
    """Answer a question about the latest statement with page citations."""
    _company, _filing, source = resolve_statement_source(ico)
    return _ask_filing(source, question)


@mcp.tool()
def analyze_company_financials(query: str) -> CompanyFinancialReport:
    """Full financial report for a company."""
    return _analyze_company_financials(query)


@mcp.tool()
def analyze_company_card(query: str) -> list[UIResource]:
    """Full financial report rendered as an interactive HTML card."""
    report = _analyze_company_financials(query)
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


@mcp.tool(structured_output=False)
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


def _to_ico(value: str) -> str:
    """Accept an IČO directly, otherwise resolve a name via ARES."""
    candidate = value.strip()
    return candidate.zfill(8) if candidate.isdigit() else _find_company(candidate).ico


@mcp.tool()
def check_insolvency(ico: str) -> InsolvencyStatus:
    """Check the Czech insolvency register (ISIR) by IČO or company name."""
    return _check_insolvency(_to_ico(ico))


@mcp.tool()
def get_statutory_bodies(ico: str) -> list[Officer]:
    """List statutory body members from the ARES public-register extract."""
    return _get_statutory_bodies(_to_ico(ico))


@mcp.tool()
def check_vat(ico: str) -> VatStatus:
    """Report VAT registration and DIČ from the ARES detail record."""
    return _check_vat(_to_ico(ico))


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
