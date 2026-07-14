# Stage G (Features, v0.7.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four Stage G features — scanned-filing page images, Damodaran-Europe NACE-mapped valuation multiples, a short-TTL `list_filings` cache, and a canary auto-issue workflow — from the approved spec `docs/superpowers/specs/2026-07-14-post-audit-hardening-and-features-design.md` (sections G1–G4).

**Architecture:** New keyless MCP tool `read_filing_page_images` rasterizes PDF pages to PNG with pypdfium2 (no OCR — the host model is the OCR engine). Valuation gains a vendored Damodaran-Europe EV/EBITDA dataset keyed by a ported `NACE_DIVISION_MAP`; NACE is only a mapping key, never a hand-tuned multiple. `list_filings` gets an in-process TTL cache with an injectable clock. The canary workflow opens/updates a single tracking issue on failure. All new tests are offline and key-free per CLAUDE.md.

**Tech Stack:** Python 3.11/3.12, pydantic v2, httpx, pypdf (existing), **pypdfium2 (new runtime dep)**, xlrd (manual-tooling-only, not a runtime dep), FastMCP, pytest + respx, ruff.

## Global Constraints

- Tests are offline and key-free. Mock the LLM via the `DocumentLLM` protocol and registry checks via the `*_check` injection points. No network, no LLM in any test.
- TDD per CLAUDE.md: failing test → minimal impl → green → commit. One commit per task.
- **Every task ends with:** `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` (all green).
- Live/network tooling lives in `scripts/` (like `scripts/smoke.py`) and is **never** run in CI or tests. The Damodaran importer is such tooling; tests read only the committed JSON dataset.
- `NACE_DIVISION_MAP` is ported **verbatim** from `~/projects/obchodni-rejstrik-ai/apps/api/services/business_classification.py`. Any deviation is listed in the "Deviations for product-owner sign-off" section at the end of this plan — never changed silently.
- `read_filing_page_images` caps at **5 pages per call**. `read_filing_text`'s 20-page cap is unchanged.
- Statements-only `estimate_valuation` calls (no `ico`, no `industry_key`) must keep their existing field values and caveats unchanged (see Deviations §1 for the exact interpretation of the spec's "byte-identical" wording).
- pypdfium2 must have prebuilt wheels for the CI matrix (Linux + Windows, py3.11/3.12). Task 1 Step 0 verifies this before any code is written.

---

## File Structure

**Created:**
- `src/rejstrik/documents/pdfimages.py` — pypdfium2 rasterizer + minimal stdlib PNG encoder (G1).
- `src/rejstrik/analysis/data/industry_multiples.json` — vendored Damodaran-Europe dataset (G2).
- `src/rejstrik/analysis/industry_multiples.py` — dataset loader (G2, ported from reference).
- `src/rejstrik/analysis/industry.py` — `NACE_DIVISION_MAP` + `industry_key_for_nace` (G2, ported).
- `scripts/import_damodaran_multiples.py` — manual importer (G2, ported; network, never in CI).
- `tests/documents/test_pdfimages.py`, `tests/mcp/test_read_filing_page_images.py` (G1).
- `tests/analysis/test_industry_multiples.py`, `tests/analysis/test_industry.py` (G2).
- `tests/filings/test_filings_cache.py` (G3).

**Modified:**
- `pyproject.toml` — add `pypdfium2` dependency; bump version (final task).
- `src/rejstrik/mcp/server.py` — new tool, `ImageContent` import, `estimate_valuation` wiring, steering text.
- `src/rejstrik/documents/pdftext.py` — steer `_NO_TEXT_NOTE` to the new tool.
- `src/rejstrik/registry/models.py`, `src/rejstrik/registry/ares.py` — `Company.nace_codes` + parse.
- `src/rejstrik/documents/schema.py`, `src/rejstrik/analysis/normalize.py` — `depreciation_amortization`.
- `src/rejstrik/analysis/valuation.py` — industry multiple + EBITDA + provenance.
- `src/rejstrik/filings/justice.py` — TTL cache.
- `.github/workflows/canary.yml` — auto-issue on failure.
- `src/rejstrik/__init__.py`, `server.json`, `mcpb/manifest.json` — version bump (final task).
- `README.md` — dataset provenance + regeneration note.

---

## Task 1: pypdfium2 dependency + PNG rasterizer module (G1)

**Files:**
- Modify: `pyproject.toml` (dependencies list)
- Create: `src/rejstrik/documents/pdfimages.py`
- Test: `tests/documents/test_pdfimages.py`

**Interfaces:**
- Produces:
  - `class PageImage(BaseModel)` with fields `page: int`, `png_base64: str`, `width: int`, `height: int`.
  - `def render_page_images(data: bytes, pages: list[int], *, dpi: int = 150, max_long_side: int = 1600) -> list[PageImage]` — rasterizes the given 1-based page numbers to PNG (color type RGBA), base64-encoded. Pages out of range are skipped (returns fewer items).

- [x] **Step 0: Confirm pypdfium2 wheel availability, then install it**

Run: `pip index versions pypdfium2` (or check https://pypi.org/project/pypdfium2/#files) and confirm prebuilt wheels exist for `manylinux`, `win_amd64`, cp311 and cp312. pypdfium2 ships platform wheels with the PDFium binary bundled (no system deps).
Then: `pip install pypdfium2`
Expected: install succeeds; `python -c "import pypdfium2 as p; print(p.PdfDocument)"` prints a class.

- [x] **Step 1: Add the runtime dependency**

In `pyproject.toml`, add `"pypdfium2>=4"` to the `dependencies` list (immediately after `"pypdf>=5",`):

```toml
    "pypdf>=5",
    "pypdfium2>=4",
    "mcp>=1.2",
```

- [x] **Step 2: Write the failing test**

Create `tests/documents/test_pdfimages.py`:

```python
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
```

- [x] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/documents/test_pdfimages.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rejstrik.documents.pdfimages'`.

- [x] **Step 4: Write the minimal implementation**

Create `src/rejstrik/documents/pdfimages.py`:

```python
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
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/documents/test_pdfimages.py -q`
Expected: PASS (3 passed).

- [x] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green. (If `ruff format --check` complains, run `ruff format src/ tests/` and re-run.)

- [x] **Step 7: Commit**

```bash
git add pyproject.toml src/rejstrik/documents/pdfimages.py tests/documents/test_pdfimages.py
git commit -m "feat(documents): rasterize PDF pages to PNG via pypdfium2"
```

---

## Task 2: `read_filing_page_images` MCP tool + steering (G1)

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Modify: `src/rejstrik/documents/pdftext.py` (`_NO_TEXT_NOTE`)
- Test: `tests/mcp/test_read_filing_page_images.py`

**Interfaces:**
- Consumes: `render_page_images` and `PageImage` from Task 1; existing `parse_page_range`, `_fetch_filing`, `count_pdf_pages`.
- Produces: MCP tool `read_filing_page_images(ico, year=None, filing_id=None, pages="1-5") -> list[TextContent | ImageContent]` (metadata TextContent first, then one ImageContent per rendered page). Added to `EXPOSED_TOOL_NAMES`.

- [x] **Step 1: Write the failing test**

Create `tests/mcp/test_read_filing_page_images.py`:

```python
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
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/mcp/test_read_filing_page_images.py -q`
Expected: FAIL with `AttributeError: module 'rejstrik.mcp.server' has no attribute 'read_filing_page_images'`.

- [x] **Step 3: Add the `ImageContent` import to `server.py`**

In `src/rejstrik/mcp/server.py`, extend the `mcp.types` import block (currently `BlobResourceContents, EmbeddedResource, TextContent, ToolAnnotations`) to include `ImageContent`:

```python
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    ImageContent,
    TextContent,
    ToolAnnotations,
)
```

- [x] **Step 4: Add the `render_page_images` import to `server.py`**

Immediately after the existing `from rejstrik.documents.pdftext import ...` line, add:

```python
from rejstrik.documents.pdfimages import render_page_images
```

- [x] **Step 5: Register the tool name**

In `EXPOSED_TOOL_NAMES`, add `"read_filing_page_images"` immediately after `"read_filing_text"`:

```python
    "read_filing_text",
    "read_filing_page_images",
    "estimate_valuation",
```

- [x] **Step 6: Implement the tool**

In `src/rejstrik/mcp/server.py`, immediately after the `read_filing_text` function (after its `return FilingText(...)` block, before `analyze_financials`), add:

```python
@mcp.tool(annotations=_ro("Read filing page images"), structured_output=False)
def read_filing_page_images(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    pages: str = "1-5",
) -> list[TextContent | ImageContent]:
    """Rasterize statement PDF pages to PNG images — keyless, no LLM, no OCR.
    For SCANNED filings with no text layer (read_filing_text reports
    has_text=false) on hosts WITHOUT filesystem access: this delivers legible
    page images the host model can read directly. Page grammar: "3", "1-5",
    "1-3,5" (default "1-5"). At most 5 pages per call (images are token-heavy);
    request later ranges for the rest. Returns one metadata text block, then one
    PNG image per rendered page."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    page_count = doc.page_count or count_pdf_pages(source.data) or 0
    requested, message = parse_page_range(pages, page_count=page_count, max_pages=5)
    images = render_page_images(source.data, requested)
    meta = {
        "ico": doc.ico,
        "year": doc.year,
        "page_count": page_count,
        "rendered_pages": [im.page for im in images],
        "message": message,
    }
    parts: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(meta, indent=2))
    ]
    for im in images:
        parts.append(
            ImageContent(type="image", data=im.png_base64, mimeType="image/png")
        )
    return parts
```

- [x] **Step 7: Steer `read_filing_text`'s no-text note to the new tool**

In `src/rejstrik/documents/pdftext.py`, replace `_NO_TEXT_NOTE`:

```python
_NO_TEXT_NOTE = (
    "No extractable text layer on this page — the filing is likely a scanned "
    "image. Read the PDF from file_path with your own capabilities, call the "
    "keyed extract_financials tool, or — on a host without filesystem access — "
    "call read_filing_page_images for this page range to get legible PNGs."
)
```

- [x] **Step 8: Steer the `analyze-company` prompt (step 3)**

In `src/rejstrik/mcp/server.py`, in `analyze_company_prompt`, replace the tail of step 3 (the sentence beginning "Otherwise use the embedded resource, or call read_filing_text...") so it reads:

```python
   embedded resource, or call read_filing_text(ico, year=..., pages="1-10") to
   pull the text layer in digestible slices. If read_filing_text reports
   has_text=false (a scanned filing) and you cannot read local files, call
   read_filing_page_images(ico, year=..., pages="1-5") to get the pages as PNGs.
```

- [x] **Step 9: Run the test to verify it passes**

Run: `python -m pytest tests/mcp/test_read_filing_page_images.py -q`
Expected: PASS (3 passed).

- [x] **Step 10: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 11: Commit**

```bash
git add src/rejstrik/mcp/server.py src/rejstrik/documents/pdftext.py tests/mcp/test_read_filing_page_images.py
git commit -m "feat(mcp): add keyless read_filing_page_images tool for scanned filings"
```

---

## Task 3: Vendor the Damodaran dataset + importer script (G2)

**Files:**
- Create: `src/rejstrik/analysis/data/industry_multiples.json` (copied from the reference vendored dataset — real Damodaran-Europe data)
- Create: `scripts/import_damodaran_multiples.py` (ported manual tooling)
- Modify: `README.md` (regeneration note)

**Interfaces:**
- Produces: the committed JSON at `src/rejstrik/analysis/data/industry_multiples.json` with top-level `source`, `source_url`, `as_of`, `region`, `metric`, and `rows` (each row: `industry_key`, `source_industry`, `firms`, `ev_ebitda`). Includes a `total_market_ex_financials` row. Loaded by Task 4.

> **Note:** The importer is manual, network-using tooling like `scripts/smoke.py`. It is NEVER run in CI or tests. The dataset it produces is committed and versioned; tests read only the committed file. Because we cannot run the network importer here, Step 1 copies the already-vendored, importer-produced dataset from the reference project verbatim.

- [x] **Step 1: Copy the vendored dataset into the package**

```bash
mkdir -p src/rejstrik/analysis/data
cp ~/projects/obchodni-rejstrik-ai/apps/api/data/valuation/industry_multiples_2026.json \
   src/rejstrik/analysis/data/industry_multiples.json
```

- [x] **Step 2: Verify the copied dataset shape**

Run:
```bash
python -c "import json; d=json.load(open('src/rejstrik/analysis/data/industry_multiples.json')); print('rows', len(d['rows'])); print('keys', sorted(d.keys())); print('fallback', any(r['industry_key']=='total_market_ex_financials' for r in d['rows']))"
```
Expected: `rows 94` (or ≥60), `keys ['as_of', 'metric', 'region', 'rows', 'source', 'source_url']`, `fallback True`.

- [x] **Step 3: Ensure the JSON ships in the wheel**

In `pyproject.toml`, under `[tool.hatch.build.targets.wheel]`, the line `packages = ["src/rejstrik"]` already globs the package tree; JSON data files under `src/rejstrik/analysis/data/` are included automatically by hatchling. Confirm by running:
```bash
python -m build --wheel 2>/dev/null && python -c "import zipfile,glob; w=sorted(glob.glob('dist/*.whl'))[-1]; print([n for n in zipfile.ZipFile(w).namelist() if n.endswith('industry_multiples.json')])"
```
Expected: a list containing `rejstrik/analysis/data/industry_multiples.json`. If empty, add to `pyproject.toml`:
```toml
[tool.hatch.build.targets.wheel.force-include]
"src/rejstrik/analysis/data/industry_multiples.json" = "rejstrik/analysis/data/industry_multiples.json"
```
(Clean up `dist/` afterward: `rm -rf dist build`.)

- [x] **Step 4: Port the importer script**

Create `scripts/import_damodaran_multiples.py` (adapted paths; manual tooling — needs `pip install xlrd`; network; never in CI):

```python
"""Manual importer for Damodaran Europe EV/EBITDA industry multiples.

Network-using manual tooling like scripts/smoke.py — NEVER run in CI or tests.
Tests read only the committed JSON. Requires xlrd:  pip install xlrd

Usage:  python scripts/import_damodaran_multiples.py [--as-of YYYY-MM-DD]
Writes: src/rejstrik/analysis/data/industry_multiples.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import httpx
import xlrd

SOURCE_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/vebitdaEurope.xls"
SOURCE = "Damodaran Europe industry EV/EBITDA"
REGION = "Europe"
METRIC = "EV/EBITDA for positive EBITDA firms"
DEFAULT_AS_OF = "2026-01-05"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "rejstrik"
    / "analysis"
    / "data"
    / "industry_multiples.json"
)
SHEET_NAME = "Industry Averages"
TOTAL_MARKET_EX_FINANCIALS_ALIAS = {
    "total_market_without_financials": "total_market_ex_financials",
}


def slugify_industry(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name.lower()).strip("_")
    return TOTAL_MARKET_EX_FINANCIALS_ALIAS.get(slug, slug)


def _cell_text(value: Any) -> str:
    return str(value).strip()


def _find_header_row(sheet: xlrd.sheet.Sheet) -> int:
    for row_idx in range(sheet.nrows):
        values = [
            _cell_text(sheet.cell_value(row_idx, col_idx))
            for col_idx in range(sheet.ncols)
        ]
        if (
            "Industry Name" in values
            and "Number of firms" in values
            and "EV/EBITDA" in values
        ):
            return row_idx
    raise RuntimeError("Could not find Damodaran industry-average header row")


def _column_index(headers: list[str], header: str, *, occurrence: int = 1) -> int:
    matches = [idx for idx, value in enumerate(headers) if value == header]
    if len(matches) < occurrence:
        raise RuntimeError(f"Could not find header {header!r} occurrence {occurrence}")
    return matches[occurrence - 1]


def _positive_number(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip()
        if not value or value.upper() in {"NA", "N/A", "NM"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _firm_count(value: Any) -> int:
    try:
        firms = int(float(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid firm count {value!r}") from exc
    if firms < 0:
        raise RuntimeError(f"Invalid negative firm count {firms}")
    return firms


def parse_multiples(workbook_bytes: bytes, *, as_of: str) -> dict[str, Any]:
    workbook = xlrd.open_workbook(file_contents=workbook_bytes)
    sheet = workbook.sheet_by_name(SHEET_NAME)
    header_row = _find_header_row(sheet)
    headers = [
        _cell_text(sheet.cell_value(header_row, col_idx))
        for col_idx in range(sheet.ncols)
    ]
    industry_col = _column_index(headers, "Industry Name")
    firms_col = _column_index(headers, "Number of firms")
    ev_ebitda_col = _column_index(headers, "EV/EBITDA", occurrence=1)

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row_idx in range(header_row + 1, sheet.nrows):
        source_industry = _cell_text(sheet.cell_value(row_idx, industry_col))
        if not source_industry:
            continue
        ev_ebitda = _positive_number(sheet.cell_value(row_idx, ev_ebitda_col))
        if ev_ebitda is None:
            continue
        industry_key = slugify_industry(source_industry)
        if industry_key in seen_keys:
            raise RuntimeError(f"Duplicate industry key {industry_key!r}")
        seen_keys.add(industry_key)
        rows.append(
            {
                "industry_key": industry_key,
                "source_industry": source_industry,
                "firms": _firm_count(sheet.cell_value(row_idx, firms_col)),
                "ev_ebitda": ev_ebitda,
            }
        )

    if len(rows) < 60:
        raise RuntimeError(f"Expected at least 60 positive EV/EBITDA rows, got {len(rows)}")
    if "total_market_ex_financials" not in seen_keys:
        raise RuntimeError("Missing total_market_ex_financials fallback row")

    return {
        "source": SOURCE,
        "source_url": SOURCE_URL,
        "as_of": as_of,
        "region": REGION,
        "metric": METRIC,
        "rows": rows,
    }


def download_workbook(url: str) -> bytes:
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def write_dataset(dataset: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Damodaran Europe EV/EBITDA industry multiples."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    dataset = parse_multiples(download_workbook(args.source_url), as_of=args.as_of)
    write_dataset(dataset, args.output)
    print(f"Wrote {len(dataset['rows'])} rows to {args.output}")


if __name__ == "__main__":
    main()
```

- [x] **Step 5: Document the dataset + regeneration command in the README**

In `README.md`, add a short subsection (place it near the "How it works" / valuation discussion; exact anchor is author's choice) with this text:

```markdown
### Industry valuation multiples data

`src/rejstrik/analysis/data/industry_multiples.json` vendors **Damodaran
Europe** industry EV/EBITDA multiples (source, source_url, as_of and region are
recorded in the file). NACE is used only as a mapping key into Damodaran's
industry taxonomy — no hand-tuned multiples. Regenerate (network, manual, never
in CI) with:

    pip install xlrd
    python scripts/import_damodaran_multiples.py --as-of YYYY-MM-DD
```

- [x] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (no new tests yet; dataset + script are inert until Task 4).

- [x] **Step 7: Commit**

```bash
git add src/rejstrik/analysis/data/industry_multiples.json scripts/import_damodaran_multiples.py README.md pyproject.toml
git commit -m "feat(analysis): vendor Damodaran Europe multiples + importer tooling"
```

---

## Task 4: Industry-multiples loader (G2)

**Files:**
- Create: `src/rejstrik/analysis/industry_multiples.py` (ported from reference `industry_multiples.py`)
- Test: `tests/analysis/test_industry_multiples.py`

**Interfaces:**
- Consumes: the committed JSON from Task 3.
- Produces:
  - `FALLBACK_INDUSTRY_KEY = "total_market_ex_financials"`.
  - `@dataclass(frozen=True) class IndustryMultiple` with `industry_key`, `source_industry`, `ev_ebitda: float`, `firms: int`, `source`, `source_url`, `as_of`, `region` (all `str` except the two typed).
  - `def get_industry_multiple(industry_key: str | None) -> IndustryMultiple` — unknown/blank keys fall back to `total_market_ex_financials`.

- [x] **Step 1: Write the failing test**

Create `tests/analysis/test_industry_multiples.py`:

```python
import pytest

from rejstrik.analysis.industry_multiples import (
    FALLBACK_INDUSTRY_KEY,
    IndustryMultiple,
    get_industry_multiple,
)


def test_known_key_returns_row_with_provenance():
    im = get_industry_multiple("machinery")
    assert isinstance(im, IndustryMultiple)
    assert im.industry_key == "machinery"
    assert im.source_industry == "Machinery"
    assert im.ev_ebitda == pytest.approx(14.980532406240457)
    assert im.firms == 210
    assert im.source_url.startswith("https://")
    assert im.as_of
    assert im.region == "Europe"


def test_unknown_key_falls_back_to_total_market():
    im = get_industry_multiple("does_not_exist")
    assert im.industry_key == FALLBACK_INDUSTRY_KEY


def test_blank_key_falls_back():
    assert get_industry_multiple(None).industry_key == FALLBACK_INDUSTRY_KEY
    assert get_industry_multiple("  ").industry_key == FALLBACK_INDUSTRY_KEY
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/analysis/test_industry_multiples.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rejstrik.analysis.industry_multiples'`.

- [x] **Step 3: Write the minimal implementation**

Create `src/rejstrik/analysis/industry_multiples.py` (ported verbatim from the reference, with the package-local `DATA_PATH`):

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "industry_multiples.json"
FALLBACK_INDUSTRY_KEY = "total_market_ex_financials"
INDUSTRY_KEY_ALIASES = {
    "photonics_optoelectronics": "electronics_general",
}


@dataclass(frozen=True)
class IndustryMultiple:
    industry_key: str
    source_industry: str
    ev_ebitda: float
    firms: int
    source: str
    source_url: str
    as_of: str
    region: str


@lru_cache(maxsize=1)
def load_industry_multiples() -> dict:
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_industry_multiple(industry_key: str | None) -> IndustryMultiple:
    data = load_industry_multiples()
    requested = (industry_key or "").strip() or FALLBACK_INDUSTRY_KEY
    requested = INDUSTRY_KEY_ALIASES.get(requested, requested)
    rows = {row["industry_key"]: row for row in data["rows"]}
    row = rows.get(requested) or rows[FALLBACK_INDUSTRY_KEY]
    return IndustryMultiple(
        industry_key=row["industry_key"],
        source_industry=row["source_industry"],
        ev_ebitda=float(row["ev_ebitda"]),
        firms=int(row["firms"]),
        source=data["source"],
        source_url=data["source_url"],
        as_of=data["as_of"],
        region=data["region"],
    )
```

- [x] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/analysis/test_industry_multiples.py -q`
Expected: PASS (3 passed).

- [x] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/industry_multiples.py tests/analysis/test_industry_multiples.py
git commit -m "feat(analysis): load vendored Damodaran industry multiples with fallback"
```

---

## Task 5: NACE division map + `industry_key_for_nace` (G2)

**Files:**
- Create: `src/rejstrik/analysis/industry.py`
- Test: `tests/analysis/test_industry.py`

**Interfaces:**
- Produces:
  - `FALLBACK_INDUSTRY_KEY` (re-exported from `industry_multiples`).
  - `NACE_DIVISION_MAP: dict[str, str]` — **ported verbatim** from the reference `business_classification.py` (2-digit division → Damodaran industry slug; divisions 64/65/66 → fallback).
  - `def industry_key_for_nace(nace_codes: list[str]) -> tuple[str, str]` — returns `(industry_key, human_reason)`; empty/unmatched → `(FALLBACK_INDUSTRY_KEY, <reason>)`.

- [x] **Step 1: Write the failing test**

Create `tests/analysis/test_industry.py`:

```python
from rejstrik.analysis.industry import (
    FALLBACK_INDUSTRY_KEY,
    NACE_DIVISION_MAP,
    industry_key_for_nace,
)


def test_map_is_ported_verbatim_spot_checks():
    assert NACE_DIVISION_MAP["28"] == "machinery"
    assert NACE_DIVISION_MAP["25"] == "machinery"
    assert NACE_DIVISION_MAP["27"] == "electrical_equipment"
    assert NACE_DIVISION_MAP["10"] == "food_processing"
    # financial divisions map to the fallback
    assert NACE_DIVISION_MAP["64"] == FALLBACK_INDUSTRY_KEY
    assert NACE_DIVISION_MAP["65"] == FALLBACK_INDUSTRY_KEY
    assert NACE_DIVISION_MAP["66"] == FALLBACK_INDUSTRY_KEY


def test_resolves_division_from_code():
    key, reason = industry_key_for_nace(["28150"])
    assert key == "machinery"
    assert "28" in reason


def test_manufacturing_prioritized_over_retail():
    # division 28 (manufacturing, priority 0) beats 47 (retail, priority 2)
    key, _ = industry_key_for_nace(["47110", "28150"])
    assert key == "machinery"


def test_no_codes_returns_fallback():
    key, reason = industry_key_for_nace([])
    assert key == FALLBACK_INDUSTRY_KEY
    assert reason


def test_unmapped_division_returns_fallback():
    key, _ = industry_key_for_nace(["99999"])
    assert key == FALLBACK_INDUSTRY_KEY
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/analysis/test_industry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rejstrik.analysis.industry'`.

- [x] **Step 3: Write the minimal implementation**

Create `src/rejstrik/analysis/industry.py`. `NACE_DIVISION_MAP` and `_division_priority` are ported verbatim from the reference `business_classification.py`; the division-selection logic mirrors the reference `_nace_classification` (minus the out-of-scope keyword layer):

```python
from __future__ import annotations

from collections import Counter

from rejstrik.analysis.industry_multiples import FALLBACK_INDUSTRY_KEY

# Ported verbatim from ~/projects/obchodni-rejstrik-ai
# apps/api/services/business_classification.py (NACE_DIVISION_MAP).
NACE_DIVISION_MAP = {
    "01": "farming_agriculture",
    "02": "paper_forest_products",
    "03": "farming_agriculture",
    "05": "coal_related_energy",
    "06": "oil_gas_production_and_exploration",
    "07": "metals_mining",
    "08": "construction_supplies",
    "09": "oilfield_svcs_equip",
    "10": "food_processing",
    "11": "beverage_alcoholic",
    "12": "tobacco",
    "13": "apparel",
    "14": "apparel",
    "15": "shoe",
    "16": "furn_home_furnishings",
    "17": "paper_forest_products",
    "18": "publishing_newspapers",
    "19": "oil_gas_distribution",
    "20": "chemical_diversified",
    "21": "drugs_pharmaceutical",
    "22": "rubber_tires",
    "23": "building_materials",
    "24": "steel",
    "25": "machinery",
    "26": "electronics_general",
    "27": "electrical_equipment",
    "28": "machinery",
    "29": "auto_truck",
    "30": "shipbuilding_marine",
    "31": "furn_home_furnishings",
    "32": "healthcare_products",
    "33": "machinery",
    "35": "power",
    "36": "utility_water",
    "37": "environmental_waste_services",
    "38": "environmental_waste_services",
    "39": "environmental_waste_services",
    "41": "homebuilding",
    "42": "engineering_construction",
    "43": "engineering_construction",
    "45": "retail_automotive",
    "46": "retail_distributors",
    "47": "retail_general",
    "49": "transportation",
    "50": "shipbuilding_marine",
    "51": "air_transport",
    "52": "transportation",
    "53": "transportation",
    "55": "hotel_gaming",
    "56": "restaurant_dining",
    "58": "publishing_newspapers",
    "59": "entertainment",
    "60": "broadcasting",
    "61": "telecom_services",
    "62": "software_system_application",
    "63": "information_services",
    "64": FALLBACK_INDUSTRY_KEY,
    "65": FALLBACK_INDUSTRY_KEY,
    "66": FALLBACK_INDUSTRY_KEY,
    "68": "real_estate_operations_services",
    "69": "business_consumer_services",
    "70": "business_consumer_services",
    "71": "engineering_construction",
    "72": "business_consumer_services",
    "73": "advertising",
    "74": "business_consumer_services",
    "75": "healthcare_support_services",
    "77": "business_consumer_services",
    "78": "business_consumer_services",
    "79": "recreation",
    "80": "business_consumer_services",
    "81": "environmental_waste_services",
    "82": "office_equipment_services",
    "85": "education",
    "86": "hospitals_healthcare_facilities",
    "87": "healthcare_support_services",
    "88": "healthcare_support_services",
    "90": "entertainment",
    "91": "recreation",
    "92": "hotel_gaming",
    "93": "recreation",
    "94": "business_consumer_services",
    "95": "business_consumer_services",
    "96": "business_consumer_services",
}


def _division_priority(division: str) -> int:
    value = int(division)
    if 10 <= value <= 33:
        return 0
    if 45 <= value <= 47:
        return 2
    return 1


def industry_key_for_nace(nace_codes: list[str]) -> tuple[str, str]:
    """Map a list of CZ-NACE codes to a Damodaran industry key and a human
    reason. Manufacturing divisions (10-33) win over retail (45-47) over the
    rest; ties break by frequency then first-seen order (ported selection
    logic). Empty or unmapped input returns the market fallback."""
    divisions: list[str] = []
    for code in nace_codes:
        digits = "".join(ch for ch in str(code) if ch.isdigit())
        if len(digits) >= 2 and digits[:2] in NACE_DIVISION_MAP:
            divisions.append(digits[:2])
    if not divisions:
        return (
            FALLBACK_INDUSTRY_KEY,
            "no mapped NACE division; using generic market fallback",
        )
    counts = Counter(divisions)
    first_seen = {division: divisions.index(division) for division in counts}
    selected = min(
        counts,
        key=lambda division: (
            _division_priority(division),
            -counts[division],
            first_seen[division],
        ),
    )
    target = NACE_DIVISION_MAP[selected]
    return target, f"NACE {int(selected)} → {target}"
```

- [x] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/analysis/test_industry.py -q`
Expected: PASS (5 passed).

- [x] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/industry.py tests/analysis/test_industry.py
git commit -m "feat(analysis): port NACE division map + industry_key resolver"
```

---

## Task 6: `Company.nace_codes` from ARES (G2)

**Files:**
- Modify: `src/rejstrik/registry/models.py`
- Modify: `src/rejstrik/registry/ares.py`
- Test: `tests/registry/test_ares.py`, `tests/registry/test_models.py`

**Interfaces:**
- Produces: `Company.nace_codes: list[str]` populated from the ARES detail record's top-level `czNace` array (verified present in `tests/fixtures/ares/detail_00006947.json`).

- [x] **Step 1: Write the failing test**

Append to `tests/registry/test_ares.py`:

```python
def test_parse_detail_extracts_nace_codes():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    company = parse_detail(payload)
    assert company.nace_codes == ["84110"]


def test_parse_detail_missing_nace_defaults_empty():
    company = parse_detail({"ico": "12345678", "obchodniJmeno": "X"})
    assert company.nace_codes == []
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/registry/test_ares.py -q`
Expected: FAIL with `AttributeError: 'Company' object has no attribute 'nace_codes'`.

- [x] **Step 3: Add the field to the model**

In `src/rejstrik/registry/models.py`, add `nace_codes` to the `Company` model (after `founded`):

```python
class Company(BaseModel):
    ico: str
    name: str
    address: str | None = None
    legal_form: str | None = None
    legal_form_name: str | None = None
    founded: str | None = None
    nace_codes: list[str] = []
```

- [x] **Step 4: Populate it in `parse_detail`**

In `src/rejstrik/registry/ares.py`, in `parse_detail`, add the field to the returned `Company(...)`:

```python
def parse_detail(payload: dict) -> Company:
    sidlo = payload.get("sidlo") or {}
    legal_form = payload.get("pravniForma")
    return Company(
        ico=str(payload["ico"]),
        name=payload.get("obchodniJmeno") or "",
        address=sidlo.get("textovaAdresa"),
        legal_form=legal_form,
        legal_form_name=legal_form_name(legal_form),
        founded=payload.get("datumVzniku"),
        nace_codes=[str(code) for code in (payload.get("czNace") or [])],
    )
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/registry/test_ares.py -q`
Expected: PASS.

- [x] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green. (Existing `test_models.py` still passes; the new field has a default so no fixture breaks.)

- [x] **Step 7: Commit**

```bash
git add src/rejstrik/registry/models.py src/rejstrik/registry/ares.py tests/registry/test_ares.py
git commit -m "feat(registry): surface CZ-NACE codes on Company"
```

---

## Task 7: `depreciation_amortization` canonical line (G2)

**Files:**
- Modify: `src/rejstrik/documents/schema.py`
- Modify: `src/rejstrik/analysis/normalize.py`
- Test: `tests/documents/test_schema.py`, `tests/analysis/test_normalize.py`

**Interfaces:**
- Produces:
  - `CanonicalFigures.depreciation_amortization: Figure | None` (description names the Czech line "Úpravy hodnot v provozní oblasti").
  - `NormalizedFinancials.depreciation_amortization: float | None`, populated by `normalize()` from the canonical field or a keyword match.

- [x] **Step 1: Write the failing test**

Append to `tests/analysis/test_normalize.py`:

```python
def test_normalize_extracts_depreciation_amortization_from_canonical():
    from rejstrik.documents.schema import (
        CanonicalFigures,
        Figure,
        FinancialStatement,
    )
    from rejstrik.analysis.normalize import normalize

    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            depreciation_amortization=Figure(
                label="Úpravy hodnot v provozní oblasti", value=42.0
            )
        ),
    )
    assert normalize(stmt).depreciation_amortization == 42.0


def test_normalize_extracts_depreciation_from_income_statement_label():
    from rejstrik.documents.schema import Figure, FinancialStatement
    from rejstrik.analysis.normalize import normalize

    stmt = FinancialStatement(
        period_year=2023,
        income_statement=[
            Figure(label="Úpravy hodnot v provozní oblasti", value=17.0)
        ],
    )
    assert normalize(stmt).depreciation_amortization == 17.0
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: FAIL (`AttributeError`/validation: `depreciation_amortization` not on `NormalizedFinancials`/`CanonicalFigures`).

- [x] **Step 3: Add the canonical field**

In `src/rejstrik/documents/schema.py`, add to `CanonicalFigures` (after `operating_cash_flow`):

```python
    operating_cash_flow: Figure | None = Field(
        default=None,
        description="Peněžní tok z provozní činnosti (operating cash flow)",
    )
    depreciation_amortization: Figure | None = Field(
        default=None,
        description="Úpravy hodnot v provozní oblasti (depreciation & amortization)",
    )
```

- [x] **Step 4: Add the normalize rule, field list entry, and model field**

In `src/rejstrik/analysis/normalize.py`:

Add to `_FIELD_RULES` (after the `operating_cash_flow` rule):

```python
    "operating_cash_flow": {
        "any": (
            "penezni tok z provozni",
            "cash flow from operat",
        )
    },
    "depreciation_amortization": {
        "any": (
            "upravy hodnot v provozni oblasti",
            "odpisy",
            "depreciation",
            "amortization",
        )
    },
```

Add `"depreciation_amortization"` to the `_FIELDS` tuple (after `"operating_cash_flow"`):

```python
    "operating_cash_flow",
    "depreciation_amortization",
)
```

Add the field to `NormalizedFinancials` (after `operating_cash_flow`):

```python
    operating_cash_flow: float | None = None
    depreciation_amortization: float | None = None
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: PASS.

- [x] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 7: Commit**

```bash
git add src/rejstrik/documents/schema.py src/rejstrik/analysis/normalize.py tests/analysis/test_normalize.py
git commit -m "feat(analysis): capture depreciation/amortization for EBITDA"
```

---

## Task 8: Industry EV/EBITDA in `estimate_valuation` (G2)

**Files:**
- Modify: `src/rejstrik/analysis/valuation.py`
- Test: `tests/analysis/test_valuation.py`

**Interfaces:**
- Consumes: `get_industry_multiple` (Task 4), `NormalizedFinancials.depreciation_amortization` (Task 7).
- Produces:
  - `ValuationEstimate` gains `ebitda: float | None = None`, `ev_ebitda_multiple: float | None = None`, `industry_multiple_applied: str | None = None`.
  - `estimate_valuation(statements, assumptions=None, industry_key=None, industry_reason=None)`:
    - When `industry_key` is falsy → **unchanged behavior** (all three new fields `None`, caveats == default `_CAVEATS`, existing field values identical).
    - When `industry_key` is set AND latest `operating_profit` and `depreciation_amortization` are both present → compute `ebitda = operating_profit + D&A`, `ev_ebitda_multiple = im.ev_ebitda * ebitda`, include it in the value range, set `industry_multiple_applied = im.industry_key`, and append a provenance caveat (industry, firms, as_of, source URL) while dropping the "generic defaults" caveat.
    - When `industry_key` is set but D&A (or EBIT) is missing → do NOT apply an EBITDA multiple; keep the generic EBIT multiple and append a caveat explaining the fallback.

- [x] **Step 1: Write the failing test**

Append to `tests/analysis/test_valuation.py` (extend the `_stmt` helper to accept D&A, and add the new tests):

```python
def _stmt_da(year, *, equity=None, ebit=None, revenue=None, net_profit=None, da=None):
    return FinancialStatement(
        period_year=year,
        canonical=CanonicalFigures(
            equity=None
            if equity is None
            else Figure(label="Vlastní kapitál", value=equity),
            operating_profit=None
            if ebit is None
            else Figure(label="Provozní VH", value=ebit),
            revenue=None if revenue is None else Figure(label="Tržby", value=revenue),
            net_profit=None
            if net_profit is None
            else Figure(label="VH za účetní období", value=net_profit),
            depreciation_amortization=None
            if da is None
            else Figure(label="Úpravy hodnot v provozní oblasti", value=da),
        ),
    )


def test_statements_only_output_unchanged_by_industry_feature():
    result = estimate_valuation([_stmt_da(2023, equity=800.0, ebit=100.0)])
    assert result.ev_ebitda_multiple is None
    assert result.ebitda is None
    assert result.industry_multiple_applied is None
    assert result.caveats == [
        "Figures are in thousands of CZK as filed.",
        "Book values are not market values.",
        "Multiples are generic defaults, not industry-calibrated.",
        "Minority and marketability discounts are not applied.",
        "This is an indicative estimate, not investment advice.",
    ]


def test_industry_key_applies_ev_ebitda_when_da_present():
    from rejstrik.analysis.industry_multiples import get_industry_multiple

    result = estimate_valuation(
        [_stmt_da(2023, ebit=100.0, da=50.0)],
        industry_key="total_market_ex_financials",
        industry_reason="NACE 10 → food_processing",
    )
    im = get_industry_multiple("total_market_ex_financials")
    assert result.ebitda == 150.0
    assert result.ev_ebitda_multiple == pytest.approx(im.ev_ebitda * 150.0)
    assert result.industry_multiple_applied == "total_market_ex_financials"
    assert result.value_high == pytest.approx(im.ev_ebitda * 150.0)
    provenance = " ".join(result.caveats)
    assert "NACE 10" in provenance
    assert im.source_url in provenance
    assert str(im.firms) in provenance
    assert "generic defaults" not in provenance


def test_industry_key_without_da_does_not_apply_ebitda_multiple():
    result = estimate_valuation(
        [_stmt_da(2023, ebit=100.0)],  # no D&A
        industry_key="machinery",
    )
    assert result.ev_ebitda_multiple is None
    assert result.ev_ebit_multiple == 500.0  # generic EBIT multiple retained
    assert any("EBITDA multiple not applied" in c for c in result.caveats)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/analysis/test_valuation.py -q`
Expected: FAIL (`TypeError: estimate_valuation() got an unexpected keyword argument 'industry_key'` / missing fields).

- [x] **Step 3: Write the implementation**

Rewrite `src/rejstrik/analysis/valuation.py` as follows (adds imports, three model fields, and the industry branch; existing logic unchanged):

```python
from statistics import fmean, pstdev

from pydantic import BaseModel, Field

from rejstrik.analysis.industry_multiples import get_industry_multiple
from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Multiples are generic defaults, not industry-calibrated.",
    "Minority and marketability discounts are not applied.",
    "This is an indicative estimate, not investment advice.",
]
_GENERIC_MULTIPLES_CAVEAT = "Multiples are generic defaults, not industry-calibrated."


class ValuationAssumptions(BaseModel):
    capitalization_rate: float = 0.12
    ebit_multiple: float = 5.0
    revenue_multiple: float = 0.5
    dispersion_threshold: float = 0.5


class ValuationEstimate(BaseModel):
    book_value: float | None = None
    capitalized_earnings: float | None = None
    ev_ebit_multiple: float | None = None
    price_revenue_multiple: float | None = None
    ebitda: float | None = None
    ev_ebitda_multiple: float | None = None
    industry_multiple_applied: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    earnings_dispersion_flag: bool = False
    assumptions: ValuationAssumptions
    caveats: list[str] = Field(default_factory=lambda: list(_CAVEATS))


def _mul(factor: float, value: float | None) -> float | None:
    if value is None:
        return None
    return factor * value


def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    industry_reason: str | None = None,
) -> ValuationEstimate:
    assumptions = assumptions or ValuationAssumptions()
    if not statements:
        raise ValueError(
            "statements must contain at least one FinancialStatement "
            "(extract it from the PDF returned by get_filing)"
        )
    normalized = [normalize(s) for s in statements]
    ordered = sorted(
        normalized, key=lambda n: (n.period_year is None, -(n.period_year or 0))
    )
    latest = ordered[0]

    book_value = latest.equity
    ev = _mul(assumptions.ebit_multiple, latest.operating_profit)
    price = _mul(assumptions.revenue_multiple, latest.revenue)

    earnings = [n.net_profit for n in normalized if n.net_profit is not None]
    capitalized = None
    dispersion_flag = False
    if earnings and assumptions.capitalization_rate != 0:
        mean = fmean(earnings)
        capitalized = mean / assumptions.capitalization_rate
        if len(earnings) > 1 and mean != 0:
            cv = pstdev(earnings) / abs(mean)
            dispersion_flag = cv > assumptions.dispersion_threshold

    caveats = list(_CAVEATS)
    ebitda: float | None = None
    ev_ebitda: float | None = None
    industry_applied: str | None = None
    if industry_key:
        im = get_industry_multiple(industry_key)
        reason = industry_reason or f"industry_key '{industry_key}'"
        if latest.operating_profit is not None and latest.depreciation_amortization is not None:
            ebitda = latest.operating_profit + latest.depreciation_amortization
            ev_ebitda = im.ev_ebitda * ebitda
            industry_applied = im.industry_key
            caveats = [c for c in caveats if c != _GENERIC_MULTIPLES_CAVEAT]
            caveats.insert(
                2,
                f"Industry EV/EBITDA {im.ev_ebitda:.1f}x applied to EBITDA {ebitda:.0f} "
                f"(chosen: {reason}); Damodaran industry '{im.source_industry}', "
                f"{im.firms} firms, as of {im.as_of}. Source: {im.source_url}",
            )
        else:
            caveats.insert(
                2,
                f"EBITDA multiple not applied for '{im.source_industry}': operating "
                f"profit and/or depreciation & amortization missing. Kept the generic "
                f"EV/EBIT multiple instead.",
            )

    methods = [
        v
        for v in (book_value, capitalized, ev, price, ev_ebitda)
        if v is not None
    ]
    value_low = min(methods) if methods else None
    value_high = max(methods) if methods else None

    return ValuationEstimate(
        book_value=book_value,
        capitalized_earnings=capitalized,
        ev_ebit_multiple=ev,
        price_revenue_multiple=price,
        ebitda=ebitda,
        ev_ebitda_multiple=ev_ebitda,
        industry_multiple_applied=industry_applied,
        value_low=value_low,
        value_high=value_high,
        earnings_dispersion_flag=dispersion_flag,
        assumptions=assumptions,
        caveats=caveats,
    )
```

- [x] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/analysis/test_valuation.py -q`
Expected: PASS (all, including the pre-existing tests).

- [x] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/valuation.py tests/analysis/test_valuation.py
git commit -m "feat(analysis): apply Damodaran EV/EBITDA multiple with provenance"
```

---

## Task 9: Wire `ico`/`industry_key` into the `estimate_valuation` MCP tool (G2)

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_valuation_tool.py`

**Interfaces:**
- Consumes: `industry_key_for_nace` (Task 5), `Company.nace_codes` (Task 6), the extended `_estimate_valuation` (Task 8), existing `_find_company`.
- Produces: MCP tool `estimate_valuation(statements, assumptions=None, industry_key=None, ico=None)` enforcing precedence: explicit `assumptions` > explicit `industry_key` > NACE-derived (via `ico`) > generic defaults.

- [x] **Step 1: Write the failing test**

Append to `tests/mcp/test_valuation_tool.py`:

```python
def test_industry_key_flows_through_tool():
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation([stmt], industry_key="machinery")
    assert result.industry_multiple_applied == "machinery"


def test_ico_resolves_nace_to_industry(monkeypatch):
    from rejstrik.registry.models import Company

    monkeypatch.setattr(
        server,
        "_find_company",
        lambda q: Company(ico="00000001", name="X", nace_codes=["28150"]),
    )
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation([stmt], ico="00000001")
    assert result.industry_multiple_applied == "machinery"
    assert any("NACE 28" in c for c in result.caveats)


def test_explicit_assumptions_take_precedence_over_industry():
    from rejstrik.analysis.valuation import ValuationAssumptions

    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            operating_profit=Figure(label="Provozní VH", value=100.0),
            depreciation_amortization=Figure(label="Úpravy hodnot", value=50.0),
        ),
    )
    result = server.estimate_valuation(
        [stmt],
        assumptions=ValuationAssumptions(ebit_multiple=6.0),
        industry_key="machinery",
    )
    assert result.industry_multiple_applied is None
    assert result.ev_ebit_multiple == 600.0
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/mcp/test_valuation_tool.py -q`
Expected: FAIL (`TypeError: estimate_valuation() got an unexpected keyword argument 'industry_key'`).

- [x] **Step 3: Add the resolver import to `server.py`**

Immediately after the existing `from rejstrik.analysis.valuation import (...)` block, add:

```python
from rejstrik.analysis.industry import industry_key_for_nace
```

- [x] **Step 4: Rewrite the tool**

In `src/rejstrik/mcp/server.py`, replace the `estimate_valuation` tool function with:

```python
@mcp.tool(annotations=_ro("Estimate indicative valuation"))
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    ico: str | None = None,
) -> ValuationEstimate:
    """Indicative, deterministic valuation from statements YOU extracted: book
    value, capitalized earnings, generic EV/EBIT and price/revenue multiples,
    and — when an industry is known — a Damodaran Europe EV/EBITDA multiple
    (EBITDA = operating profit + depreciation/amortization). Provide `ico` to let
    the server map the company's CZ-NACE to a Damodaran industry, or pass
    `industry_key` directly (you know the business better than a registry code).
    Precedence: explicit `assumptions` > `industry_key` > NACE-derived > generic
    defaults. Amounts are thousands of CZK as filed; book values are not market
    values. NOT investment advice."""
    resolved_key: str | None = None
    reason: str | None = None
    if assumptions is None:
        if industry_key:
            resolved_key = industry_key
            reason = f"industry_key '{industry_key}' given by caller"
        elif ico:
            company = _find_company(ico)
            resolved_key, reason = industry_key_for_nace(company.nace_codes)
    return _estimate_valuation(
        statements,
        assumptions,
        industry_key=resolved_key,
        industry_reason=reason,
    )
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/mcp/test_valuation_tool.py -q`
Expected: PASS.

- [x] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [x] **Step 7: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_valuation_tool.py
git commit -m "feat(mcp): resolve NACE/industry_key for estimate_valuation"
```

