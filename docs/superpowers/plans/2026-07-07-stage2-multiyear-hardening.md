# Stage 2: Multi-Year Analysis + Production Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the keyed path do genuine multi-year analysis (last N years → N PDFs → year-over-year trends), killing the `trends=[]` dead code, and harden the server for a live demo (HTTP retries, MCP tool annotations, agent onboarding, README visuals).

**Architecture:** The keyed `analyze_company_financials` is refactored to fetch up to N financial statements, LLM-extract each into `FinancialStatement`, then delegate to the already-tested `analyze_statements(list, ico=...)` built in Stage 1 — so the keyed and keyless paths share one deterministic analysis core and the trends wiring is exercised by both. The keyed single-statement tools (`extract_financials`, `ask_filing`) gain `year`/`filing_id` selectors that thread through to the Stage 1 `pick_financial_filing`. Robustness work is orthogonal polish.

**Tech Stack:** Python 3.11+, FastMCP (`mcp`), pydantic v2, httpx, typer, pytest + respx.

## Global Constraints

- CI test suite stays offline and key-free (no network, no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`). Mock the LLM via the existing `DocumentLLM` protocol; mock registry checks via the `insolvency_check`/`vat_check` injection points.
- `years` is clamped to `[1, 5]` everywhere it appears.
- Reuse `analyze_statements` and `pick_financial_filing` from Stage 1 — do NOT duplicate normalize/ratios/trends logic.
- Run `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` before every commit; all must pass.
- Bump version to `0.3.0` (Task 7).
- Windows dev machine: use `pathlib`, no POSIX-only assumptions.

---

### Task 1: `resolve_statement_source` gains year/filing_id

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service.py` (extend)

**Interfaces:**
- Consumes: `pick_financial_filing` (Stage 1).
- Produces: `resolve_statement_source(query, year=None, filing_id=None, client=None) -> tuple[Company, Filing, PdfSource]`. Backward compatible (defaults preserve "latest"). Raises `NoStatementFound` with available-years hint when nothing matches.

- [ ] **Step 1: Write failing test** — append to `tests/test_service.py`:

```python
import pytest

from rejstrik import service
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company
from rejstrik.service import NoStatementFound, resolve_statement_source


def _wire_source(monkeypatch, filings):
    monkeypatch.setattr(
        service, "find_company", lambda q, client=None: Company(ico="00514152", name="Budvar")
    )
    monkeypatch.setattr(service, "list_filings", lambda ico, client=None: filings)
    monkeypatch.setattr(
        service, "load_pdf",
        lambda filing, client=None: PdfSource(data=b"x", sha256="s", filename="f.pdf"),
    )


def _fin(year, doc_id):
    return Filing(
        title=f"ucetni zaverka {year}", year=year,
        pdf_url=f"https://x/dokumenty/sbirka-listin/{doc_id}",
        is_financial_statement=True,
    )


def test_resolve_statement_source_by_year(monkeypatch):
    _wire_source(monkeypatch, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    _company, filing, _source = resolve_statement_source("Budvar", year=2023)
    assert filing.year == 2023


def test_resolve_statement_source_missing_year_lists_available(monkeypatch):
    _wire_source(monkeypatch, [_fin(2024, "aaa"), _fin(2023, "bbb")])
    with pytest.raises(NoStatementFound) as exc:
        resolve_statement_source("Budvar", year=2000)
    assert "2024" in str(exc.value) and "2023" in str(exc.value)
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/test_service.py -k resolve_statement_source -v`
Expected: FAIL — `TypeError: resolve_statement_source() got an unexpected keyword argument 'year'`

- [ ] **Step 3: Implement** — replace `resolve_statement_source` in `src/rejstrik/service.py`:

```python
def resolve_statement_source(
    query: str,
    year: int | None = None,
    filing_id: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[Company, Filing, PdfSource]:
    company = find_company(query, client=client)
    filings = list_filings(company.ico, client=client)
    filing = pick_financial_filing(filings, year=year, filing_id=filing_id)
    if filing is None:
        years = sorted(
            {f.year for f in filings if f.is_financial_statement and f.year},
            reverse=True,
        )
        hint = (
            f" Available years: {years}." if years else " No financial statements filed."
        )
        raise NoStatementFound(
            f"No matching financial statement in Sbírka listin for {company.ico}.{hint}"
        )
    return company, filing, load_pdf(filing, client=client)
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_service.py -v` — Expected: PASS (existing callers unaffected).

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/service.py tests/test_service.py
git commit -m "feat: resolve_statement_source accepts year/filing_id"
```

---

### Task 2: Multi-year keyed `analyze_company_financials` via `analyze_statements`

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service.py` (extend)

**Interfaces:**
- Consumes: `analyze_statements` (Stage 1), `extract_financials`, `find_company`, `list_filings`, `load_pdf`.
- Produces: `analyze_company_financials(query, *, years=1, llm=None, insolvency_check=None, vat_check=None) -> CompanyFinancialReport`. Fetches up to `years` (clamped 1–5) most-recent financial statements, extracts each, delegates to `analyze_statements`. `trends` is populated for 2+ years. This removes the hardcoded `trends=[]`.

- [ ] **Step 1: Write failing test** — append to `tests/test_service.py`:

```python
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.vat import VatStatus


class _FakeLLM:
    """Returns a statement whose revenue encodes the filing year."""

    _REVENUE = {2024: 1000.0, 2023: 800.0, 2022: 600.0}

    def extract(self, source, schema, instructions):
        # filename carries the year via our fake load_pdf below
        year = int(source.filename.split("-")[0])
        return FinancialStatement(
            company_name="Budvar", ico="00514152", period_year=year, currency="CZK",
            income_statement=[Figure(label="Tržby", value=self._REVENUE[year])],
        )

    def ask(self, source, question):  # pragma: no cover - unused here
        raise NotImplementedError


def _wire_multiyear(monkeypatch):
    monkeypatch.setattr(
        service, "find_company", lambda q, client=None: Company(ico="00514152", name="Budvar")
    )
    monkeypatch.setattr(
        service, "list_filings",
        lambda ico, client=None: [_fin(2024, "aaa"), _fin(2023, "bbb"), _fin(2022, "ccc")],
    )
    monkeypatch.setattr(
        service, "load_pdf",
        lambda filing, client=None: PdfSource(
            data=b"x", sha256="s", filename=f"{filing.year}-f.pdf"
        ),
    )


def test_analyze_company_financials_multiyear_computes_trends(monkeypatch):
    _wire_multiyear(monkeypatch)
    report = service.analyze_company_financials(
        "Budvar", years=3, llm=_FakeLLM(),
        insolvency_check=lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False),
        vat_check=lambda ico: VatStatus(ico=ico, dic="CZ00514152", is_vat_payer=True, is_unreliable=False),
    )
    assert report.period_year == 2024
    revenue = next(t for t in report.trends if t.metric == "revenue")
    assert revenue.current == 1000.0 and revenue.prior == 800.0


def test_analyze_company_financials_clamps_years(monkeypatch):
    _wire_multiyear(monkeypatch)
    captured = {}
    real = service.analyze_statements

    def spy(statements, **kw):
        captured["n"] = len(statements)
        return real(statements, **kw)

    monkeypatch.setattr(service, "analyze_statements", spy)
    service.analyze_company_financials(
        "Budvar", years=99, llm=_FakeLLM(),
        insolvency_check=lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False),
        vat_check=lambda ico: VatStatus(ico=ico, dic="X", is_vat_payer=True, is_unreliable=False),
    )
    assert captured["n"] == 3  # only 3 filings exist, and 99 clamps to 5
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/test_service.py -k multiyear -v`
Expected: FAIL — `TypeError: analyze_company_financials() got an unexpected keyword argument 'years'`

- [ ] **Step 3: Implement** — replace `analyze_company_financials` in `src/rejstrik/service.py`:

```python
def analyze_company_financials(
    query: str,
    *,
    years: int = 1,
    llm: DocumentLLM | None = None,
    insolvency_check: Callable[[str], InsolvencyStatus] | None = None,
    vat_check: Callable[[str], VatStatus] | None = None,
) -> CompanyFinancialReport:
    years = max(1, min(years, 5))
    company = find_company(query)
    statements_filings = [
        f for f in list_filings(company.ico) if f.is_financial_statement
    ][:years]
    if not statements_filings:
        raise NoStatementFound(
            f"No financial statement in Sbírka listin for {company.ico}"
        )
    statements = [
        extract_financials(load_pdf(filing), llm=llm) for filing in statements_filings
    ]
    report = analyze_statements(
        statements,
        ico=company.ico,
        insolvency_check=insolvency_check,
        vat_check=vat_check,
    )
    report.company_name = report.company_name or company.name
    report.source_filing_title = statements_filings[0].title
    return report
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_service.py -v` — Expected: PASS. Confirm no `trends=[]` remains: `grep -n "trends=\[\]" src/rejstrik/service.py` returns nothing.

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/service.py tests/test_service.py
git commit -m "feat: multi-year keyed analyze_company_financials, remove trends=[] dead code"
```

---

### Task 3: Thread year/years through MCP tools and CLI

**Files:**
- Modify: `src/rejstrik/mcp/server.py`, `src/rejstrik/cli/main.py`
- Test: `tests/mcp/test_multiyear_tools.py` (new), `tests/cli/test_analyze_cli.py` (extend)

**Interfaces:**
- Produces: MCP `extract_financials(ico, year=None, filing_id=None)`, `ask_filing(ico, question, year=None, filing_id=None)`, `analyze_company_financials(query, years=1)`, `analyze_company_card(query, years=1)`. CLI `analyze` gains `--years`.

- [ ] **Step 1: Write failing tests** — create `tests/mcp/test_multiyear_tools.py`:

```python
import inspect

from rejstrik.mcp import server


def test_extract_financials_has_year_params():
    sig = inspect.signature(server.extract_financials)
    assert "year" in sig.parameters and "filing_id" in sig.parameters


def test_ask_filing_has_year_params():
    sig = inspect.signature(server.ask_filing)
    assert "year" in sig.parameters and "filing_id" in sig.parameters


def test_analyze_company_financials_has_years():
    sig = inspect.signature(server.analyze_company_financials)
    assert sig.parameters["years"].default == 1
```

Append to `tests/cli/test_analyze_cli.py` a test asserting the `analyze` command exposes a `--years` option (mirror the existing CLI test style in that file — use the `typer.testing.CliRunner` already imported there, invoke `["analyze", "Budvar", "--years", "3"]` with the service mocked, and assert exit code 0).

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/mcp/test_multiyear_tools.py -v`
Expected: FAIL — `AssertionError` (params missing).

- [ ] **Step 3: Implement.**

In `src/rejstrik/mcp/server.py`, update the four tool signatures and bodies:

```python
@mcp.tool()
def extract_financials(
    ico: str, year: int | None = None, filing_id: str | None = None
) -> FinancialStatement:
    """Extract structured financials from a statement PDF (latest, or by year /
    filing id). Requires a server-side API key; without one, use get_filing +
    analyze_financials."""
    _require_llm_key()
    _company, _filing, source = resolve_statement_source(
        ico, year=year, filing_id=filing_id
    )
    return _extract_financials(source)


@mcp.tool()
def ask_filing(
    ico: str, question: str, year: int | None = None, filing_id: str | None = None
) -> Answer:
    """Answer a question about a statement with page citations (latest, or by
    year / filing id). Requires a server-side API key; without one, use
    get_filing + analyze_financials."""
    _require_llm_key()
    _company, _filing, source = resolve_statement_source(
        ico, year=year, filing_id=filing_id
    )
    return _ask_filing(source, question)


@mcp.tool()
def analyze_company_financials(query: str, years: int = 1) -> CompanyFinancialReport:
    """Full financial report for a company over the last `years` (1-5) years,
    with year-over-year trends when years > 1. Requires a server-side API key;
    without one, use get_filing + analyze_financials."""
    _require_llm_key()
    return _analyze_company_financials(query, years=years)


@mcp.tool()
def analyze_company_card(query: str, years: int = 1) -> list[UIResource]:
    """Full financial report as an interactive HTML card, over the last `years`
    (1-5) years. Requires a server-side API key; without one, use get_filing +
    analyze_financials + render_card."""
    _require_llm_key()
    report = _analyze_company_financials(query, years=years)
    return [
        create_ui_resource(
            {
                "uri": "ui://rejstrik/report",
                "content": {"type": "rawHtml", "htmlString": render_report_card(report)},
                "encoding": "text",
            }
        )
    ]
```

In `src/rejstrik/cli/main.py`, update `analyze`:

```python
@app.command()
def analyze(query: str, years: int = typer.Option(1, "--years", min=1, max=5)) -> None:
    """Full financial analysis for a company (optionally multi-year)."""
    report = analyze_company_financials(query, years=years)
    ...  # rest of the existing body unchanged
```

(Change the import line so `analyze_company_financials` is called with `years=`.)

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp tests/cli -v` — Expected: PASS.

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py src/rejstrik/cli/main.py tests/mcp/test_multiyear_tools.py tests/cli/test_analyze_cli.py
git commit -m "feat: expose year/filing_id and years params on MCP tools and CLI"
```

---

### Task 4: MCP tool annotations

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_annotations.py` (new)

**Interfaces:**
- Produces: every tool declares `readOnlyHint=True` and `openWorldHint=True` (all tools are read-only calls to external registries), plus a human-readable `title`, via the FastMCP `@mcp.tool(annotations=ToolAnnotations(...))` argument.

- [ ] **Step 1: Write failing test** — create `tests/mcp/test_annotations.py`:

```python
import asyncio

from rejstrik.mcp import server


def test_all_tools_are_read_only_and_open_world():
    tools = asyncio.run(server.mcp.list_tools())
    exposed = {t.name: t for t in tools if t.name in server.EXPOSED_TOOL_NAMES}
    assert len(exposed) == len(server.EXPOSED_TOOL_NAMES)
    for name, tool in exposed.items():
        assert tool.annotations is not None, f"{name} missing annotations"
        assert tool.annotations.readOnlyHint is True, f"{name} not marked read-only"
        assert tool.annotations.openWorldHint is True, f"{name} not marked open-world"
        assert tool.annotations.title, f"{name} missing title"
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/mcp/test_annotations.py -v`
Expected: FAIL — `AssertionError: <tool> missing annotations`.

- [ ] **Step 3: Implement.** In `src/rejstrik/mcp/server.py` add `from mcp.types import ToolAnnotations`, then define a helper and apply it to every `@mcp.tool(...)` decorator:

```python
def _ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True, openWorldHint=True)
```

Then set `annotations=_ro("...")` on each tool decorator, e.g.:

```python
@mcp.tool(annotations=_ro("Find Czech company"))
def find_company(query: str) -> Company:
    ...
