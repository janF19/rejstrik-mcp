import httpx
from collections.abc import Callable

from rejstrik.analysis.normalize import normalize
from rejstrik.analysis.ratios import compute_ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.llm import DocumentLLM
from rejstrik.documents.pick import pick_latest_financial_filing
from rejstrik.documents.source import PdfSource, load_pdf
from rejstrik.filings.justice import list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company
from rejstrik.registry.isir import InsolvencyStatus, check_insolvency
from rejstrik.registry.models import Company


class NoStatementFound(Exception):
    pass


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
) -> CompanyFinancialReport:
    insolvency_check = insolvency_check or check_insolvency
    company, filing, source = resolve_statement_source(query)
    statement = extract_financials(source, llm=llm)
    normalized = normalize(statement)
    ratios = compute_ratios(normalized)
    status = insolvency_check(company.ico)
    insolvent = status.in_insolvency if status.checked else None
    red_flags = detect_red_flags(
        normalized, ratios, statement.notes, insolvent=insolvent
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
