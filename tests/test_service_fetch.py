import hashlib

import pytest

from rejstrik import service
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company
from rejstrik.service import NoStatementFound, fetch_filing

_PDF = b"%PDF-1.4 fake"


def _wire(monkeypatch, tmp_path, filings):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        service,
        "find_company",
        lambda q, client=None: Company(ico="00514152", name="Budvar"),
    )
    monkeypatch.setattr(service, "list_filings", lambda ico, client=None: filings)
    monkeypatch.setattr(
        service,
        "load_pdf",
        lambda filing, client=None: PdfSource(
            data=_PDF, sha256=hashlib.sha256(_PDF).hexdigest(), filename="filing.pdf"
        ),
    )


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}",
        year=year,
        pdf_url=f"https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_fetch_filing_latest(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    doc, source = fetch_filing("Budvar")
    assert doc.year == 2024
    assert doc.ico == "00514152"
    assert doc.company_name == "Budvar"
    assert doc.size_bytes == len(_PDF)
    assert doc.file_path.endswith(".pdf")
    assert source.data == _PDF


def test_fetch_filing_by_year(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    doc, _ = fetch_filing("Budvar", year=2023)
    assert doc.year == 2023


def test_fetch_filing_missing_year_lists_available(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    with pytest.raises(NoStatementFound) as exc:
        fetch_filing("Budvar", year=2019)
    assert "2024" in str(exc.value) and "2023" in str(exc.value)


def test_fetch_filing_no_financials(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [])
    with pytest.raises(NoStatementFound):
        fetch_filing("Budvar")
