from unittest.mock import patch

import pytest

import rejstrik.service as service
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import Figure, FinancialStatement, NoteItem
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.models import Company

COMPANY = Company(ico="00006947", name="Budějovický Budvar")
FILINGS = [
    Filing(
        title="Účetní závěrka 2023",
        year=2023,
        pdf_url="https://example.test/fs-2023.pdf",
        is_financial_statement=True,
    )
]
SRC = PdfSource(data=b"%PDF-1.4 fake", sha256="abc", filename="fs-2023.pdf")
STATEMENT = FinancialStatement(
    company_name="Budějovický Budvar",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    balance_sheet=[
        Figure(label="Aktiva celkem", value=1000.0),
        Figure(label="Vlastní kapitál", value=-50.0),
        Figure(label="Oběžná aktiva", value=100.0),
        Figure(label="Krátkodobé závazky", value=300.0),
        Figure(label="Cizí zdroje", value=600.0),
    ],
    income_statement=[
        Figure(label="Tržby", value=2000.0),
        Figure(label="Výsledek hospodaření za účetní období", value=-10.0),
    ],
    notes=[
        NoteItem(
            topic="Going concern",
            summary="Material uncertainty about going concern.",
        )
    ],
)


def test_resolve_statement_source_returns_company_filing_and_pdf():
    with (
        patch.object(service, "find_company", return_value=COMPANY),
        patch.object(service, "list_filings", return_value=FILINGS),
        patch.object(service, "load_pdf", return_value=SRC),
    ):
        company, filing, source = service.resolve_statement_source("Test")
    assert company.ico == "00006947"
    assert filing.year == 2023
    assert source is SRC


def test_resolve_raises_when_no_statement():
    with (
        patch.object(service, "find_company", return_value=COMPANY),
        patch.object(service, "list_filings", return_value=[]),
    ):
        with pytest.raises(service.NoStatementFound):
            service.resolve_statement_source("Test")


def test_analyze_company_financials_assembles_report_with_flags():
    insolvency = InsolvencyStatus(
        ico="00006947",
        in_insolvency=False,
        cases=[],
        checked=False,
    )
    with (
        patch.object(service, "find_company", return_value=COMPANY),
        patch.object(service, "list_filings", return_value=FILINGS),
        patch.object(service, "load_pdf", return_value=SRC),
        patch.object(service, "extract_financials", return_value=STATEMENT),
        patch.object(service, "check_insolvency", return_value=insolvency),
    ):
        report = service.analyze_company_financials("Test")
    assert isinstance(report, CompanyFinancialReport)
    assert report.ico == "00006947"
    assert report.normalized.total_assets == 1000.0
    codes = {flag.code for flag in report.red_flags}
    assert {"negative_equity", "net_loss", "going_concern"} <= codes
    assert report.trends == []
    assert report.source_filing_title == "Účetní závěrka 2023"
