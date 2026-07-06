# Stage 1: Keyless Document Flow + stdio + Packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rejstrik-mcp usable with zero API keys: document tools hand PDFs to the calling agent, deterministic analysis tools compute reports from host-extracted data, stdio is the default transport, and the package installs via `uvx rejstrik-mcp`.

**Architecture:** New keyless path = `get_filing` (download PDF → cache dir → return path + embedded blob) + `analyze_financials` (pure Pydantic-in, report-out, reusing existing normalize/ratios/redflags/trends) + `render_card` (existing HTML card from passed-in data) + MCP prompts choreographing the loop. Existing keyed LLM tools stay but degrade gracefully without a key. Spec: `docs/superpowers/specs/2026-07-06-keyless-pivot-and-growth-design.md`.

**Tech Stack:** Python 3.11+, FastMCP (`mcp>=1.2`), pydantic v2, httpx, platformdirs (new), pytest + respx, hatchling.

## Global Constraints

- CI test suite stays offline and key-free (no network, no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`).
- All new tools return typed, explanatory errors — never raw stack traces of missing config.
- Follow existing code style: module-level functions, pydantic models, underscore-aliased imports in `server.py`, fixture-based tests.
- Run `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` before every commit; all must pass.
- Version bumps to `0.2.0` in this stage (Task 10).
- Windows dev machine: paths via `pathlib`, no POSIX-only assumptions.

---

### Task 1: Parameterized filing picker

**Files:**
- Modify: `src/rejstrik/documents/pick.py`
- Test: `tests/documents/test_pick.py`

**Interfaces:**
- Consumes: `Filing` from `rejstrik.filings.models` (fields: `title`, `year`, `pdf_url`, `is_financial_statement`).
- Produces: `pick_financial_filing(filings: list[Filing], year: int | None = None, filing_id: str | None = None) -> Filing | None`. `filing_id` matches when it equals `pdf_url` or is a substring of `pdf_url` (document ids are embedded in the portal URLs). `pick_latest_financial_filing` keeps working unchanged.

- [ ] **Step 1: Write failing tests** — append to `tests/documents/test_pick.py`:

```python
from rejstrik.documents.pick import pick_financial_filing


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}",
        year=year,
        pdf_url=f"https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_pick_financial_filing_default_latest():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings).year == 2024


def test_pick_financial_filing_by_year():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings, year=2023).pdf_url.endswith("bbb")


def test_pick_financial_filing_by_year_missing_returns_none():
    assert pick_financial_filing([_fin(2024, "aaa")], year=2019) is None


def test_pick_financial_filing_by_filing_id_substring():
    filings = [_fin(2024, "aaa"), _fin(2023, "bbb")]
    assert pick_financial_filing(filings, filing_id="bbb").year == 2023


def test_pick_financial_filing_by_filing_id_ignores_year_filter():
    non_fin = Filing(title="zprava", year=2022, pdf_url="https://x/ccc")
    assert pick_financial_filing([non_fin], filing_id="ccc") is non_fin
```

(`Filing` is already imported at the top of the test file; if not, add `from rejstrik.filings.models import Filing`.)

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/documents/test_pick.py -v`
Expected: FAIL — `ImportError: cannot import name 'pick_financial_filing'`

- [ ] **Step 3: Implement** — in `src/rejstrik/documents/pick.py`:

```python
def pick_financial_filing(
    filings: list[Filing],
    year: int | None = None,
    filing_id: str | None = None,
) -> Filing | None:
    """Pick a financial statement: latest by default, or by year / filing id.

    filing_id matches any filing (financial or not) whose pdf_url equals or
    contains it — document ids are embedded in the portal URLs.
    """
    if filing_id:
        for f in filings:
            if filing_id == f.pdf_url or filing_id in f.pdf_url:
                return f
        return None
    candidates = [f for f in filings if f.is_financial_statement]
    if year is not None:
        candidates = [f for f in candidates if f.year == year]
    return candidates[0] if candidates else None
```

Then rewrite `pick_latest_financial_filing` to delegate: `return pick_financial_filing(filings)`.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/documents/test_pick.py -v`
Expected: all PASS (old tests too — the list is pre-sorted financial-first, year-desc by `justice.py`, so first financial candidate is the latest).

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/documents/pick.py tests/documents/test_pick.py
git commit -m "feat: pick_financial_filing with year/filing_id selectors"
```

---

### Task 2: Filing PDF cache

**Files:**
- Create: `src/rejstrik/documents/cache.py`
- Test: `tests/documents/test_cache.py`
- Modify: `pyproject.toml` (add `platformdirs>=4` to `dependencies`)

**Interfaces:**
- Consumes: `PdfSource` from `rejstrik.documents.source` (fields: `data: bytes`, `sha256: str`, `filename: str`).
- Produces: `cache_dir() -> Path` (respects `REJSTRIK_CACHE_DIR` env override, else platformdirs user cache for app `rejstrik-mcp`; creates it). `save_filing_pdf(source: PdfSource, ico: str, year: int | None) -> Path` (writes `{ico}-{year|unknown}-{sha256[:8]}.pdf`, idempotent).

