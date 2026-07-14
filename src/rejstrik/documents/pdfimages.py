"""Rasterize PDF pages to PNG with pypdfium2 — keyless, no OCR.

The host model is the OCR engine (project design stance); this module only
delivers legible page images. PNG is encoded from the raw RGBA buffer with the
standard library (zlib/struct) so pypdfium2 stays the only new dependency.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pypdfium2 as pdfium
from pydantic import BaseModel

_POINTS_PER_INCH = 72.0


class PageImage(BaseModel):
    page: int
    png_base64: str
    width: int
    height: int


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _encode_png_rgba(buffer: bytes, width: int, height: int, stride: int) -> bytes:
    """Encode an RGBA byte buffer (row length ``stride``) as an 8-bit RGBA PNG."""
    row_bytes = width * 4
    raw = bytearray()
    for y in range(height):
        start = y * stride
        raw.append(0)  # PNG filter type 0 (None)
        raw.extend(buffer[start : start + row_bytes])
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit, RGBA
    idat = zlib.compress(bytes(raw))
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def render_page_images(
    data: bytes,
    pages: list[int],
    *,
    dpi: int = 150,
    max_long_side: int = 1600,
) -> list[PageImage]:
    """Render the given 1-based page numbers to PNG. Out-of-range pages are
    skipped. Rendered so the longest side never exceeds ``max_long_side`` px."""
    pdf = pdfium.PdfDocument(data)
    try:
        total = len(pdf)
        out: list[PageImage] = []
        for page_no in pages:
            if page_no < 1 or page_no > total:
                continue
            page = pdf[page_no - 1]
            width_pt, height_pt = page.get_size()
            longest_pt = max(width_pt, height_pt)
            scale = dpi / _POINTS_PER_INCH
            if longest_pt * scale > max_long_side and longest_pt > 0:
                scale = max_long_side / longest_pt
            bitmap = page.render(scale=scale, rev_byteorder=True)
            png = _encode_png_rgba(
                bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.stride
            )
            out.append(
                PageImage(
                    page=page_no,
                    png_base64=base64.standard_b64encode(png).decode(),
                    width=bitmap.width,
                    height=bitmap.height,
                )
            )
            bitmap.close()
            page.close()
        return out
    finally:
        pdf.close()
