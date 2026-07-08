from unittest.mock import patch

import pytest

import rejstrik.service as service
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import Figure, FinancialStatement, NoteItem
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.models import Company
from rejstrik.registry.vat import VatStatus

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
        report = service.analyze_company_financials(
            "Test",
            vat_check=lambda ico: VatStatus(ico=ico, is_vat_payer=False),
        )
    assert isinstance(report, CompanyFinancialReport)
    assert report.ico == "00006947"
    assert report.normalized.total_assets == 1000.0
    codes = {flag.code for flag in report.red_flags}
    assert {"negative_equity", "net_loss", "going_concern"} <= codes
    assert report.trends == []
    assert report.source_filing_title == "Účetní závěrka 2023"


def _wire_source(monkeypatch, filings):
    monkeypatch.setattr(
        service,
        "find_company",
        lambda q, client=None: Company(ico="00514152", name="Budvar"),
    )
    monkeypatch.setattr(service, "list_filings", lambda ico, client=None: filings)
    monkeypatch.setattr(
        service,
        "load_pdf",
        lambda filing, client=None: PdfSource(data=b"x", sha256="s", filename="f.pdf"),
    )


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}",
        year=year,
        pdf_url=f"https://x/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_resolve_statement_source_by_year(monkeypatch):
    _wire_source(monkeypatch, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    _company, filing, _source = service.resolve_statement_source("Budvar", year=2023)
    assert filing.year == 2023


def test_resolve_statement_source_missing_year_lists_available(monkeypatch):
    _wire_source(monkeypatch, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    with pytest.raises(service.NoStatementFound) as exc:
        service.resolve_statement_source("Budvar", year=2000)
    assert "2024" in str(exc.value) and "2023" in str(exc.value)


class _FakeLLM:
    """Returns a statement whose revenue encodes the filing year."""

    _REVENUE = {2024: 1000.0, 2023: 800.0, 2022: 600.0}

    def extract(self, source, schema, instructions):
        # filename carries the year via our fake load_pdf below
        year = int(source.filename.split("-")[0])
        return FinancialStatement(
            company_name="Budvar",
            ico="00514152",
            period_year=year,
            currency="CZK",
            income_statement=[Figure(label="Tržby", value=self._REVENUE[year])],
        )

    def ask(self, source, question):  # pragma: no cover - unused here
        raise NotImplementedError


def _wire_multiyear(monkeypatch):
    monkeypatch.setattr(
        service,
        "find_company",
        lambda q, client=None: Company(ico="00514152", name="Budvar"),
    )
    monkeypatch.setattr(
        service,
        "list_filings",
        lambda ico, client=None: [
            _fin(2024, "aaa"),
            _fin(2023, "bbb"),
            _fin(2022, "ccc"),
        ],
    )
    monkeypatch.setattr(
        service,
        "load_pdf",
        lambda filing, client=None: PdfSource(
            data=b"x", sha256="s", filename=f"{filing.year}-f.pdf"
        ),
    )


def test_analyze_company_financials_multiyear_computes_trends(monkeypatch):
    _wire_multiyear(monkeypatch)
    report = service.analyze_company_financials(
        "Budvar",
        years=3,
        llm=_FakeLLM(),
        insolvency_check=lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False),
        vat_check=lambda ico: VatStatus(
            ico=ico, dic="CZ00514152", is_vat_payer=True, is_unreliable=False
        ),
    )
    assert report.period_year == 2024
    revenue = next(t for t in report.trends if t.metric == "revenue")
    assert revenue.current == 1000.0 and revenue.prior == 800.0


def test_analyze_company_financials_clamps_years(monkeypatch):
    _wire_multiyear(monkeypatch)
    captured = {}
    real = service.analyze_statements

    def spy(statements, **kw):
        captured["n"] = len(statements)
        return real(statements, **kw)

    monkeypatch.setattr(service, "analyze_statements", spy)
    service.analyze_company_financials(
        "Budvar",
        years=99,
        llm=_FakeLLM(),
        insolvency_check=lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False),
        vat_check=lambda ico: VatStatus(
            ico=ico, dic="X", is_vat_payer=True, is_unreliable=False
        ),
    )
    assert captured["n"] == 3  # only 3 filings exist, and 99 clamps to 5