- [ ] **Step 1: Add dependency** — in `pyproject.toml` `dependencies`, add line `"platformdirs>=4",` after `"python-dotenv>=1.0",`. Run `pip install -e ".[dev]"`.

- [ ] **Step 2: Write failing tests** — create `tests/documents/test_cache.py`:

```python
from rejstrik.documents.cache import cache_dir, save_filing_pdf
from rejstrik.documents.source import PdfSource
import hashlib


def _source(data: bytes = b"%PDF-1.4 fake") -> PdfSource:
    return PdfSource(
        data=data, sha256=hashlib.sha256(data).hexdigest(), filename="filing.pdf"
    )


def test_cache_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path / "custom"))
    d = cache_dir()
    assert d == tmp_path / "custom"
    assert d.is_dir()


def test_save_filing_pdf_writes_named_file(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    src = _source()
    path = save_filing_pdf(src, "00514152", 2024)
    assert path.name == f"00514152-2024-{src.sha256[:8]}.pdf"
    assert path.read_bytes() == src.data


def test_save_filing_pdf_unknown_year_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    src = _source()
    first = save_filing_pdf(src, "00514152", None)
    second = save_filing_pdf(src, "00514152", None)
    assert first == second
    assert "unknown" in first.name
```

- [ ] **Step 3: Run tests, verify failure**

Run: `python -m pytest tests/documents/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.documents.cache'`

- [ ] **Step 4: Implement** — create `src/rejstrik/documents/cache.py`:

```python
import os
from pathlib import Path

from platformdirs import user_cache_dir

from rejstrik.documents.source import PdfSource


def cache_dir() -> Path:
    override = os.environ.get("REJSTRIK_CACHE_DIR")
    base = Path(override) if override else Path(user_cache_dir("rejstrik-mcp"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_filing_pdf(source: PdfSource, ico: str, year: int | None) -> Path:
    stem = f"{ico}-{year if year is not None else 'unknown'}-{source.sha256[:8]}.pdf"
    path = cache_dir() / stem
    if not path.exists():
        path.write_bytes(source.data)
    return path
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/documents/test_cache.py -v` — Expected: PASS

- [ ] **Step 6: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/documents/cache.py tests/documents/test_cache.py pyproject.toml
git commit -m "feat: filing PDF cache directory with env override"
```

---

### Task 3: Service `fetch_filing` + `FilingDocument`

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service_fetch.py` (new)

**Interfaces:**
- Consumes: `pick_financial_filing` (Task 1), `save_filing_pdf` (Task 2), existing `find_company`, `list_filings`, `load_pdf`, `NoStatementFound`.
- Produces: `class FilingDocument(BaseModel)` with fields `ico: str`, `company_name: str`, `title: str`, `year: int | None`, `pdf_url: str`, `file_path: str`, `sha256: str`, `size_bytes: int`. `fetch_filing(query: str, year: int | None = None, filing_id: str | None = None, client: httpx.Client | None = None) -> tuple[FilingDocument, PdfSource]`. Raises `NoStatementFound` listing available years when nothing matches.

- [ ] **Step 1: Write failing tests** — create `tests/test_service_fetch.py`:

```python
import hashlib

import pytest

from rejstrik import service
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company
from rejstrik.service import NoStatementFound, fetch_filing

_PDF = b"%PDF-1.4 fake"


def _wire(monkeypatch, tmp_path, filings):
    monkeypatch.setenv("REJSTRIK_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        service, "find_company", lambda q, client=None: Company(ico="00514152", name="Budvar")
    )
    monkeypatch.setattr(service, "list_filings", lambda ico, client=None: filings)
    monkeypatch.setattr(
        service,
        "load_pdf",
        lambda filing, client=None: PdfSource(
            data=_PDF, sha256=hashlib.sha256(_PDF).hexdigest(), filename="filing.pdf"
        ),
    )


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}",
        year=year,
        pdf_url=f"https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_fetch_filing_latest(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    doc, source = fetch_filing("Budvar")
    assert doc.year == 2024
    assert doc.ico == "00514152"
    assert doc.company_name == "Budvar"
    assert doc.size_bytes == len(_PDF)
    assert doc.file_path.endswith(".pdf")
    assert source.data == _PDF


def test_fetch_filing_by_year(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    doc, _ = fetch_filing("Budvar", year=2023)
    assert doc.year == 2023


def test_fetch_filing_missing_year_lists_available(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    with pytest.raises(NoStatementFound) as exc:
        fetch_filing("Budvar", year=2019)
    assert "2024" in str(exc.value) and "2023" in str(exc.value)


def test_fetch_filing_no_financials(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, [])
    with pytest.raises(NoStatementFound):
        fetch_filing("Budvar")
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/test_service_fetch.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_filing'`

- [ ] **Step 3: Implement** — in `src/rejstrik/service.py`, add imports (`from pydantic import BaseModel`, `from rejstrik.documents.cache import save_filing_pdf`, and extend the pick import to `from rejstrik.documents.pick import pick_financial_filing, pick_latest_financial_filing`), then add:

