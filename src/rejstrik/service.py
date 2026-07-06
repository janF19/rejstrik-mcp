import httpx
from collections.abc import Callable

from pydantic import BaseModel

from rejstrik.analysis.normalize import normalize
from rejstrik.analysis.ratios import compute_ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.trends import compute_trends
from rejstrik.documents.cache import save_filing_pdf
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.llm import DocumentLLM
from rejstrik.documents.pick import pick_financial_filing, pick_latest_financial_filing
from rejstrik.documents.schema import FinancialStatement
from rejstrik.documents.source import PdfSource, load_pdf
from rejstrik.filings.justice import list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company
from rejstrik.registry.isir import InsolvencyStatus, check_insolvency
from rejstrik.registry.models import Company
from rejstrik.registry.vat import VatStatus, check_vat


class NoStatementFound(Exception):
    pass


class FilingDocument(BaseModel):
    ico: str
    company_name: str
    title: str
    year: int | None = None
    pdf_url: str
    file_path: str
    sha256: str
    size_bytes: int


def fetch_filing(
    query: str,
    year: int | None = None,
    filing_id: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[FilingDocument, PdfSource]:
    company = find_company(query, client=client)
    filings = list_filings(company.ico, client=client)
    filing = pick_financial_filing(filings, year=year, filing_id=filing_id)
    if filing is None:
        years = sorted(
            {f.year for f in filings if f.is_financial_statement and f.year},
            reverse=True,
        )
        hint = (
            f" Available years: {years}."
            if years
            else " No financial statements filed."
        )
        raise NoStatementFound(
            f"No matching financial statement in Sbírka listin for {company.ico}.{hint}"
        )
    source = load_pdf(filing, client=client)
    path = save_filing_pdf(source, company.ico, filing.year)
    return (
        FilingDocument(
            ico=company.ico,
            company_name=company.name,
            title=filing.title,
            year=filing.year,
            pdf_url=filing.pdf_url,
            file_path=str(path),
            sha256=source.sha256,
            size_bytes=len(source.data),
        ),
        source,
    )


def resolve_statement_source(
    query: str,
    client: httpx.Client | None = None,
) -> tuple[Company, Filing, PdfSource]:
    company = find_company(query, client=client)
    filing = pick_latest_financial_filing(list_filings(company.ico, client=client))
    if filing is None:
        raise NoStatementFound(
            f"No financial statement in Sbírka listin for {company.ico}"
        )
    return company, filing, load_pdf(filing, client=client)


def analyze_company_financials(
    query: str,
    *,
    llm: DocumentLLM | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
) -> CompanyFinancialReport:
    insolvency_check = insolvency_check or check_insolvency
    vat_check = vat_check or check_vat
    company, filing, source = resolve_statement_source(query)
    statement = extract_financials(source, llm=llm)
    normalized = normalize(statement)
    ratios = compute_ratios(normalized)
    status = insolvency_check(company.ico)
    insolvent = status.in_insolvency if status.checked else None
    vat = vat_check(company.ico)
    red_flags = detect_red_flags(
        normalized,
        ratios,
        statement.notes,
        insolvent=insolvent,
        unreliable_vat=vat.is_unreliable,
    )
    return CompanyFinancialReport(
        company_name=statement.company_name or company.name,
        ico=statement.ico or company.ico,
        period_year=statement.period_year,
        currency=statement.currency,
        statement=statement,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        trends=[],
        source_filing_title=filing.title,
    )


def analyze_statements(
    statements: list[FinancialStatement],
    *,
    ico: str | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
) -> CompanyFinancialReport:
    """Deterministic report from host-extracted statements. No LLM calls."""
    if not statements:
        raise ValueError(
            "statements must contain at least one FinancialStatement "
            "(extract it from the PDF returned by get_filing)"
        )
    ordered = sorted(
        statements, key=lambda s: (s.period_year is None, -(s.period_year or 0))
    )
    current = ordered[0]
    normalized = normalize(current)
    ratios = compute_ratios(normalized)
    resolved_ico = ico or current.ico
    insolvent = None
    unreliable_vat = None
    if resolved_ico:
        insolvency_check = insolvency_check or check_insolvency
        vat_check = vat_check or check_vat
        status = insolvency_check(resolved_ico)
        insolvent = status.in_insolvency if status.checked else None
        unreliable_vat = vat_check(resolved_ico).is_unreliable
    red_flags = detect_red_flags(
        normalized,
        ratios,
        current.notes,
        insolvent=insolvent,
        unreliable_vat=unreliable_vat,
    )
    trends = (
        compute_trends(normalized, normalize(ordered[1])) if len(ordered) > 1 else []
    )
    return CompanyFinancialReport(
        company_name=current.company_name,
        ico=resolved_ico,
        period_year=current.period_year,
        currency=current.currency,
        statement=current,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        trends=trends,
    )
