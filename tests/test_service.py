from unittest.mock import patch

import pytest

from rejstrik import service
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
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
        pytest.raises(service.NoStatementFound),
    ):
        service.resolve_statement_source("Test")


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