```python
class FilingDocument(BaseModel):
    ico: str
    company_name: str
    title: str
    year: int | None = None
    pdf_url: str
    file_path: str
    sha256: str
    size_bytes: int


def fetch_filing(
    query: str,
    year: int | None = None,
    filing_id: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[FilingDocument, PdfSource]:
    company = find_company(query, client=client)
    filings = list_filings(company.ico, client=client)
    filing = pick_financial_filing(filings, year=year, filing_id=filing_id)
    if filing is None:
        years = sorted(
            {f.year for f in filings if f.is_financial_statement and f.year},
            reverse=True,
        )
        hint = f" Available years: {years}." if years else " No financial statements filed."
        raise NoStatementFound(
            f"No matching financial statement in Sbírka listin for {company.ico}.{hint}"
        )
    source = load_pdf(filing, client=client)
    path = save_filing_pdf(source, company.ico, filing.year)
    return (
        FilingDocument(
            ico=company.ico,
            company_name=company.name,
            title=filing.title,
            year=filing.year,
            pdf_url=filing.pdf_url,
            file_path=str(path),
            sha256=source.sha256,
            size_bytes=len(source.data),
        ),
        source,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_service_fetch.py tests/test_service.py -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/service.py tests/test_service_fetch.py
git commit -m "feat: fetch_filing service returning cached PDF + metadata"
```

---

### Task 4: Deterministic `analyze_statements` service

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service_analyze_statements.py` (new)

**Interfaces:**
- Consumes: existing `normalize`, `compute_ratios`, `detect_red_flags`, `check_insolvency`, `check_vat`, `CompanyFinancialReport`; `compute_trends` from `rejstrik.analysis.trends` (new import).
- Produces: `analyze_statements(statements: list[FinancialStatement], *, ico: str | None = None, insolvency_check=None, vat_check=None) -> CompanyFinancialReport`. Zero LLM calls. Sorts statements newest-first by `period_year`; trends computed when 2+ statements; registry cross-checks only when an IČO is known (argument or `statements[0].ico`); raises `ValueError` on empty list.

- [ ] **Step 1: Write failing tests** — create `tests/test_service_analyze_statements.py`:

```python
import pytest

from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.vat import VatStatus
from rejstrik.service import analyze_statements