---

## Task 10: Short-TTL cache for `list_filings` (G3)

**Files:**
- Modify: `src/rejstrik/filings/justice.py`
- Test: `tests/filings/test_filings_cache.py`

**Interfaces:**
- Produces:
  - `list_filings(ico, client=None, *, clock=time.monotonic)` — in-process TTL cache keyed by 8-padded IČO. TTL from `REJSTRIK_FILINGS_TTL_SECONDS` (default `900`, `0` disables). Only successful results are cached; returns a shallow copy.
  - `clear_filings_cache() -> None` — test helper to reset the cache.

- [x] **Step 1: Write the failing test**

Create `tests/filings/test_filings_cache.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.filings.justice import clear_filings_cache, list_filings

FIXTURES = Path(__file__).parent.parent / "fixtures" / "justice"
SEARCH_HTML = (FIXTURES / "legacy_search_00514152.html").read_text(encoding="utf-8")
DEEDS_HTML = (FIXTURES / "legacy_deeds_00514152.html").read_text(encoding="utf-8")

_NEW_FILINGS_URL = (
    "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152"
)

_API_JSON = {
    "status": "OK",
    "vysledekdetail": {
        "prehledlistin": [
            {
                "typlistiny": "účetní závěrka [2024]",
                "detail": [
                    {"obsah": {"digitalnipodoba": {"documentid": "1"}}}
                ],
            }
        ]
    },
}


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_filings_cache()
    yield
    clear_filings_cache()


@respx.mock
def test_second_call_within_ttl_hits_network_once(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "900")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    now = [1000.0]
    clock = lambda: now[0]  # noqa: E731

    first = list_filings("00514152", clock=clock)
    now[0] += 60.0  # still within TTL
    second = list_filings("00514152", clock=clock)

    assert route.call_count == 1
    assert [f.title for f in first] == [f.title for f in second]


@respx.mock
def test_call_after_ttl_expiry_refetches(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "900")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    now = [1000.0]
    clock = lambda: now[0]  # noqa: E731

    list_filings("00514152", clock=clock)
    now[0] += 901.0  # past TTL
    list_filings("00514152", clock=clock)

    assert route.call_count == 2


@respx.mock
def test_ttl_zero_disables_cache(monkeypatch):
    monkeypatch.setenv("REJSTRIK_FILINGS_TTL_SECONDS", "0")
    route = respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(200, json=_API_JSON)
    )
    list_filings("00514152")
    list_filings("00514152")
    assert route.call_count == 2
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/filings/test_filings_cache.py -q`
Expected: FAIL with `ImportError: cannot import name 'clear_filings_cache'`.

