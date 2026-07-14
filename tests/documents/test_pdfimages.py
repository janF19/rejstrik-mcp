import base64
import io
import warnings

from pypdf import PdfReader, PdfWriter

from rejstrik.documents.pdfimages import PageImage, render_page_images

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


def _two_page_pdf() -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_TEXT_PDF_RAW)))
        writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)
    return buf.getvalue()


def test_render_returns_png_images_for_requested_pages():
    images = render_page_images(_two_page_pdf(), [1, 2])
    assert len(images) == 2
    assert [im.page for im in images] == [1, 2]
    for im in images:
        assert isinstance(im, PageImage)
        raw = base64.standard_b64decode(im.png_base64)
        assert raw.startswith(_PNG_MAGIC)
        assert im.width > 0 and im.height > 0


def test_render_caps_longest_side():
    images = render_page_images(_two_page_pdf(), [1], dpi=600, max_long_side=400)
    assert max(images[0].width, images[0].height) <= 400


def test_render_skips_out_of_range_pages():
    images = render_page_images(_two_page_pdf(), [1, 99])
    assert [im.page for im in images] == [1]
