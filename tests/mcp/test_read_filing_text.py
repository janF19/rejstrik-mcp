import asyncio
import io
import warnings

from pypdf import PdfReader, PdfWriter

from rejstrik.documents.source import PdfSource
from rejstrik.mcp import server
from rejstrik.service import FilingDocument

_TEXT_PDF_RAW = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj
4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
5 0 obj<</Length 44>>stream
BT /F1 24 Tf 40 150 Td (Rozvaha 2024) Tj ET
endstream endobj
xref
0 6
0000000000 65535 f
trailer<</Root 1 0 R/Size 6>>
startxref
0
%%EOF"""


def _pdf_bytes() -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_TEXT_PDF_RAW)))
        writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)
    return buf.getvalue()


def _fake_fetch(pdf: bytes):
    def _inner(query, year=None, filing_id=None):
        import hashlib

        doc = FilingDocument(
            ico="00514152",
            company_name="Budvar",
            title="ucetni zaverka 2024",
            year=2024,
            pdf_url="https://verejnerejstriky.msp.gov.cz/x",
            file_path="/tmp/x.pdf",
            sha256=hashlib.sha256(pdf).hexdigest(),
            size_bytes=len(pdf),
            page_count=2,
        )
        return doc, PdfSource(data=pdf, sha256=doc.sha256, filename="x.pdf")

    return _inner


def test_read_filing_text_returns_text_page(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes()))
    result = server.read_filing_text("00514152", pages="1")
    assert result.page_count == 2
    assert result.requested_pages == [1]
    assert result.pages[0].has_text is True
    assert "Rozvaha 2024" in result.pages[0].text


def test_read_filing_text_is_honest_about_scanned_page(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes()))
    result = server.read_filing_text("00514152", pages="2")
    assert result.pages[0].has_text is False
    assert result.pages[0].note is not None
    assert result.pages[0].text == ""


def test_read_filing_text_registered_and_exposed():
    assert "read_filing_text" in server.EXPOSED_TOOL_NAMES
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "read_filing_text" in names
