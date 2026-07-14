import io
import warnings

from pypdf import PdfReader, PdfWriter

from rejstrik.documents.pdftext import (
    PageText,
    extract_pages_text,
    parse_page_range,
)

# Minimal one-page PDF with a real text layer, plus one appended blank page.
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


def _two_page_text_then_blank() -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_TEXT_PDF_RAW)))
        writer.add_blank_page(width=300, height=300)  # page 2: no text layer
        buf = io.BytesIO()
        writer.write(buf)
    return buf.getvalue()


def test_parse_single_page():
    pages, msg = parse_page_range("3", page_count=10)
    assert pages == [3]
    assert msg is None


def test_parse_range_and_list():
    pages, _ = parse_page_range("1-3,7", page_count=10)
    assert pages == [1, 2, 3, 7]


def test_parse_dedup_and_clamp():
    pages, _ = parse_page_range("1-3,2,99", page_count=5)
    assert pages == [1, 2, 3]


def test_parse_over_cap_is_honest():
    pages, msg = parse_page_range("1-30", page_count=30, max_pages=20)
    assert pages == list(range(1, 21))
    assert msg is not None and "20" in msg


def test_extract_returns_text_for_text_layer():
    data = _two_page_text_then_blank()
    result = extract_pages_text(data, [1])
    assert isinstance(result[0], PageText)
    assert result[0].has_text is True
    assert "Rozvaha 2024" in result[0].text


def test_extract_is_honest_about_no_text_layer():
    data = _two_page_text_then_blank()
    result = extract_pages_text(data, [2])
    assert result[0].has_text is False
    assert result[0].text == ""
    assert result[0].note is not None
    assert "extract_financials" in result[0].note