- [x] **Step 3: Implement the cache**

In `src/rejstrik/filings/justice.py`:

Add imports at the top (with the existing stdlib imports):

```python
import os
import time
from collections.abc import Callable
```

After the module-level URL constants (e.g. below `_YEAR_RE`), add the cache state and helpers:

```python
_FILINGS_CACHE: dict[str, tuple[float, list[Filing]]] = {}


def _filings_ttl_seconds() -> float:
    try:
        return float(os.environ.get("REJSTRIK_FILINGS_TTL_SECONDS", "900"))
    except ValueError:
        return 900.0


def clear_filings_cache() -> None:
    """Reset the in-process list_filings TTL cache (test/ops helper)."""
    _FILINGS_CACHE.clear()
```

Rewrite `list_filings` to consult the cache. Replace the current signature and body:

```python
def list_filings(
    ico: str,
    client: httpx.Client | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Results are cached in-process per 8-padded IČO for
    REJSTRIK_FILINGS_TTL_SECONDS (default 900; 0 disables) so a multi-year
    analysis does not re-hit the registry once per tool call. In-memory only —
    the stdio server is single-process and per-worker HTTP state is acceptable.

    Tries the new verejnerejstriky.msp.gov.cz JSON API first (numeric IČO
    without leading zeroes). On a block-shaped failure — HTTP 403, 429, any
    5xx, or a 2xx body that is not JSON (an Azure Front Door challenge page) —
    falls back to the legacy or.justice.cz HTML portal (IČO with leading
    zeroes). Non-block failures (404, timeouts, transport errors) from the new
    API propagate unchanged — they aren't evidence of a block.
    """
    ico_padded = ico.strip().zfill(8)
    ico_stripped = ico_padded.lstrip("0") or "0"
    ttl = _filings_ttl_seconds()
    if ttl > 0:
        cached = _FILINGS_CACHE.get(ico_padded)
        if cached is not None and clock() - cached[0] < ttl:
            return list(cached[1])

    own_client = client is None
    if own_client:
        client = make_client()

    try:
        try:
            result = _fetch_new_filings(ico_stripped, client)
        except _BlockShaped as block:
            try:
                legacy_filings = _fetch_legacy_filings(ico_padded, client)
            except httpx.HTTPError:
                legacy_filings = None
            if legacy_filings is None:
                raise RegistryBlockedError(
                    f"Sbírka listin unreachable for IČO {ico_padded}: "
                    f"new portal (verejnerejstriky.msp.gov.cz) returned "
                    f"{block.reason} and the legacy portal (or.justice.cz) has "
                    f"no matching subject. The registry may be blocking "
                    f"automated access. Check manually: "
                    f"https://or.justice.cz/ias/ui/rejstrik-$firma?ico={ico_padded}"
                ) from block
            result = legacy_filings
    finally:
        if own_client:
            client.close()

    if ttl > 0:
        _FILINGS_CACHE[ico_padded] = (clock(), result)
    return list(result)
```

