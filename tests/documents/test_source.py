import hashlib
from pathlib import Path

import httpx
import respx

from rejstrik.documents.source import load_pdf, PdfSource
from rejstrik.filings.models import Filing

PDF_BYTES = b"%PDF-1.4 fake pdf bytes"


def test_load_pdf_from_local_path(tmp_path: Path):
    p = tmp_path / "report.pdf"
    p.write_bytes(PDF_BYTES)
    src = load_pdf(str(p))
    assert isinstance(src, PdfSource)
    assert src.data == PDF_BYTES
    assert src.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert src.filename == "report.pdf"


@respx.mock
def test_load_pdf_from_url():
    url = "https://or.justice.cz/ias/content/download?id=abc"
    respx.get(url).mock(return_value=httpx.Response(200, content=PDF_BYTES))
    src = load_pdf(url)
    assert src.data == PDF_BYTES
    assert src.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()


@respx.mock
def test_load_pdf_from_filing_uses_pdf_url():
    url = "https://or.justice.cz/ias/content/download?id=xyz"
    respx.get(url).mock(return_value=httpx.Response(200, content=PDF_BYTES))
    filing = Filing(
        title="Účetní závěrka 2023", year=2023, pdf_url=url, is_financial_statement=True
    )
    src = load_pdf(filing)
    assert src.data == PDF_BYTES
