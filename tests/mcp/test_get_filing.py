import asyncio
import base64
import hashlib
import json

from mcp.types import EmbeddedResource, TextContent

from rejstrik.documents.source import PdfSource
from rejstrik.mcp import server
from rejstrik.service import FilingDocument

_PDF = b"%PDF-1.4 fake"


def _fake_fetch(query, year=None, filing_id=None):
    doc = FilingDocument(
        ico="00514152",
        company_name="Budvar",
        title="ucetni zaverka 2024",
        year=2024,
        pdf_url="https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/aaa",
        file_path="/cache/00514152-2024-abcd1234.pdf",
        sha256=hashlib.sha256(_PDF).hexdigest(),
        size_bytes=len(_PDF),
    )
    return doc, PdfSource(data=_PDF, sha256=doc.sha256, filename="filing.pdf")


def test_get_filing_returns_metadata_and_blob(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch)
    parts = server.get_filing("00514152")
    assert isinstance(parts[0], TextContent)
    meta = json.loads(parts[0].text)
    assert meta["year"] == 2024
    assert meta["file_path"].endswith(".pdf")
    blob_part = parts[1]
    assert isinstance(blob_part, EmbeddedResource)
    assert blob_part.resource.mimeType == "application/pdf"
    assert base64.standard_b64decode(blob_part.resource.blob) == _PDF


def test_get_filing_skips_blob_when_too_large(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch)
    monkeypatch.setattr(server, "_MAX_EMBED_BYTES", 4)
    parts = server.get_filing("00514152")
    assert len(parts) == 2
    assert isinstance(parts[1], TextContent)
    assert "file_path" in parts[1].text


def test_get_filing_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert "get_filing" in {t.name for t in tools}
