from rejstrik.documents.llm import pdf_block
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF-1.4 x", sha256="deadbeef", filename="f.pdf")


def test_pdf_block_is_base64_document():
    block = pdf_block(SRC)
    assert block["type"] == "document"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "application/pdf"
    import base64

    assert block["source"]["data"] == base64.standard_b64encode(SRC.data).decode()
    assert "citations" not in block
    assert "cache_control" not in block


def test_pdf_block_citations_and_cache_flags():
    block = pdf_block(SRC, citations=True, cache=True)
    assert block["citations"] == {"enabled": True}
    assert block["cache_control"] == {"type": "ephemeral"}