```

Apply a fitting title to all 12: Find Czech company, List Sbírka listin filings, Extract financial statement, Ask about a filing, Analyze company financials, Check insolvency, Get statutory bodies, Check VAT status, Analyze company card, Get filing PDF, Analyze extracted financials, Render report card. Keep `get_filing`'s existing `structured_output=False` alongside the new `annotations=`.

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/mcp -v` — Expected: PASS.

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_annotations.py
git commit -m "feat: read-only/open-world annotations and titles on all MCP tools"
```

---

### Task 5: HTTP retries + backoff, User-Agent version

**Files:**
- Modify: `src/rejstrik/core/http.py`
- Test: `tests/core/test_http.py` (extend)

**Interfaces:**
- Produces: `make_client(timeout=30.0, retries=3)` — an `httpx.Client` whose transport retries connection errors, and which retries idempotent GETs on 502/503/504 with exponential backoff. `USER_AGENT` updated to `0.3`.

- [ ] **Step 1: Write failing test** — extend `tests/core/test_http.py` (uses `respx`, already a dev dep):

```python
import httpx
import respx

from rejstrik.core.http import USER_AGENT, make_client


def test_user_agent_reflects_current_version():
    assert "0.3" in USER_AGENT


@respx.mock
def test_get_retries_on_503_then_succeeds():
    route = respx.get("https://example.test/x").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client = make_client(retries=3)
    resp = client.get("https://example.test/x")
    assert resp.status_code == 200
    assert route.call_count == 3
    client.close()
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/core/test_http.py -v`
Expected: FAIL — `USER_AGENT` still says `0.1`; retry test sees only 1 call.

- [ ] **Step 3: Implement** — replace `src/rejstrik/core/http.py`:

```python
import time