- [x] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/filings/test_filings_cache.py -q`
Expected: PASS (3 passed).

- [x] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green. (Existing `tests/filings/test_justice.py` cache-agnostic tests still pass because each uses a distinct IČO/fixture and respx per test; if any fail due to cross-test caching, add `clear_filings_cache()` in that file's autouse fixture — but the default 900s TTL keyed by IČO does not collide across the existing single-call tests.)

> **Verification note for the implementer:** run the *whole* `tests/filings/` package (`python -m pytest tests/filings -q`) to confirm no cross-test cache bleed. The existing tests each call `list_filings` once per IČO and assert on the returned list, so caching does not change their outcomes.

- [x] **Step 6: Commit**

```bash
git add src/rejstrik/filings/justice.py tests/filings/test_filings_cache.py
git commit -m "feat(filings): short-TTL in-process cache for list_filings"
```

---

## Task 11: Canary auto-files/updates a tracking issue (G4)

**Files:**
- Modify: `.github/workflows/canary.yml`

> **Scope:** Workflow-only change; no Python code and no pytest changes. Per the spec, verification is a YAML sanity parse plus the standard command (which stays green since no source changed).

- [x] **Step 1: Rewrite the workflow to add issues:write and an on-failure github-script step**

Replace the entire contents of `.github/workflows/canary.yml` with:

```yaml
name: filings-portal-canary

