import asyncio
import base64
import hashlib
import json

from mcp.types import EmbeddedResource, TextContent

from rejstrik.documents.source import PdfSource
from rejstrik.mcp import server
from rejstrik.service import FilingDocument

_PDF = b"%PDF-1.4 fake"


def _make_fake_fetch(file_path):
    def _fake_fetch(query, year=None, filing_id=None):
        doc = FilingDocument(
            ico="00514152",
            company_name="Budvar",
            title="ucetni zaverka 2024",
            year=2024,
            pdf_url="https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/aaa",
            file_path=str(file_path),
            sha256=hashlib.sha256(_PDF).hexdigest(),
            size_bytes=len(_PDF),
        )
        return doc, PdfSource(data=_PDF, sha256=doc.sha256, filename="filing.pdf")

    return _fake_fetch


def test_get_filing_returns_metadata_and_blob(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    parts = server.get_filing("00514152")
    assert isinstance(parts[0], TextContent)
    meta = json.loads(parts[0].text)
    assert meta["year"] == 2024
    assert meta["file_path"].endswith(".pdf")
    blob_part = parts[1]
    assert isinstance(blob_part, EmbeddedResource)
    assert blob_part.resource.mimeType == "application/pdf"
    assert base64.standard_b64decode(blob_part.resource.blob) == _PDF


def test_get_filing_skips_blob_when_too_large(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    monkeypatch.setattr(server, "_MAX_EMBED_BYTES", 4)
    parts = server.get_filing("00514152")
    assert len(parts) == 2
    assert isinstance(parts[1], TextContent)
    assert "file_path" in parts[1].text


def test_get_filing_falls_back_when_path_not_absolute(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch("cache/rel.pdf"))
    parts = server.get_filing("00514152")
    assert len(parts) == 2
    assert isinstance(parts[1], TextContent)
    assert "rel.pdf" in parts[1].text


def test_get_filing_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert "get_filing" in {t.name for t in tools}


def test_get_filing_never_skips_blob(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    parts = server.get_filing("00514152", embed="never")
    assert all(isinstance(p, TextContent) for p in parts)
    assert any("file_path" in p.text for p in parts if isinstance(p, TextContent))


def test_get_filing_always_embeds_within_cap(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    parts = server.get_filing("00514152", embed="always")
    assert isinstance(parts[1], EmbeddedResource)


def test_get_filing_always_over_cap_is_honest(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    monkeypatch.setattr(server, "_MAX_EMBED_BYTES", 4)
    parts = server.get_filing("00514152", embed="always")
    assert isinstance(parts[1], TextContent)
    assert "too large" in parts[1].text.lower()


def test_get_filing_default_embed_cap_is_25mb():
    assert server._MAX_EMBED_BYTES == 25000000


def test_get_filing_metadata_carries_page_count(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    parts = server.get_filing("00514152")
    import json

    meta = json.loads(parts[0].text)
    assert "page_count" in meta