import httpx

USER_AGENT = "rejstrik-mcp/0.3 (+https://github.com/janF19/rejstrik-mcp)"

_RETRY_STATUS = {502, 503, 504}


class _RetryTransport(httpx.HTTPTransport):
    def __init__(self, retries: int) -> None:
        super().__init__(retries=retries)
        self._retries = retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last = None
        for attempt in range(self._retries + 1):
            response = super().handle_request(request)
            if request.method != "GET" or response.status_code not in _RETRY_STATUS:
                return response
            last = response
            if attempt < self._retries:
                response.close()
                time.sleep(min(2**attempt * 0.5, 4.0))
        return last


def make_client(timeout: float = 30.0, retries: int = 3) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
        transport=_RetryTransport(retries=retries),
    )
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/core/test_http.py -v` — Expected: PASS. If `respx` does not intercept the custom transport, switch the test to `httpx.MockTransport` injected via a `transport` param on `make_client` — but prefer the respx form; verify which works and keep the green one.

- [ ] **Step 5: Lint + full suite + commit**

```bash
ruff check src/ tests/ && ruff format src/ tests/ && python -m pytest -q
git add src/rejstrik/core/http.py tests/core/test_http.py
git commit -m "feat: retry idempotent GETs on 5xx with backoff; bump UA to 0.3"
```

---

### Task 6: CLAUDE.md + README visuals & CI badge

**Files:**
- Create: `CLAUDE.md`, `docs/media/` (placeholder note)
- Modify: `README.md`

**Interfaces:** documentation only; no test.

- [ ] **Step 1: Create `CLAUDE.md`** with the repo's agent-onboarding facts:

```markdown
# CLAUDE.md