on:
  schedule:
    - cron: "0 6 * * 1"
  workflow_dispatch:

permissions:
  contents: read
  issues: write

jobs:
  canary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e .
      - name: Run canary
        run: |
          python -c "
          from scripts.smoke import canary, _CANARY_ENDPOINTS
          import httpx
          canary()
          failures = []
          for name, url in _CANARY_ENDPOINTS.items():
              try:
                  resp = httpx.get(url, timeout=10.0, follow_redirects=True)
                  if resp.status_code >= 400:
                      failures.append(name)
              except httpx.HTTPError:
                  failures.append(name)
          if len(failures) == len(_CANARY_ENDPOINTS):
              raise SystemExit(f'Both filings portals are blocked: {failures}')
          "
      - name: Open or update tracking issue on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const label = 'portal-canary';
            const title = 'Filings portal canary failing';
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            const body = `The scheduled filings-portal canary failed on ${new Date().toISOString()}.\n\nBoth Sbírka listin portals may be blocking automated access. See the run: ${runUrl}`;
            const existing = await github.rest.issues.listForRepo({
              owner: context.repo.owner,
              repo: context.repo.repo,
              state: 'open',
              labels: label,
            });
            if (existing.data.length > 0) {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: existing.data[0].number,
                body,
              });
            } else {
              await github.rest.issues.create({
                owner: context.repo.owner,
                repo: context.repo.repo,
                title,
                body,
                labels: [label],
              });
            }
