import io
from collections.abc import Callable

import httpx
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rejstrik.analysis.normalize import normalize
from rejstrik.analysis.ratios import compute_ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.analysis.trends import compute_trends
from rejstrik.documents.cache import save_filing_pdf
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.llm import DocumentLLM
from rejstrik.documents.pick import pick_financial_filing
from rejstrik.documents.schema import FinancialStatement
from rejstrik.documents.source import PdfSource, load_pdf
from rejstrik.filings.justice import list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company
from rejstrik.registry.isir import InsolvencyStatus, check_insolvency
from rejstrik.registry.contracts import ContractReport
from rejstrik.registry.models import Company
from rejstrik.registry.subsidies import SubsidyReport
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
    page_count: int | None = None


def count_pdf_pages(data: bytes) -> int | None:
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except (PdfReadError, ValueError, OSError):
        return None


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
            page_count=count_pdf_pages(source.data),
        ),
        source,
    )


def resolve_statement_source(
    query: str,
    year: int | None = None,
    filing_id: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[Company, Filing, PdfSource]:
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
    return company, filing, load_pdf(filing, client=client)


def analyze_company_financials(
    query: str,
    *,
    years: int = 1,
    llm: DocumentLLM | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
) -> CompanyFinancialReport:
    years = max(1, min(years, 5))
    company = find_company(query)
    all_filings = list_filings(company.ico)
    statements_filings = [f for f in all_filings if f.is_financial_statement][:years]
    if not statements_filings:
        available_years = sorted(
            {f.year for f in all_filings if f.is_financial_statement and f.year},
            reverse=True,
        )
        hint = (
            f" Available years: {available_years}."
            if available_years
            else " No financial statements filed."
        )
        raise NoStatementFound(
            f"No financial statement in Sbírka listin for {company.ico}.{hint}"
        )
    statements = [
        extract_financials(load_pdf(filing), llm=llm) for filing in statements_filings
    ]
    report = analyze_statements(
        statements,
        ico=company.ico,
        insolvency_check=insolvency_check,
        vat_check=vat_check,
    )
    report.company_name = report.company_name or company.name
    report.source_filing_title = statements_filings[0].title
    return report


def analyze_statements(
    statements: list[FinancialStatement],
    *,
    ico: str | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
    subsidy_check: Callable[[str], SubsidyReport] | None = None,
    contract_check: Callable[[str], ContractReport] | None = None,
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
    normalized_all = [normalize(s) for s in ordered]
    current = ordered[0]
    normalized = normalized_all[0]
    ratios = compute_ratios(normalized)
    resolved_ico = ico or current.ico
    insolvent = None
    unreliable_vat = None
    subsidies_total = None
    contracts_total = None
    public_money_ratio = None
    if resolved_ico:
        insolvency_check = insolvency_check or check_insolvency
        vat_check = vat_check or check_vat
        status = insolvency_check(resolved_ico)
        insolvent = status.in_insolvency if status.checked else None
        unreliable_vat = vat_check(resolved_ico).is_unreliable
        # subsidy_check/contract_check stay None by default (unlike insolvency/vat) so keyless callers never trigger a live HTTP call here
        if subsidy_check:
            subsidies_total = subsidy_check(resolved_ico).total_amount
        if contract_check:
            contracts_total = contract_check(resolved_ico).total_value
        if (
            normalized.revenue
            and normalized.revenue > 0
            and (subsidies_total is not None or contracts_total is not None)
        ):
            public_total = (subsidies_total or 0.0) + (contracts_total or 0.0)
            public_money_ratio = public_total / normalized.revenue
    red_flags = detect_red_flags(
        normalized,
        ratios,
        current.notes,
        insolvent=insolvent,
        unreliable_vat=unreliable_vat,
        public_money_ratio=public_money_ratio,
    )
    trends = compute_trends(normalized, normalized_all[1]) if len(ordered) > 1 else []
    yearly = [
        YearlyFigures(
            period_year=n.period_year,
            revenue=n.revenue,
            net_profit=n.net_profit,
            total_assets=n.total_assets,
            equity=n.equity,
        )
        for n in normalized_all
    ]
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
        yearly=yearly,
        subsidies_total=subsidies_total,
        contracts_total=contracts_total,
        public_money_ratio=public_money_ratio,
    )