Guidance for AI agents working in this repository.

## What this is
An MCP server + CLI exposing the Czech company registry, with the
differentiator that it reads the filed PDF financial statements. Keyless by
default (the calling agent reads PDFs); an optional server-side API key
enables in-server extraction.

## Layout
- `core/` shared HTTP (retrying client) + text utilities
- `registry/` ARES, ISIR (insolvency), ADIS (VAT), statutory bodies
- `filings/` Sbírka listin client (verejnerejstriky.msp.gov.cz)
- `documents/` PDF fetch/cache + keyed extraction + Q&A
- `analysis/` normalize → ratios → red flags → trends (pure, no I/O)
- `service.py` orchestration; `cli/` and `mcp/` are two faces over it

## Rules
- Tests are offline and key-free. Mock the LLM via the `DocumentLLM`
  protocol and registry checks via the `*_check` injection points.
- Follow TDD: failing test → minimal impl → green → commit.
- Always run `ruff check src/ tests/ && ruff format --check src/ tests/ &&
  python -m pytest -q` before committing.
- Live network checks live in `scripts/smoke.py`, never in CI.

## Commands
- Install: `pip install -e ".[dev]"`
- Test: `python -m pytest -q`
- Run MCP server (stdio): `rejstrik-mcp`  (HTTP: `rejstrik-mcp --http`)
- Live smoke: `python scripts/smoke.py`
```

- [ ] **Step 2: Add CI badge + visuals placeholders to `README.md`.** Under the H1, add:

```markdown
[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml)
```

After the "Two modes" section add:

```markdown
## See it work