```

- [x] **Step 2: YAML sanity parse**

Run: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/canary.yml').read_text()); print('yaml ok')"`
Expected: `yaml ok`. (If PyYAML is not installed: `pip install pyyaml` first — this is a local check only, not a project dependency.)

- [x] **Step 3: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (unchanged Python).

- [x] **Step 4: Commit**

```bash
git add .github/workflows/canary.yml
git commit -m "ci(canary): open or update a tracking issue on failure"
```

---

## Task 12: Release gate — bump version to 0.7.0 (do last, only when cutting v0.7.0)

**Files:**
- Modify: `pyproject.toml`, `src/rejstrik/__init__.py`, `server.json`, `mcpb/manifest.json`
- Guarded by: `tests/test_version_sync.py` (four-location guard from Stage F)

> Only run this task when actually cutting the v0.7.0 release. It is separated so the feature commits above can land and be reviewed without forcing a version bump.

> **TODO (human operator):** Tasks 1–11 (G1–G4) are implemented, tested, and committed on `stage/g`. This task is intentionally left undone — the executing agent was instructed not to bump versions, merge, push, or tag. Run this task manually (or ask an agent to) only when actually cutting the v0.7.0 release.

- [ ] **Step 1: Read the current version locations**

Run: `python -c "import json,tomllib,pathlib; r=pathlib.Path('.'); print('pyproject', tomllib.loads((r/'pyproject.toml').read_text())['project']['version']); print('init', __import__('rejstrik').__version__ if False else open('src/rejstrik/__init__.py').read().strip()); print('server', json.load(open('server.json'))['version']); print('manifest', json.load(open('mcpb/manifest.json'))['version'])"`
Expected: all four report `0.6.1`.