def _statement(year: int, revenue: float) -> FinancialStatement:
    return FinancialStatement(
        company_name="Budvar",
        ico="00514152",
        period_year=year,
        currency="CZK",
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def _no_insolvency(ico):
    return InsolvencyStatus(checked=True, in_insolvency=False)


def _clean_vat(ico):
    return VatStatus(is_vat_payer=True, dic="CZ00514152", is_unreliable=False)


def test_analyze_statements_single_year(monkeypatch):
    report = analyze_statements(
        [_statement(2024, 1000.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert report.period_year == 2024
    assert report.trends == []
    assert report.ico == "00514152"


def test_analyze_statements_two_years_computes_trends():
    report = analyze_statements(
        [_statement(2023, 800.0), _statement(2024, 1000.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert report.period_year == 2024
    revenue = next(t for t in report.trends if t.metric == "revenue")
    assert revenue.current == 1000.0
    assert revenue.prior == 800.0
    assert revenue.pct_change == pytest.approx(0.25)


def test_analyze_statements_without_ico_skips_registry_checks():
    stmt = _statement(2024, 1000.0)
    stmt.ico = None

    def boom(ico):
        raise AssertionError("registry check must not run without an ICO")

    report = analyze_statements([stmt], insolvency_check=boom, vat_check=boom)
    assert report.ico is None


def test_analyze_statements_empty_raises():
    with pytest.raises(ValueError):
        analyze_statements([])
```

Adjust `VatStatus`/`InsolvencyStatus` constructor kwargs to the real model fields (check `src/rejstrik/registry/vat.py` and `isir.py`) — the intent is "checked, not insolvent" and "registered, not unreliable".

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/test_service_analyze_statements.py -v`
Expected: FAIL — `ImportError: cannot import name 'analyze_statements'`

- [ ] **Step 3: Implement** — in `src/rejstrik/service.py`, add `from rejstrik.analysis.trends import compute_trends` and `from rejstrik.documents.schema import FinancialStatement`, then:

```python
def analyze_statements(
    statements: list[FinancialStatement],
    *,
    ico: str | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
) -> CompanyFinancialReport:
    """Deterministic report from host-extracted statements. No LLM calls."""
    if not statements:
        raise ValueError(
            "statements must contain at least one FinancialStatement "
            "(extract it from the PDF returned by get_filing)"
        )
    ordered = sorted(
        statements, key=lambda s: (s.period_year is None, -(s.period_year or 0))
    )
    current = ordered[0]
    normalized = normalize(current)
    ratios = compute_ratios(normalized)
    resolved_ico = ico or current.ico
    insolvent = None
    unreliable_vat = None
    if resolved_ico:
        insolvency_check = insolvency_check or check_insolvency
        vat_check = vat_check or check_vat
        status = insolvency_check(resolved_ico)
        insolvent = status.in_insolvency if status.checked else None
        unreliable_vat = vat_check(resolved_ico).is_unreliable
    red_flags = detect_red_flags(
        normalized,
        ratios,
        current.notes,
        insolvent=insolvent,
        unreliable_vat=unreliable_vat,
    )
    trends = (
        compute_trends(normalized, normalize(ordered[1])) if len(ordered) > 1 else []
    )
    return CompanyFinancialReport(
        company_name=current.company_name,
        ico=resolved_ico,
        period_year=current.period_year,
        currency=current.currency,
        statement=current,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        trends=trends,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_service_analyze_statements.py -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/service.py tests/test_service_analyze_statements.py
git commit -m "feat: deterministic analyze_statements with trends wiring"
```

---

### Task 5: MCP tool `get_filing`

**Files:**
- Modify: `src/rejstrik/mcp/server.py`, `tests/mcp/test_server.py`
- Test: `tests/mcp/test_get_filing.py` (new)

**Interfaces:**
- Consumes: `fetch_filing` (Task 3).
- Produces: MCP tool `get_filing(ico: str, year: int | None = None, filing_id: str | None = None)` returning `[TextContent(metadata JSON), EmbeddedResource(PDF blob)]`; blob omitted with an explanatory TextContent when `size_bytes` exceeds `REJSTRIK_MAX_EMBED_BYTES` (default 15,000,000).

- [ ] **Step 1: Write failing tests** — create `tests/mcp/test_get_filing.py`:

```python
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
        file_path="C:\\cache\\00514152-2024-abcd1234.pdf",
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/mcp/test_get_filing.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_fetch_filing'`

- [ ] **Step 3: Implement** — in `src/rejstrik/mcp/server.py`:

Add imports:

```python
import base64
import os
from pathlib import Path

from mcp.types import BlobResourceContents, EmbeddedResource, TextContent
```

Extend the service import to include `fetch_filing as _fetch_filing`. Add near the top:

```python
_MAX_EMBED_BYTES = int(os.environ.get("REJSTRIK_MAX_EMBED_BYTES", "15000000"))
```

Add the tool (note `structured_output=False` — the return value is raw MCP content, not a serializable model):

```python
@mcp.tool(structured_output=False)
def get_filing(
    ico: str, year: int | None = None, filing_id: str | None = None
) -> list[TextContent | EmbeddedResource]:
    """Download a financial statement PDF from Sbírka listin (latest, or by
    year / filing id from list_filings). Returns filing metadata with a local
    file_path, plus the PDF itself as an embedded resource. Read the PDF with
    your own capabilities, then pass extracted figures to analyze_financials —
    no server-side API key needed."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    parts: list[TextContent | EmbeddedResource] = [
        TextContent(type="text", text=doc.model_dump_json(indent=2))
    ]
    if doc.size_bytes <= _MAX_EMBED_BYTES:
        parts.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=Path(doc.file_path).as_uri(),
                    mimeType="application/pdf",
                    blob=base64.standard_b64encode(source.data).decode(),
                ),
            )
        )
    else:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — too large to embed. "
                    f"Read it from file_path: {doc.file_path}"
                ),
            )
        )
    return parts
```

Append `"get_filing"` to `EXPOSED_TOOL_NAMES` and to the expected list in `tests/mcp/test_server.py::test_exposed_tool_names`.

If `@mcp.tool(structured_output=False)` raises `TypeError` (older mcp package), upgrade: change `pyproject.toml` to `"mcp>=1.10"` and `pip install -e ".[dev]"`.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_get_filing.py tests/mcp/test_server.py pyproject.toml
git commit -m "feat: get_filing MCP tool returning PDF path + embedded blob"
```

---

### Task 6: MCP tools `analyze_financials` + `render_card`

**Files:**
- Modify: `src/rejstrik/mcp/server.py`, `tests/mcp/test_server.py`
- Test: `tests/mcp/test_keyless_analysis.py` (new)

**Interfaces:**
- Consumes: `analyze_statements` (Task 4), existing `render_report_card`, `create_ui_resource`.
- Produces: MCP tool `analyze_financials(statements: list[FinancialStatement], ico: str | None = None) -> CompanyFinancialReport`; MCP tool `render_card(report: CompanyFinancialReport) -> list[UIResource]`.

- [ ] **Step 1: Write failing tests** — create `tests/mcp/test_keyless_analysis.py`:

```python
import asyncio

from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.mcp import server


def _statement(year: int, revenue: float) -> FinancialStatement:
    return FinancialStatement(
        company_name="Budvar",
        period_year=year,
        currency="CZK",
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def test_analyze_financials_two_years():
    report = server.analyze_financials([_statement(2023, 800.0), _statement(2024, 1000.0)])
    assert isinstance(report, CompanyFinancialReport)
    assert report.period_year == 2024
    assert any(t.metric == "revenue" and t.pct_change for t in report.trends)


def test_render_card_returns_ui_resource():
    report = server.analyze_financials([_statement(2024, 1000.0)])
    resources = server.render_card(report)
    assert resources[0].resource.uri == "ui://rejstrik/report"
    assert "Budvar" in resources[0].resource.text


def test_new_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"analyze_financials", "render_card"} <= names
```

Note: statements in these tests have no `ico`, so `analyze_statements` skips registry HTTP calls — the test stays offline without mocking.

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/mcp/test_keyless_analysis.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'analyze_financials'`

- [ ] **Step 3: Implement** — in `src/rejstrik/mcp/server.py`, extend the service import with `analyze_statements as _analyze_statements`, add `from rejstrik.documents.schema import FinancialStatement`, then:

```python
@mcp.tool()
def analyze_financials(
    statements: list[FinancialStatement], ico: str | None = None
) -> CompanyFinancialReport:
    """Deterministic financial report from statements YOU extracted from the
    get_filing PDF(s): normalize → ratios → red flags → trends (with 2+ years).
    Amounts in Czech statements are usually thousands of CZK. Pass the ico to
    enrich red flags with insolvency and unreliable-VAT-payer checks."""
    return _analyze_statements(statements, ico=ico)


@mcp.tool()
def render_card(report: CompanyFinancialReport) -> list[UIResource]:
    """Render a CompanyFinancialReport (from analyze_financials) as an
    interactive HTML card for MCP UI hosts."""
    return [
        create_ui_resource(
            {
                "uri": "ui://rejstrik/report",
                "content": {
                    "type": "rawHtml",
                    "htmlString": render_report_card(report),
                },
                "encoding": "text",
            }
        )
    ]
```

Append `"analyze_financials"` and `"render_card"` to `EXPOSED_TOOL_NAMES` and the expected list in `tests/mcp/test_server.py`.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_keyless_analysis.py tests/mcp/test_server.py
git commit -m "feat: keyless analyze_financials and render_card MCP tools"
```

---

### Task 7: Graceful degradation of keyed tools

**Files:**
- Modify: `src/rejstrik/documents/config.py`, `src/rejstrik/mcp/server.py`
- Test: `tests/documents/test_config.py` (extend), `tests/mcp/test_keyed_degradation.py` (new)

**Interfaces:**
- Consumes: nothing new.
- Produces: `has_llm_key() -> bool` in `rejstrik.documents.config`; `MissingApiKey(Exception)` in `rejstrik.mcp.server`; the four keyed tools (`extract_financials`, `ask_filing`, `analyze_company_financials`, `analyze_company_card`) raise `MissingApiKey` with keyless guidance before doing any network work when no key is configured.

- [ ] **Step 1: Write failing tests** — append to `tests/documents/test_config.py`:

```python
from rejstrik.documents.config import has_llm_key


def test_has_llm_key_false_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert has_llm_key() is False


def test_has_llm_key_true_with_either(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert has_llm_key() is True
```

Create `tests/mcp/test_keyed_degradation.py`:

```python
import pytest

from rejstrik.mcp import server


@pytest.fixture()
def no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.mark.parametrize(
    "call",
    [
        lambda: server.extract_financials("00514152"),
        lambda: server.ask_filing("00514152", "what changed?"),
        lambda: server.analyze_company_financials("Budvar"),
        lambda: server.analyze_company_card("Budvar"),
    ],
)
def test_keyed_tools_raise_helpful_error_without_key(no_keys, call):
    with pytest.raises(server.MissingApiKey) as exc:
        call()
    message = str(exc.value)
    assert "get_filing" in message
    assert "analyze_financials" in message
```

(No network mocking needed: the key check must run before any HTTP call — that ordering is what the test proves.)

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/documents/test_config.py tests/mcp/test_keyed_degradation.py -v`
Expected: FAIL — `ImportError: cannot import name 'has_llm_key'`

- [ ] **Step 3: Implement** — in `src/rejstrik/documents/config.py`:

```python
def has_llm_key() -> bool:
    _load_local_env()
    return bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
```

In `src/rejstrik/mcp/server.py`, add `from rejstrik.documents.config import has_llm_key` and:

```python
class MissingApiKey(Exception):
    pass


_KEYLESS_HINT = (
    "This tool runs a model inside the server and needs ANTHROPIC_API_KEY or "
    "OPENAI_API_KEY set where rejstrik-mcp runs. Keyless alternative: call "
    "get_filing to fetch the statement PDF, read it yourself, then pass the "
    "extracted figures to analyze_financials (and render_card for the UI card)."
)


def _require_llm_key() -> None:
    if not has_llm_key():
        raise MissingApiKey(_KEYLESS_HINT)
```

Add `_require_llm_key()` as the first line of the four keyed tool bodies. Extend each keyed tool's docstring with the sentence: `Requires a server-side API key; without one, use get_filing + analyze_financials.`

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/documents/test_config.py tests/mcp/test_keyed_degradation.py -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/documents/config.py src/rejstrik/mcp/server.py tests/documents/test_config.py tests/mcp/test_keyed_degradation.py
git commit -m "feat: keyed tools degrade gracefully without an API key"
```

---

### Task 8: MCP prompts `analyze-company` + `company-health-check`

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_prompts.py` (new)

**Interfaces:**
- Consumes: `FinancialStatement.model_json_schema()`.
- Produces: MCP prompts `analyze-company(company: str, years: int = 1)` and `company-health-check(company: str)` returning recipe strings that reference the exact tool names.

- [ ] **Step 1: Write failing tests** — create `tests/mcp/test_prompts.py`:

```python
import asyncio

from rejstrik.mcp import server


def test_prompts_registered():
    prompts = asyncio.run(server.mcp.list_prompts())
    names = {p.name for p in prompts}
    assert {"analyze-company", "company-health-check"} <= names


def test_analyze_company_prompt_mentions_tools_and_schema():
    text = server.analyze_company_prompt("Budvar", years=3)
    for needle in (
        "find_company",
        "list_filings",
        "get_filing",
        "analyze_financials",
        "render_card",
        "thousands of CZK",
        "period_year",
        "Budvar",
        "3",
    ):
        assert needle in text


def test_health_check_prompt_mentions_breadth_tools():
    text = server.company_health_check_prompt("Budvar")
    for needle in ("check_insolvency", "check_vat", "get_statutory_bodies", "Budvar"):
        assert needle in text
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/mcp/test_prompts.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'analyze_company_prompt'`

- [ ] **Step 3: Implement** — in `src/rejstrik/mcp/server.py`, add `import json`, then:

```python
@mcp.prompt(name="analyze-company")
def analyze_company_prompt(company: str, years: int = 1) -> str:
    """Guide the host model through keyless company financial analysis."""
    schema = json.dumps(FinancialStatement.model_json_schema(), indent=2)
    return f"""Analyze the financials of the Czech company "{company}" over the
last {years} year(s), using only your own reading of the filed statements.

Follow these steps exactly:
1. Call find_company("{company}") to resolve the IČO.
2. Call list_filings(ico) and identify the financial statements for the
   {years} most recent year(s).
3. For each year, call get_filing(ico, year=...). Read the returned PDF
   (use the local file_path if you can read files, otherwise the embedded
   resource).
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema (amounts in Czech statements are usually reported in thousands of
   CZK — keep them as printed and set currency to "CZK"; set period_year to
   the statement year; cite source_page for every figure):
{schema}
5. Call analyze_financials(statements=[...], ico=ico) with ALL extracted
   statements in one call to get ratios, red flags, and year-over-year trends.
6. If your client renders MCP UI resources, also call render_card(report).
7. Summarize: overall health, notable trends, every red flag with its
   severity, and page citations for key numbers."""


@mcp.prompt(name="company-health-check")
def company_health_check_prompt(company: str) -> str:
    """Guide the host model through a full registry + financials health check."""
    return f"""Run a full health check on the Czech company "{company}".

1. Call find_company("{company}") to resolve the IČO.
2. In parallel where possible, call check_insolvency(ico), check_vat(ico),
   and get_statutory_bodies(ico).
3. Follow the analyze-company recipe for the latest financial year
   (list_filings → get_filing → extract figures → analyze_financials).
4. Report: registry status (insolvency, VAT reliability, who runs the
   company), financial health (ratios, red flags), and an overall verdict
   with the caveats an accountant would add."""
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp/test_prompts.py -v` — Expected: PASS

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_prompts.py
git commit -m "feat: analyze-company and company-health-check MCP prompts"
```

---

### Task 9: stdio default transport, `--http` flag

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_transport.py` (new)

**Interfaces:**
- Consumes: existing `mcp` FastMCP instance.
- Produces: `main(argv: list[str] | None = None)` — stdio by default; `--http [--port N]` runs streamable-http on the given port (default 8000).

- [ ] **Step 1: Write failing tests** — create `tests/mcp/test_transport.py`:

```python
from rejstrik.mcp import server


def test_main_defaults_to_stdio(monkeypatch):
    calls = {}
    monkeypatch.setattr(server.mcp, "run", lambda transport: calls.setdefault("t", transport))
    server.main([])
    assert calls["t"] == "stdio"


def test_main_http_flag(monkeypatch):
    calls = {}
    monkeypatch.setattr(server.mcp, "run", lambda transport: calls.setdefault("t", transport))
    server.main(["--http", "--port", "9000"])
    assert calls["t"] == "streamable-http"
    assert server.mcp.settings.port == 9000
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/mcp/test_transport.py -v`
Expected: FAIL — `TypeError: main() takes 0 positional arguments but 1 was given`

- [ ] **Step 3: Implement** — replace `main()` in `src/rejstrik/mcp/server.py` (add `import argparse`):

```python
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rejstrik-mcp")
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve streamable HTTP on /mcp instead of stdio",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp -v` — Expected: PASS

- [ ] **Step 5: Manual sanity check** — run `rejstrik-mcp --http` in a background shell, confirm it binds port 8000 and serves `/mcp`, then kill it. Then run `python -c "from rejstrik.mcp.server import main; print('import ok')"`.

- [ ] **Step 6: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_transport.py
git commit -m "feat: stdio default transport with --http fallback"
```

---

### Task 10: Packaging metadata + PyPI release workflow

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Produces: version `0.2.0`; PyPI-ready metadata; a tag-triggered release workflow using PyPI Trusted Publishing (no token in repo).

- [ ] **Step 1: Update `pyproject.toml`** — set `version = "0.2.0"`, and add below `classifiers`:

```toml
keywords = ["mcp", "czech", "ares", "obchodni-rejstrik", "sbirka-listin", "insolvency", "financial-statements"]

[project.urls]
Homepage = "https://github.com/janf19/rejstrik-mcp"
Issues = "https://github.com/janf19/rejstrik-mcp/issues"
```

(Confirm the actual GitHub repo URL with `git remote get-url origin` and use that.)

- [ ] **Step 2: Verify the package builds**

Run: `pip install build && python -m build`
Expected: `dist/rejstrik_mcp-0.2.0-py3-none-any.whl` and the sdist build without errors. Delete `dist/` afterwards (and ensure `dist/` is in `.gitignore`).

- [ ] **Step 3: Create `.github/workflows/release.yml`:**

```yaml
name: release
on:
  push:
    tags: ["v*"]

jobs:
  pypi:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
```

- [ ] **Step 4: Document the one-time manual setup** — add to the README (Task 12 rewrites it fully; for now append a `## Releasing` section):

```markdown
## Releasing

1. One-time: on pypi.org, add a *Trusted Publisher* for this GitHub repo
   (workflow `release.yml`, environment `pypi`).
2. Bump the version in `pyproject.toml`, commit, tag `vX.Y.Z`, push the tag.
   CI builds, publishes to PyPI, and attaches artifacts to the GitHub release.
```

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && python -m pytest -q
git add pyproject.toml .github/workflows/release.yml README.md .gitignore
git commit -m "chore: v0.2.0 packaging metadata and PyPI release workflow"
```

---

### Task 11: MCP registry manifest + Desktop Extension bundle

**Files:**
- Create: `server.json` (MCP registry), `mcpb/manifest.json` (Desktop Extension)
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Produces: registry metadata pointing at the PyPI package (stdio transport); an `.mcpb` bundle whose `mcp_config` launches `uvx rejstrik-mcp`.

- [ ] **Step 1: Create `server.json`** (official MCP registry format; verify the current schema URL at https://github.com/modelcontextprotocol/registry before committing — update the `$schema` date if a newer one exists):

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json",
  "name": "io.github.janf19/rejstrik-mcp",
  "description": "Czech company registry MCP that reads filed PDF financial statements — keyless, agent-native.",
  "version": "0.2.0",
  "packages": [
    {
      "registry_type": "pypi",
      "identifier": "rejstrik-mcp",
      "version": "0.2.0",
      "transport": { "type": "stdio" }
    }
  ]
}
```

- [ ] **Step 2: Create `mcpb/manifest.json`:**

```json
{
  "manifest_version": "0.2",
  "name": "rejstrik-mcp",
  "display_name": "Czech Registry (rejstřík)",
  "version": "0.2.0",
  "description": "Czech company registry that reads the filed PDF financial statements. No API key needed.",
  "author": { "name": "janf19" },
  "server": {
    "type": "binary",
    "entry_point": "",
    "mcp_config": {
      "command": "uvx",
      "args": ["rejstrik-mcp"]
    }
  },
  "compatibility": {
    "platforms": ["darwin", "win32", "linux"],
    "runtimes": { "python": ">=3.11" }
  }
}
```

- [ ] **Step 3: Validate the manifest**

Run: `npx @anthropic-ai/mcpb validate mcpb/manifest.json`
Expected: validation passes. If the CLI rejects `"type": "binary"` with an empty entry point, follow its error message — the authoritative schema is in the `@anthropic-ai/mcpb` package; adjust the manifest until `validate` passes while keeping `mcp_config` = `uvx rejstrik-mcp`. Record any deviation in the commit message.

- [ ] **Step 4: Pack + add to release workflow**

Run locally: `npx @anthropic-ai/mcpb pack mcpb rejstrik-mcp.mcpb` — expect a `.mcpb` file (do not commit it). Then add to `.github/workflows/release.yml` `pypi` job, before the gh-release step:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npx @anthropic-ai/mcpb pack mcpb rejstrik-mcp.mcpb
```

and add `rejstrik-mcp.mcpb` to the `files:` list of the gh-release step:

```yaml
          files: |
            dist/*
            rejstrik-mcp.mcpb
```

- [ ] **Step 5: Commit**

```bash
ruff check src/ tests/ && python -m pytest -q
git add server.json mcpb/manifest.json .github/workflows/release.yml
git commit -m "feat: MCP registry manifest and one-click .mcpb bundle"
```

---

### Task 12: README rewrite + live smoke script

**Files:**
- Modify: `README.md`
- Create: `scripts/smoke.py`

**Interfaces:**
- Consumes: everything above.
- Produces: README leading with the keyless 30-second install; `python scripts/smoke.py` exercises the live keyless path end-to-end (manual, pre-release only).

- [ ] **Step 1: Create `scripts/smoke.py`:**

```python
"""Manual live smoke test — network required, run before releases, not in CI.

Usage: python scripts/smoke.py [company]
"""

import sys

from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.ares import find_company
from rejstrik.filings.justice import list_filings
from rejstrik.service import analyze_statements, fetch_filing


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Budejovicky Budvar"
    company = find_company(query)
    print(f"[1/4] find_company: {company.name} ({company.ico})")

    filings = [f for f in list_filings(company.ico) if f.is_financial_statement]
    print(f"[2/4] list_filings: {len(filings)} financial statements")

    doc, _source = fetch_filing(company.ico)
    print(f"[3/4] get_filing: {doc.title} ({doc.year}) -> {doc.file_path} "
          f"({doc.size_bytes} bytes)")

    statements = [
        FinancialStatement(
            company_name=company.name, ico=company.ico, period_year=2024,
            currency="CZK", income_statement=[Figure(label="Tržby", value=1000.0)],
        ),
        FinancialStatement(
            company_name=company.name, ico=company.ico, period_year=2023,
            currency="CZK", income_statement=[Figure(label="Tržby", value=800.0)],
        ),
    ]
    report = analyze_statements(statements, ico=company.ico)
    print(f"[4/4] analyze_statements: {len(report.red_flags)} red flags, "
          f"{len(report.trends)} trend metrics (registry checks live)")
    assert report.trends, "trends must be computed for 2 statements"
    print("SMOKE OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it live**

Run: `python scripts/smoke.py`
Expected: four numbered lines and `SMOKE OK`. This hits ARES, the Sbírka listin portal (real PDF download), ISIR, and ADIS — if a live endpoint is down, note it and retry once before treating it as a code bug.

- [ ] **Step 3: Rewrite `README.md`.** Keep the existing sections `How it works`, `A Note On Real-World Drift`, `CI`, `Development`, `Attribution`, `License`, `Releasing` (updating tool lists where they appear). Replace everything above `How it works` with:

````markdown
# rejstrik-mcp

**Add the Czech business registry to your Claude in 30 seconds — no API key.
It reads the actual filed PDFs with your own subscription.**

```bash
claude mcp add rejstrik -- uvx rejstrik-mcp
```

Then ask: *"What happened to Budějovický Budvar's finances last year?"* —
your agent resolves the company (ARES), pulls the filed statement PDF from
the Sbírka listin, reads it itself, and gets deterministic ratios, red
flags, and trends back from the server. No OCR pipeline, no server-side AI
key, no scraping middleman.

## Why this one

|  | agent-native (MCP) | reads filed PDFs | free & open source | works without any API key |
|---|---|---|---|---|
| cz-agents-mcp and similar | ✅ | ❌ | ✅ | ✅ |
| chytryrejstrik.cz | ❌ | partly (paid) | ❌ | — |
| **rejstrik-mcp** | ✅ | ✅ | ✅ | ✅ |

## Install

**Claude Code:** `claude mcp add rejstrik -- uvx rejstrik-mcp`

**Claude Desktop:** download `rejstrik-mcp.mcpb` from the latest GitHub
release and double-click it (requires [uv](https://docs.astral.sh/uv/)) —
or add to `claude_desktop_config.json`:

```json
{ "mcpServers": { "rejstrik": { "command": "uvx", "args": ["rejstrik-mcp"] } } }
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.rejstrik]
command = "uvx"
args = ["rejstrik-mcp"]
```

**Any HTTP host:** `uvx rejstrik-mcp --http` serves streamable HTTP on
`http://127.0.0.1:8000/mcp`.

## Two modes, one server

**Keyless (default).** Your agent does the reading with your existing
subscription; the server does everything deterministic:

| Tool | What it does |
|---|---|
| `find_company` | Resolve a company by name or IČO (ARES) |
| `list_filings` | List Sbírka listin documents, financial statements first |
| `get_filing` | Download a statement PDF (latest, by year, or by id) — returns local path + embedded PDF |
| `analyze_financials` | Your extracted figures in → ratios, red flags, year-over-year trends out (no LLM) |
| `render_card` | The report as an interactive HTML card (MCP UI hosts) |
| `check_insolvency` | Insolvency register (ISIR) |
| `get_statutory_bodies` | Directors / statutory bodies (ARES) |
| `check_vat` | VAT registration + unreliable-payer flag (ARES + ADIS) |

Use the built-in **`analyze-company`** prompt (shows up as a slash command
in Claude) to run the whole loop — find → fetch PDFs → extract → analyze →
card — including multi-year trends.

**Keyed power mode (optional).** Set `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY` where the server runs and four more tools activate, doing
the PDF reading server-side with schema-locked extraction and page
citations: `extract_financials`, `ask_filing`,
`analyze_company_financials`, `analyze_company_card`. Without a key they
politely point you back to the keyless flow.
````

- [ ] **Step 4: Verify README code blocks** — run `python -m pytest -q` (nothing should break) and manually spot-check that every tool name mentioned in the README exists in `EXPOSED_TOOL_NAMES`.

- [ ] **Step 5: Commit**

```bash
ruff check src/ tests/ && python -m pytest -q
git add README.md scripts/smoke.py
git commit -m "docs: keyless-first README and live smoke script"
```

---

## Self-review notes (already applied)

- Spec coverage: `get_filing` (T3+T5), `analyze_financials` (T4+T6), `render_card` (T6), prompts (T8), graceful keyed degradation (T7), stdio default (T9), PyPI/uvx (T10), .mcpb + registry (T11), README + smoke (T12). Registry *submission* itself is a manual post-merge action (run `mcp-publisher` per registry docs) — `server.json` from T11 is the artifact it needs.
- Not in this stage (per spec): `year` params on keyed tools, `years=N` on `analyze_company_financials` (Stage 2); contracts/subsidies/owners (Stage 3).
- Two external-format risks flagged inline with verification steps: FastMCP `structured_output=False` availability (T5) and the mcpb manifest schema (T11).
