import asyncio
import base64
import io
import warnings

from mcp.types import ImageContent, TextContent
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

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _pdf_bytes(pages: int) -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_TEXT_PDF_RAW)))
        for _ in range(pages - 1):
            writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)
    return buf.getvalue()


def _fake_fetch(pdf: bytes, page_count: int):
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
            page_count=page_count,
        )
        return doc, PdfSource(data=pdf, sha256=doc.sha256, filename="x.pdf")

    return _inner


def test_returns_metadata_then_png_images(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes(2), 2))
    parts = server.read_filing_page_images("00514152", pages="1-2")
    assert isinstance(parts[0], TextContent)
    images = [p for p in parts if isinstance(p, ImageContent)]
    assert len(images) == 2
    for im in images:
        assert im.mimeType == "image/png"
        assert base64.standard_b64decode(im.data).startswith(_PNG_MAGIC)


def test_caps_at_five_pages(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes(8), 8))
    parts = server.read_filing_page_images("00514152", pages="1-8")
    images = [p for p in parts if isinstance(p, ImageContent)]
    assert len(images) == 5
    assert isinstance(parts[0], TextContent)
    assert "capped" in parts[0].text.lower()


def test_registered_and_exposed():
    assert "read_filing_page_images" in server.EXPOSED_TOOL_NAMES
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "read_filing_page_images" in names