![3-year analysis of Budějovický Budvar](docs/media/budvar-3year.gif)

*The interactive report card (MCP UI hosts):*

![Report card](docs/media/report-card.png)
```

Create `docs/media/README.md` with a one-line note: "Drop `budvar-3year.gif` (asciinema→gif of `rejstrik analyze "Budejovicky Budvar" --years 3`) and `report-card.png` (screenshot of analyze_company_card rendered in Claude Desktop / MCP Inspector) here."

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md docs/media/README.md
git commit -m "docs: CLAUDE.md, CI badge, README demo-media placeholders"
```

> **Manual follow-up (you):** record `docs/media/budvar-3year.gif` and
> `docs/media/report-card.png`. The placeholders keep the README structure
> ready so the images render the moment the files land.

---

### Task 7: Version bump + smoke script multi-year

**Files:**
- Modify: `pyproject.toml`, `mcpb/manifest.json`, `server.json`, `scripts/smoke.py`

- [ ] **Step 1:** Set `version = "0.3.0"` in `pyproject.toml`, `mcpb/manifest.json`, and `server.json` (both the top-level `version` and the package `version` in `server.json`).

- [ ] **Step 2:** Extend `scripts/smoke.py` to exercise multi-year: after the existing checks, if a key is present call `analyze_company_financials(company.ico, years=2)` and assert `report.trends`; print the trend metrics. Guard the keyed call with `has_llm_key()` so the keyless smoke still runs without a key.

- [ ] **Step 3:** Run `python scripts/smoke.py` live; expect `SMOKE OK`. (Network-dependent; retry once on a transient 5xx — the new retry client should absorb most.)

- [ ] **Step 4: Lint + full suite + commit**

```bash
ruff check src/ tests/ && python -m pytest -q
git add pyproject.toml mcpb/manifest.json server.json scripts/smoke.py
git commit -m "chore: v0.3.0; smoke script covers multi-year"
```

---

## Self-review notes

- Spec Stage 2 coverage: year/filing_id on keyed tools (T1, T3), `years=N` multi-year with trends (T2, T3), `trends=[]` removed (T2), years clamp 1–5 (T2). ✅
- Interview-polish coverage: tool annotations (T4), HTTP retries + UA fix (T5), CLAUDE.md + README visuals + CI badge (T6). ✅
- Shipping (PyPI publish) is intentionally NOT a task here — it requires the one-time human Trusted-Publisher setup; after this stage, tag `v0.3.0` to fire the release workflow.
- Type consistency: `analyze_company_financials(query, *, years=1, llm=, insolvency_check=, vat_check=)` in service; MCP wrapper exposes `(query, years=1)`; both call the same service function. `resolve_statement_source(query, year=, filing_id=, client=)` used identically by extract/ask tools.