- [ ] **Step 2: Bump all four to 0.7.0**

- `pyproject.toml`: change `version = "0.6.1"` → `version = "0.7.0"`.
- `src/rejstrik/__init__.py`: change `__version__ = "0.6.1"` → `__version__ = "0.7.0"`.
- `server.json`: change `"version"` (top-level) and `packages[0].version` to `0.7.0`.
- `mcpb/manifest.json`: change `"version"` to `0.7.0`.

- [ ] **Step 3: Full verification (version guard is part of the suite)**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green — `tests/test_version_sync.py` (four locations) confirms agreement.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/rejstrik/__init__.py server.json mcpb/manifest.json
git commit -m "chore(release): bump version to 0.7.0"
```

---

## Deviations for product-owner sign-off

These are the only points where this plan departs from a literal reading of the spec. Nothing in `NACE_DIVISION_MAP` was changed — it is ported byte-for-byte from the reference.

1. **"Byte-identical" statements-only valuation output.** The spec (G2 and Stage G acceptance) says statements-only `estimate_valuation` output must be "byte-identical to v0.6.x." Adding the three new fields (`ebitda`, `ev_ebitda_multiple`, `industry_multiple_applied`) to the `ValuationEstimate` model necessarily adds three `null` keys to the serialized JSON, so the output is not *literally* byte-identical to v0.6.1. This plan interprets the requirement as **behavioral** identity: for statements-only calls, every pre-existing field's value and the full `caveats` list are unchanged, and the three new fields are `null`. `test_statements_only_output_unchanged_by_industry_feature` (Task 8) locks this in. If strict byte-identity of the JSON is required instead, the alternative is to omit `None` fields at serialization time — but that would also drop the existing `null` method fields and change v0.6.x output shape, which is worse. **Requesting sign-off on the behavioral interpretation.**

   > **Sign-off (2026-07-14, product owner):** Accepted. Behavioral identity is the correct reading — pre-existing fields and caveats unchanged, new fields additive and `null` by default. Literal byte-identity was never the intent; it would have made the new fields impossible to add without a breaking rename.

2. **EV/EBIT / EV/Sales not imported.** The spec says to import EV/EBIT and EV/Sales "if present in the same Damodaran Europe dataset (verify on implementation day)." The reference importer and the vendored `vebitdaEurope.xls`-derived dataset expose **only** EV/EBITDA (verified: dataset rows carry `ev_ebitda`, `firms`, `industry_key`, `source_industry` and nothing else). Accordingly, when D&A is missing the code falls back to the existing generic EV/EBIT multiple — exactly the spec's allowed fallback ("fall back to EV/EBIT if imported, or the existing generic EBIT multiple"). No EV/EBIT/EV/Sales columns are added. If a future Damodaran sheet gains those columns, extend the importer and loader then.

3. **Keyword classification layer dropped (as the spec directs).** The reference `business_classification.py` also carries `KEYWORD_RULES` / `KEYWORD_TARGET_KEYS` and a company-text pipeline. The spec's "Not in scope" section explicitly rejects porting that layer (rejstrik-mcp has no activity-text pipeline; the host-agent `industry_key` override covers the need). This plan ports only `NACE_DIVISION_MAP`, `FALLBACK_INDUSTRY_KEY`, `_division_priority`, and the division-selection logic. The loader's `INDUSTRY_KEY_ALIASES` (`photonics_optoelectronics → electronics_general`) is ported verbatim but is inert without the keyword layer; it is kept for parity and harmless.

---

## Self-Review

**Spec coverage (G1–G4):**
- G1 scanned-filing images → Tasks 1–2 (pypdfium2 rasterizer, `read_filing_page_images` tool, 5-page cap, PNG magic bytes, steering in `read_filing_text` note + `analyze-company` prompt). ✅
- G2 Damodaran NACE valuation → Tasks 3–9 (vendored dataset + importer, loader, `NACE_DIVISION_MAP` verbatim + resolver, `Company.nace_codes`, `depreciation_amortization`/EBITDA, valuation provenance, tool wiring with precedence). `find_company` surfaces NACE via the model change (Task 6). ✅
- G3 short-TTL `list_filings` cache → Task 10 (env-configurable TTL, `0` disables, injectable clock, unit-tested once/expiry/disabled). ✅
- G4 canary auto-issue → Task 11 (github-script, `portal-canary` label, create-or-comment, `issues: write`). ✅
- Release as v0.7.0 → Task 12 (four-location bump, guarded). ✅

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — every code step contains complete code. ✅

**Type consistency:** `render_page_images`/`PageImage` (Task 1) consumed unchanged in Task 2; `get_industry_multiple`/`IndustryMultiple` (Task 4) consumed in Tasks 5, 8; `industry_key_for_nace` signature `(list[str]) -> tuple[str, str]` consistent Tasks 5→9; `estimate_valuation(..., industry_key, industry_reason)` defined in Task 8, called with those exact kwargs in Task 9; `Company.nace_codes` defined Task 6, read Task 9; `depreciation_amortization` field name identical across schema/normalize/valuation (Tasks 7–8); `clear_filings_cache`/`list_filings(..., *, clock=)` consistent Task 10. ✅
