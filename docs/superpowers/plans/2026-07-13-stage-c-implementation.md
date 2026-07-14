# Stage C: MCP Apps Card + Large-PDF Delivery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the financial card render (or degrade to readable markdown) across MCP hosts, and deliver large filed PDFs reliably via file path + a keyless page-text extractor.

**Architecture:** Two independent tracks over the existing `service.py`/`mcp/server.py` orchestration. Track 1 enriches the report model additively (per-year figures, public-money totals), rewrites the card renderer, adds a markdown fallback, and gates card output on the host's negotiated MCP Apps capability (defaulting to markdown so Claude Code is useful). Track 2 raises the embed cap, adds an `embed` tri-state to `get_filing`, records `page_count`, and adds a new keyless `read_filing_text` tool built on `pypdf`. All new logic is pure/injectable so tests stay offline and key-free.

**Tech Stack:** Python 3.11+, pydantic v2, FastMCP (`mcp` 1.28.1), `mcp-ui-server` 1.0, `pypdf` 6.14.

## Global Constraints

- Tests are offline and key-free. Mock the LLM via the `DocumentLLM` protocol and registry checks via the `*_check` injection points. Never make live HTTP calls in tests.
- Strict TDD: failing test → run it red → minimal implementation → run it green → commit. One logical change per commit.
- Every task ends by running, and requiring green from: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`.
- Card HTML must be self-contained: no `http://` or `https://` anywhere in the rendered HTML (Apps iframes are sandboxed).
- Report-model changes are strictly **additive** — new fields default to empty/`None` so `analyze_financials` / `analyze_company_financials` consumers do not break.
- Default embed cap is raised **15 MB → 25 MB** (`REJSTRIK_MAX_EMBED_BYTES` default `25000000`). A large PDF is never silently dropped; when not embedded, the file path is the primary channel.
- New dependency: `pypdf` (pure Python, no system deps). Package version bumps `0.4.0 → 0.5.0` (ships as v0.5.0).
- `read_filing_text` honesty rule: never return an empty string as if a page were blank. A page with no text layer must carry an explicit per-page note pointing to keyed `extract_financials` or filesystem reading.
- Exact repo-relative paths below. All commands run from the repo root `/home/jan/projects/rejstrik-mcp`.

---

## File map

- Modify `pyproject.toml` — add `pypdf` dependency, bump version to `0.5.0`.
- Create `tests/test_packaging.py` — guards the two `pyproject.toml` facts.
- Modify `src/rejstrik/analysis/report.py` — add `YearlyFigures`, `yearly`, `subsidies_total`, `contracts_total`, `public_money_ratio`.
- Modify `src/rejstrik/service.py` — populate the new report fields in `analyze_statements`; add `count_pdf_pages`; add `page_count` to `FilingDocument` and set it in `fetch_filing`.
- Modify `tests/analysis/test_report.py` — cover the new report fields.
- Modify `src/rejstrik/mcp/card.py` — rewrite `render_report_card` (enriched HTML) and add `render_report_markdown`.
- Modify `tests/mcp/test_card.py` — cover enriched HTML.
- Create `tests/mcp/test_card_markdown.py` — cover markdown fallback.
- Modify `src/rejstrik/mcp/server.py` — capability gating, resource registration, card-tool output selection, `get_filing` tri-state + `page_count`, `read_filing_text`, prompt update, `EXPOSED_TOOL_NAMES`.
- Create `tests/mcp/test_card_apps.py` — capability gating + resource registration.
- Modify `tests/mcp/test_card_tool.py` — updated default (markdown) + tool count.
- Modify `tests/mcp/test_get_filing.py` — `embed` tri-state matrix + `page_count`.
- Create `src/rejstrik/documents/pdftext.py` — page-range parsing + page text extraction (pypdf).
- Create `tests/documents/test_pdftext.py` — parsing + extraction + no-text honesty (generated fixtures).
- Create `tests/mcp/test_read_filing_text.py` — the tool end-to-end with fixtures.
- Modify `tests/mcp/test_prompts.py` — prompt mentions `embed="never"` + `read_filing_text`.
- Modify `README.md` and `CHANGELOG.md` (create `CHANGELOG.md` if absent) — document v0.5.0.

---

## Task 1: Declare `pypdf` and bump to v0.5.0

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `pypdf` importable as a declared dependency; package `version = "0.5.0"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging.py`:

```python
from pathlib import Path

import pypdf  # noqa: F401  — must be importable (declared dependency)

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_pyproject_bumped_to_v0_5_0():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert 'version = "0.5.0"' in text


def test_pyproject_declares_pypdf():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert "pypdf" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packaging.py -q`
Expected: FAIL on `test_pyproject_bumped_to_v0_5_0` (still `0.4.0`) — `pypdf` may already import in this venv, but the version assertion must be red.

- [ ] **Step 3: Edit `pyproject.toml`**

Change the version line:

```toml
version = "0.5.0"
```

Add `pypdf` to the `dependencies` list (keep alphabetical-ish grouping, place after `platformdirs`):

```toml
    "platformdirs>=4",
    "pypdf>=5",
    "mcp>=1.2",
    "mcp-ui-server>=1.0",
```

- [ ] **Step 4: Install so the dependency resolves, then run the test**

Run: `pip install -e ".[dev]" && python -m pytest tests/test_packaging.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_packaging.py
git commit -m "build: add pypdf dependency, bump to v0.5.0"
```

---

## Task 2: Extend the report model (per-year figures + public-money totals)

**Files:**
- Modify: `src/rejstrik/analysis/report.py`
- Modify: `src/rejstrik/service.py:145-209` (`analyze_statements`)
- Test: `tests/analysis/test_report.py`

**Interfaces:**
- Consumes: `NormalizedFinancials` (`period_year, revenue, net_profit, total_assets, equity`), `normalize()`, existing `analyze_statements(statements, *, ico=None, insolvency_check=None, vat_check=None, subsidy_check=None, contract_check=None)`.
- Produces on `CompanyFinancialReport`:
  - `yearly: list[YearlyFigures]` — one entry per input statement, ordered current-year first (same order `analyze_statements` uses).
  - `subsidies_total: float | None`, `contracts_total: float | None`, `public_money_ratio: float | None` — populated only when the matching `*_check` is supplied; otherwise `None`.
  - `class YearlyFigures(BaseModel)` with fields `period_year: int | None`, `revenue: float | None`, `net_profit: float | None`, `total_assets: float | None`, `equity: float | None` (all default `None`).

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_report.py`:

```python
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.documents.schema import Figure, FinancialStatement
from rejstrik.registry.contracts import ContractReport
from rejstrik.registry.subsidies import SubsidyReport
from rejstrik.service import analyze_statements


def _stmt(year, revenue, equity):
    return FinancialStatement(
        company_name="Y s.r.o.",
        ico="00006947",
        period_year=year,
        currency="CZK",
        balance_sheet=[Figure(label="Vlastní kapitál", value=equity)],
        income_statement=[Figure(label="Tržby", value=revenue)],
    )


def test_report_yearly_is_current_first():
    report = analyze_statements(
        [_stmt(2022, 100.0, 40.0), _stmt(2023, 120.0, 50.0)]
    )
    assert [y.period_year for y in report.yearly] == [2023, 2022]
    assert isinstance(report.yearly[0], YearlyFigures)
    assert report.yearly[0].revenue == 120.0
    assert report.yearly[1].equity == 40.0


def test_report_public_money_populated_when_checks_supplied():
    report = analyze_statements(
        [_stmt(2023, 1000.0, 500.0)],
        ico="00006947",
        insolvency_check=lambda ico: _NoInsolvency(),
        vat_check=lambda ico: _ReliableVat(),
        subsidy_check=lambda ico: SubsidyReport(ico=ico, total_amount=200.0),
        contract_check=lambda ico: ContractReport(ico=ico, total_value=50.0),
    )
    assert report.subsidies_total == 200.0
    assert report.contracts_total == 50.0
    assert report.public_money_ratio == 0.25


def test_report_public_money_none_without_checks():
    report = analyze_statements([_stmt(2023, 1000.0, 500.0)])
    assert report.subsidies_total is None
    assert report.contracts_total is None
    assert report.public_money_ratio is None


class _NoInsolvency:
    checked = True
    in_insolvency = False


class _ReliableVat:
    is_unreliable = False
```

> Note: confirm `SubsidyReport` / `ContractReport` construction args by opening `src/rejstrik/registry/subsidies.py` and `src/rejstrik/registry/contracts.py`; the fields used above (`total_amount`, `total_value`) match `analyze_statements`. Adjust constructor kwargs to whatever those models require (they may need `ico` only plus the total field).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_report.py -q`
Expected: FAIL with `ImportError: cannot import name 'YearlyFigures'`.

- [ ] **Step 3: Add the model fields**

In `src/rejstrik/analysis/report.py`, add the class and fields:

```python
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement


class YearlyFigures(BaseModel):
    period_year: int | None = None
    revenue: float | None = None
    net_profit: float | None = None
    total_assets: float | None = None
    equity: float | None = None


class CompanyFinancialReport(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    statement: FinancialStatement
    normalized: NormalizedFinancials
    ratios: Ratios
    red_flags: list[RedFlag] = []
    trends: list[TrendItem] = []
    yearly: list[YearlyFigures] = []
    subsidies_total: float | None = None
    contracts_total: float | None = None
    public_money_ratio: float | None = None
    source_filing_title: str | None = None
```

- [ ] **Step 4: Populate the fields in `analyze_statements`**

In `src/rejstrik/service.py`, edit `analyze_statements`. First import the new class at the top with the existing report import:

```python
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
```

Compute normalized figures for every statement (current-first) and capture public-money totals. Replace the body from `ordered = sorted(...)` through the `return CompanyFinancialReport(...)` with:

```python
    ordered = sorted(
        statements, key=lambda s: (s.period_year is None, -(s.period_year or 0))
    )
    normalized_all = [normalize(s) for s in ordered]
    current = ordered[0]
    normalized = normalized_all[0]
    ratios = compute_ratios(normalized)
    resolved_ico = ico or current.ico
    insolvent = None
    unreliable_vat = None
    subsidies_total = None
    contracts_total = None
    public_money_ratio = None
    if resolved_ico:
        insolvency_check = insolvency_check or check_insolvency
        vat_check = vat_check or check_vat
        status = insolvency_check(resolved_ico)
        insolvent = status.in_insolvency if status.checked else None
        unreliable_vat = vat_check(resolved_ico).is_unreliable
        # subsidy_check/contract_check stay None by default (unlike insolvency/vat) so keyless callers never trigger a live HTTP call here
        if subsidy_check:
            subsidies_total = subsidy_check(resolved_ico).total_amount
        if contract_check:
            contracts_total = contract_check(resolved_ico).total_value
        if (
            normalized.revenue
            and normalized.revenue > 0
            and (subsidies_total is not None or contracts_total is not None)
        ):
            public_total = (subsidies_total or 0.0) + (contracts_total or 0.0)
            public_money_ratio = public_total / normalized.revenue
    red_flags = detect_red_flags(
        normalized,
        ratios,
        current.notes,
        insolvent=insolvent,
        unreliable_vat=unreliable_vat,
        public_money_ratio=public_money_ratio,
    )
    trends = (
        compute_trends(normalized, normalized_all[1]) if len(ordered) > 1 else []
    )
    yearly = [
        YearlyFigures(
            period_year=n.period_year,
            revenue=n.revenue,
            net_profit=n.net_profit,
            total_assets=n.total_assets,
            equity=n.equity,
        )
        for n in normalized_all
    ]
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
        yearly=yearly,
        subsidies_total=subsidies_total,
        contracts_total=contracts_total,
        public_money_ratio=public_money_ratio,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/test_report.py -q`
Expected: PASS.

- [ ] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (existing report/service/card tests still pass — changes are additive).

- [ ] **Step 7: Commit**

```bash
git add src/rejstrik/analysis/report.py src/rejstrik/service.py tests/analysis/test_report.py
git commit -m "feat(analysis): add per-year figures and public-money totals to report"
```

---

## Task 3: Markdown fallback renderer

**Files:**
- Modify: `src/rejstrik/mcp/card.py`
- Test: `tests/mcp/test_card_markdown.py`

**Interfaces:**
- Consumes: `CompanyFinancialReport` (with `yearly`, `ratios`, `red_flags`, `trends`, `public_money_ratio`).
- Produces: `render_report_markdown(report: CompanyFinancialReport) -> str` — a compact markdown summary (header line, multi-year table, ratios list with plain-language one-liners, red-flag list sorted by severity, trend arrows, public-money line when present). No raw HTML tags.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_card_markdown.py`:

```python
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.report import CompanyFinancialReport, YearlyFigures
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp.card import render_report_markdown

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.8, equity_ratio=0.4),
    red_flags=[
        RedFlag(code="low_liquidity", severity="warning", message="Current ratio below 1."),
        RedFlag(code="insolvency", severity="critical", message="Appears in ISIR."),
    ],
    trends=[TrendItem(metric="revenue", current=120.0, prior=100.0, pct_change=0.2)],
    yearly=[
        YearlyFigures(period_year=2023, revenue=120.0, net_profit=10.0, total_assets=200.0, equity=80.0),
        YearlyFigures(period_year=2022, revenue=100.0, net_profit=8.0, total_assets=180.0, equity=72.0),
    ],
    public_money_ratio=0.3,
    source_filing_title="Ucetni zaverka 2023",
)


def test_markdown_has_no_html_tags():
    md = render_report_markdown(REPORT)
    assert "<" not in md and ">" not in md


def test_markdown_has_header_and_source():
    md = render_report_markdown(REPORT)
    assert "Test s.r.o." in md
    assert "00006947" in md
    assert "2023" in md
    assert "Ucetni zaverka 2023" in md


def test_markdown_multi_year_table_present():
    md = render_report_markdown(REPORT)
    assert "| 2023 |" in md
    assert "| 2022 |" in md
    assert "120" in md and "100" in md


def test_markdown_ratios_have_plain_language():
    md = render_report_markdown(REPORT)
    assert "current_ratio" in md
    assert "0.8" in md
    assert "liquid assets" in md  # plain-language one-liner


def test_markdown_flags_sorted_critical_first():
    md = render_report_markdown(REPORT)
    assert md.index("Appears in ISIR.") < md.index("Current ratio below 1.")
    assert "CRITICAL" in md and "WARNING" in md


def test_markdown_public_money_line():
    md = render_report_markdown(REPORT)
    assert "30%" in md  # public money share of revenue
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card_markdown.py -q`
Expected: FAIL with `ImportError: cannot import name 'render_report_markdown'`.

- [ ] **Step 3: Implement the markdown renderer**

Add to `src/rejstrik/mcp/card.py` (append after the existing code; also add the shared constants used by both renderers). At the top of the file, after `_SEVERITY_COLOR`, add:

```python
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

_RATIO_BLURB = {
    "current_ratio": "short-term obligations vs liquid assets",
    "equity_ratio": "share of assets financed by equity",
    "debt_to_equity": "leverage — liabilities per unit of equity",
    "net_margin": "net profit per unit of revenue",
    "return_on_equity": "net profit per unit of equity",
}

_ARROW = {"up": "▲", "down": "▼", "flat": "→"}


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _arrow(pct: float | None) -> str:
    if pct is None:
        return _ARROW["flat"]
    if pct > 0.0005:
        return _ARROW["up"]
    if pct < -0.0005:
        return _ARROW["down"]
    return _ARROW["flat"]


def _sorted_flags(report: CompanyFinancialReport):
    return sorted(report.red_flags, key=lambda f: _SEVERITY_RANK.get(f.severity, 3))
```

Then add the renderer:

```python
def render_report_markdown(report: CompanyFinancialReport) -> str:
    lines: list[str] = []
    header = report.company_name or "Company"
    lines.append(f"## {header}")
    lines.append(
        f"IČO {report.ico or '-'} · period {report.period_year or '-'} · "
        f"{report.currency or ''}".rstrip()
    )
    if report.source_filing_title:
        lines.append(f"Source: {report.source_filing_title}")
    lines.append("")

    if report.yearly:
        lines.append("### Figures by year")
        lines.append("| Year | Revenue | Net profit | Total assets | Equity |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for y in report.yearly:
            lines.append(
                f"| {y.period_year or '-'} | {_fmt(y.revenue)} | "
                f"{_fmt(y.net_profit)} | {_fmt(y.total_assets)} | {_fmt(y.equity)} |"
            )
        lines.append("")

    lines.append("### Ratios")
    for name, value in report.ratios.model_dump().items():
        blurb = _RATIO_BLURB.get(name, "")
        shown = _shown(value)
        suffix = f" — {blurb}" if blurb else ""
        lines.append(f"- **{name}**: {shown}{suffix}")
    lines.append("")

    if report.trends:
        lines.append("### Year-over-year (latest vs prior)")
        for t in report.trends:
            pct = f"{t.pct_change:+.0%}" if t.pct_change is not None else "n/a"
            lines.append(f"- {_arrow(t.pct_change)} {t.metric}: {pct}")
        lines.append("")

    lines.append("### Red flags")
    flags = _sorted_flags(report)
    if flags:
        for flag in flags:
            lines.append(f"- **[{flag.severity.upper()}]** {flag.message}")
    else:
        lines.append("- None detected.")
    lines.append("")

    if report.public_money_ratio is not None:
        lines.append(
            f"**Public money** (subsidies + state contracts) is "
            f"~{report.public_money_ratio:.0%} of revenue."
        )
        lines.append("")

    lines.append("_Figures as filed; typically thousands of CZK._")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_card_markdown.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/card.py tests/mcp/test_card_markdown.py
git commit -m "feat(card): add markdown fallback renderer"
```

---

## Task 4: Enrich the HTML card

**Files:**
- Modify: `src/rejstrik/mcp/card.py` (`render_report_card`)
- Test: `tests/mcp/test_card.py`

**Interfaces:**
- Consumes: `CompanyFinancialReport` (with `yearly`, `trends`, `public_money_ratio`), plus the shared helpers added in Task 3 (`_fmt`, `_RATIO_BLURB`, `_sorted_flags`).
- Produces: `render_report_card(report) -> str` returns self-contained HTML containing, in order: header (company, IČO, period, currency, source title), a multi-year figures table, ratios with plain-language one-liners, red flags sorted by severity and color-coded, a public-money section when `public_money_ratio is not None`, and a footer.

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_card.py` (extend the module-level `REPORT` usage; add these tests referencing a richer report):

```python
from rejstrik.analysis.report import YearlyFigures
from rejstrik.analysis.trends import TrendItem

RICH_REPORT = CompanyFinancialReport(
    company_name="Test & Co s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.8, equity_ratio=0.4),
    red_flags=[
        RedFlag(code="low_liquidity", severity="warning", message="Current ratio below 1."),
        RedFlag(code="insolvency", severity="critical", message="Appears in ISIR."),
    ],
    trends=[TrendItem(metric="revenue", current=120.0, prior=100.0, pct_change=0.2)],
    yearly=[
        YearlyFigures(period_year=2023, revenue=120.0, net_profit=10.0, total_assets=200.0, equity=80.0),
        YearlyFigures(period_year=2022, revenue=100.0, net_profit=8.0, total_assets=180.0, equity=72.0),
    ],
    public_money_ratio=0.3,
    source_filing_title="Ucetni zaverka 2023",
)


def test_card_shows_multi_year_table():
    html = render_report_card(RICH_REPORT)
    assert "2023" in html and "2022" in html
    assert "120" in html and "100" in html


def test_card_ratios_have_plain_language():
    html = render_report_card(RICH_REPORT)
    assert "liquid assets" in html


def test_card_flags_sorted_critical_first():
    html = render_report_card(RICH_REPORT)
    assert html.index("Appears in ISIR.") < html.index("Current ratio below 1.")


def test_card_shows_public_money_section():
    html = render_report_card(RICH_REPORT)
    assert "30%" in html
    assert "Public money" in html


def test_card_footer_notes_thousands_czk():
    html = render_report_card(RICH_REPORT)
    assert "thousands of CZK" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card.py -q`
Expected: FAIL (multi-year table / public-money assertions fail against the old renderer).

- [ ] **Step 3: Rewrite `render_report_card`**

Replace the `_STYLE` string and the `render_report_card` function in `src/rejstrik/mcp/card.py` with:

```python
_STYLE = """
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;padding:16px;color:#1f2933;background:#fff}
h1{font-size:18px;line-height:1.25;margin:0 0 2px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#52606d;margin:16px 0 6px}
.sub{color:#52606d;font-size:13px;margin-bottom:8px}
table{border-collapse:collapse;width:100%;margin-bottom:8px}
th,td{padding:5px 8px;border-bottom:1px solid #e4e7eb;font-size:13px;text-align:right}
th:first-child,td:first-child,td.k{text-align:left;color:#52606d}
.blurb{color:#7b8794}
.flag{padding:7px 10px;border-radius:6px;margin:4px 0;color:#fff;font-size:13px}
.pm{padding:8px 10px;border-radius:6px;background:#f0f4f8;font-size:13px;margin:6px 0}
.foot{color:#7b8794;font-size:11px;margin-top:12px}
"""


def render_report_card(report: CompanyFinancialReport) -> str:
    if report.yearly:
        year_head = "".join(f"<th>{_esc(y.period_year or '-')}</th>" for y in report.yearly)
        metric_rows = ""
        for label, attr in (
            ("Revenue", "revenue"),
            ("Net profit", "net_profit"),
            ("Total assets", "total_assets"),
            ("Equity", "equity"),
        ):
            cells = "".join(
                f"<td>{_esc(_fmt(getattr(y, attr)))}</td>" for y in report.yearly
            )
            metric_rows += f"<tr><td class='k'>{_esc(label)}</td>{cells}</tr>"
        yearly_html = (
            "<h2>Figures by year</h2>"
            f"<table><tr><th>Metric</th>{year_head}</tr>{metric_rows}</table>"
        )
    else:
        yearly_html = ""

    ratio_rows = "".join(
        f"<tr><td class='k'>{_esc(name)}</td><td>{_esc(_shown(value))}</td>"
        f"<td class='blurb'>{_esc(_RATIO_BLURB.get(name, ''))}</td></tr>"
        for name, value in report.ratios.model_dump().items()
    )

    flags_sorted = _sorted_flags(report)
    if flags_sorted:
        flags = "".join(
            f"<div class='flag' style='background:{_SEVERITY_COLOR.get(flag.severity, '#667085')}'>"
            f"[{_esc(flag.severity.upper())}] {_esc(flag.message)}</div>"
            for flag in flags_sorted
        )
    else:
        flags = "<div class='flag' style='background:#2f855a'>No red flags detected.</div>"

    if report.public_money_ratio is not None:
        public_money = (
            f"<div class='pm'>Public money (subsidies + state contracts) is "
            f"~{_esc(f'{report.public_money_ratio:.0%}')} of revenue.</div>"
        )
    else:
        public_money = ""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <h1>{_esc(report.company_name or "")}</h1>
  <div class="sub">IČO {_esc(report.ico or "-")} &middot; period {_esc(report.period_year or "-")} &middot; {_esc(report.currency or "")}</div>
  <div class="sub">Source: {_esc(report.source_filing_title or "Sbírka listin")}</div>
  {yearly_html}
  <h2>Ratios</h2>
  <table>{ratio_rows}</table>
  <h2>Red flags</h2>
  {flags}
  {public_money}
  <div class="foot">Figures as filed; typically thousands of CZK. Source: {_esc(report.source_filing_title or "Sbírka listin")}</div>
</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_card.py -q`
Expected: PASS (including the pre-existing self-contained/escaping tests — `IČO` and `&middot;` contain no `http`).

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/card.py tests/mcp/test_card.py
git commit -m "feat(card): enriched HTML with multi-year table, blurbs, public money"
```

---

## Task 5: Capability gating + resource registration + card-tool output selection

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_card_apps.py`
- Modify: `tests/mcp/test_card_tool.py`

**Interfaces:**
- Consumes: `render_report_card`, `render_report_markdown`, `create_ui_resource`, `TextContent`, `UIResource`, `FastMCP.get_context()`, `ctx.session.client_params.capabilities.experimental` (a `dict | None`).
- Produces in `server.py`:
  - `_apps_capability(experimental: dict | None) -> bool` — pure; `True` iff the negotiated key is present.
  - `_host_supports_apps() -> bool` — reads the request context defensively; returns `False` when there is no context or no capability (so direct calls / Claude Code get markdown).
  - `_render_card_output(report, *, apps_supported: bool) -> list[TextContent | UIResource]` — UIResource list when `apps_supported`, else a single `TextContent` markdown block.
  - `render_card` and `analyze_company_card` return `list[TextContent | UIResource]` via `_render_card_output(..., apps_supported=_host_supports_apps())`.
  - A registered resource `ui://rejstrik/report` (the card's HTML shell) and `_UI_META` attached to both card tools.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_card_apps.py`:

```python
import asyncio

from mcp.types import TextContent
from mcp_ui_server import UIResource

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement
from rejstrik.mcp import server

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(),
    red_flags=[],
    source_filing_title="Ucetni zaverka 2023",
)


def test_apps_capability_detects_key():
    assert server._apps_capability({"mcp-apps": {}}) is True
    assert server._apps_capability({}) is False
    assert server._apps_capability(None) is False


def test_render_output_markdown_when_no_apps():
    out = server._render_card_output(REPORT, apps_supported=False)
    assert len(out) == 1
    assert isinstance(out[0], TextContent)
    assert "Test s.r.o." in out[0].text
    assert "<" not in out[0].text


def test_render_output_uiresource_when_apps():
    out = server._render_card_output(REPORT, apps_supported=True)
    assert len(out) == 1
    assert isinstance(out[0], UIResource)
    assert "ui://rejstrik/report" in str(out[0].model_dump())


def test_host_supports_apps_false_without_context():
    # No active request context → defensive False (Claude Code path).
    assert server._host_supports_apps() is False


def test_card_resource_registered():
    resources = asyncio.run(server.mcp.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "ui://rejstrik/report" in uris
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card_apps.py -q`
Expected: FAIL with `AttributeError: module 'rejstrik.mcp.server' has no attribute '_apps_capability'`.

- [ ] **Step 3: Add gating, resource, and output selection in `server.py`**

In `src/rejstrik/mcp/server.py`, update the imports and add the helpers. First extend the card import:

```python
from rejstrik.mcp.card import render_report_card, render_report_markdown
```

Add near the top after `_MAX_EMBED_BYTES`:

```python
_UI_URI = "ui://rejstrik/report"
# ext-apps _meta UI declaration. VERIFY the exact key against the MCP Apps spec
# (blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps) on the implementation
# day — the ecosystem moves monthly. Override at runtime via REJSTRIK_APPS_CAPABILITY_KEY.
_UI_META = {"mcp/ui": {"resourceUri": _UI_URI}}


def _apps_capability(experimental: dict | None) -> bool:
    if not experimental:
        return False
    key = os.environ.get("REJSTRIK_APPS_CAPABILITY_KEY", "mcp-apps")
    return key in experimental


def _host_supports_apps() -> bool:
    try:
        ctx = mcp.get_context()
        experimental = ctx.session.client_params.capabilities.experimental
    except Exception:
        return False
    return _apps_capability(experimental)


def _card_ui_resource(report: CompanyFinancialReport) -> UIResource:
    return create_ui_resource(
        {
            "uri": _UI_URI,
            "content": {
                "type": "rawHtml",
                "htmlString": render_report_card(report),
            },
            "encoding": "text",
        }
    )


def _render_card_output(
    report: CompanyFinancialReport, *, apps_supported: bool
) -> list[TextContent | UIResource]:
    if apps_supported:
        return [_card_ui_resource(report)]
    return [TextContent(type="text", text=render_report_markdown(report))]
```

Register the resource (place it near the other `@mcp.*` declarations, e.g. just before `analyze_company_card`):

```python
@mcp.resource(_UI_URI, mime_type="text/html", meta=_UI_META)
def report_card_ui() -> str:
    """The financial report card's self-contained HTML shell (MCP Apps template)."""
    return render_report_card(
        CompanyFinancialReport(
            statement=FinancialStatement(),
            normalized=NormalizedFinancials(),
            ratios=Ratios(),
        )
    )
```

Add the imports needed by the resource shell at the top with the other analysis imports:

```python
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
```

Now rewrite the two card tools. Replace `analyze_company_card`:

```python
@mcp.tool(annotations=_ro("Analyze company card"), meta=_UI_META, structured_output=False)
def analyze_company_card(query: str, years: int = 1) -> list[TextContent | UIResource]:
    """Full financial report as a card, over the last `years` (1-5) years. Hosts
    that negotiate the MCP Apps capability get an interactive HTML card; others
    get a compact markdown summary. Requires a server-side API key; without one,
    use get_filing + analyze_financials + render_card."""
    _require_llm_key()
    report = _analyze_company_financials(query, years=years)
    return _render_card_output(report, apps_supported=_host_supports_apps())
```

Replace `render_card`:

```python
@mcp.tool(annotations=_ro("Render report card"), meta=_UI_META, structured_output=False)
def render_card(report: CompanyFinancialReport) -> list[TextContent | UIResource]:
    """Render a CompanyFinancialReport (from analyze_financials) as a card. Hosts
    that negotiate MCP Apps get interactive HTML; others get a compact markdown
    summary suitable for Claude Code and other text-only hosts."""
    return _render_card_output(report, apps_supported=_host_supports_apps())
```

- [ ] **Step 4: Update the existing card-tool test for the new default**

In `tests/mcp/test_card_tool.py`, replace `test_card_tool_returns_ui_resource` with the markdown-default expectation, and update the count assertion to anticipate Task 9 leaving it at 14 for now (the count changes in Task 9). Replace the test body:

```python
def test_card_tool_returns_markdown_by_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with patch.object(server, "_analyze_company_financials", return_value=REPORT):
        result = server.analyze_company_card("Test")
    assert isinstance(result, list) and len(result) == 1
    from mcp.types import TextContent

    assert isinstance(result[0], TextContent)
    assert "Test s.r.o." in result[0].text
```

(Leave `test_card_tool_in_exposed_names` asserting `== 14` for now; Task 9 updates it to 15.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_card_apps.py tests/mcp/test_card_tool.py -q`
Expected: PASS.

- [ ] **Step 6: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 7: Day-one verification note (manual, not a code change)**

Before release, run the server against MCP Inspector and at least one real Apps host (Claude Desktop). Confirm the `_UI_META` key and `ui://rejstrik/report` resource wiring match the **current** MCP Apps spec; if the convention changed, update `_UI_META` / `_apps_capability`'s default key (`REJSTRIK_APPS_CAPABILITY_KEY`) accordingly. This is the "verify current API on day one" gate from the spec; the code default is a starting point, not a guarantee.

> **TODO (human judgment required, not done by this automated pass):** This
> step needs a live Claude Desktop (or other MCP Apps host) session and the
> MCP Inspector — neither is available in this offline/keyless dev
> environment. The code ships with the concrete default described above
> (`_UI_META = {"mcp/ui": {"resourceUri": _UI_URI}}`, capability key
> `"mcp-apps"`, overridable via `REJSTRIK_APPS_CAPABILITY_KEY`) but a human
> must confirm it against the current spec before relying on card rendering
> in a real Apps host, and update the default if the ecosystem has moved on.

- [ ] **Step 8: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_card_apps.py tests/mcp/test_card_tool.py
git commit -m "feat(mcp): gate card on Apps capability, markdown fallback + ui:// resource"
```

---

## Task 6: Record `page_count` on filings

**Files:**
- Modify: `src/rejstrik/service.py` (`FilingDocument`, `fetch_filing`, add `count_pdf_pages`)
- Test: `tests/test_service_fetch.py`

**Interfaces:**
- Consumes: `PdfSource.data` (bytes), `pypdf`.
- Produces:
  - `count_pdf_pages(data: bytes) -> int | None` in `service.py` — page count via pypdf, `None` on parse failure.
  - `FilingDocument.page_count: int | None = None`, populated by `fetch_filing`.

- [ ] **Step 1: Write the failing test**

First open `tests/test_service_fetch.py` to match its existing mocking style. Add a test that a fetched document carries `page_count`. Append:

```python
import io

from pypdf import PdfWriter

from rejstrik.service import count_pdf_pages


def _two_page_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_count_pdf_pages_counts():
    assert count_pdf_pages(_two_page_pdf()) == 2


def test_count_pdf_pages_bad_bytes_returns_none():
    assert count_pdf_pages(b"not a pdf") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_fetch.py -q`
Expected: FAIL with `ImportError: cannot import name 'count_pdf_pages'`.

- [ ] **Step 3: Implement `count_pdf_pages` and thread `page_count`**

In `src/rejstrik/service.py`, add the import at the top:

```python
import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError
```

Add the function (place it above `fetch_filing`):

```python
def count_pdf_pages(data: bytes) -> int | None:
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except (PdfReadError, ValueError, OSError):
        return None
```

Add the field to `FilingDocument`:

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
    page_count: int | None = None
```

In `fetch_filing`, set it when constructing the document (add the kwarg to the `FilingDocument(...)` call):

```python
        FilingDocument(
            ico=company.ico,
            company_name=company.name,
            title=filing.title,
            year=filing.year,
            pdf_url=filing.pdf_url,
            file_path=str(path),
            sha256=source.sha256,
            size_bytes=len(source.data),
            page_count=count_pdf_pages(source.data),
        ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_service_fetch.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (existing `get_filing` tests pass — `page_count` defaults to `None` in their fake documents).

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/service.py tests/test_service_fetch.py
git commit -m "feat(service): record page_count on fetched filings"
```

---

## Task 7: `get_filing` embed tri-state + 25 MB default

**Files:**
- Modify: `src/rejstrik/mcp/server.py` (`get_filing`, `_MAX_EMBED_BYTES`)
- Test: `tests/mcp/test_get_filing.py`

**Interfaces:**
- Consumes: `_fetch_filing` → `(FilingDocument, PdfSource)`, `_MAX_EMBED_BYTES`.
- Produces: `get_filing(ico, year=None, filing_id=None, embed="auto") -> list[TextContent | EmbeddedResource]` where `embed ∈ {"auto","always","never"}`:
  - `auto`: embed iff `size_bytes <= _MAX_EMBED_BYTES` (default 25 MB), else metadata + honest path message.
  - `never`: metadata + path message only, never embed.
  - `always`: embed unless `size_bytes > _MAX_EMBED_BYTES`, in which case an honest over-cap message (never a silent drop).

- [ ] **Step 1: Write the failing test**

In `tests/mcp/test_get_filing.py`, add the tri-state tests (keep the existing ones; they exercise the default `auto` path):

```python
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
```

> Note: `test_get_filing_default_embed_cap_is_25mb` assumes `REJSTRIK_MAX_EMBED_BYTES` is unset in the test environment. `tests/conftest.py` should not set it; if some other test sets the env var, read the module constant directly as above (it is computed at import time).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_get_filing.py -q`
Expected: FAIL — `_MAX_EMBED_BYTES` is still `15000000`, and `embed` is not a parameter.

- [ ] **Step 3: Implement the tri-state and raise the cap**

In `src/rejstrik/mcp/server.py`, change the default:

```python
_MAX_EMBED_BYTES = int(os.environ.get("REJSTRIK_MAX_EMBED_BYTES", "25000000"))
```

Replace the whole `get_filing` function with:

```python
@mcp.tool(annotations=_ro("Get filing PDF"), structured_output=False)
def get_filing(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    embed: str = "auto",
) -> list[TextContent | EmbeddedResource]:
    """Download a financial statement PDF from Sbírka listin (latest, or by
    year / filing id from list_filings). Returns filing metadata with a local
    file_path and page_count, and — depending on `embed` — the PDF bytes.

    embed:
      - "auto" (default): embed only if the PDF fits the server's size cap.
      - "never": metadata + file_path only. FILESYSTEM-CAPABLE HOSTS (Claude
        Code, Codex, Desktop with fs access) SHOULD pass embed="never" and read
        the PDF from file_path — filed statements are routinely 20-25 MB and the
        path is strictly better than putting ~33 MB of base64 in context.
      - "always": embed regardless (still hard-capped; an honest message is
        returned instead of silently dropping an over-cap PDF).

    Read the PDF yourself (or call read_filing_text for a page range), then pass
    extracted figures to analyze_financials — no server-side API key needed."""
    if embed not in ("auto", "always", "never"):
        raise ValueError('embed must be "auto", "always", or "never"')
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    parts: list[TextContent | EmbeddedResource] = [
        TextContent(type="text", text=doc.model_dump_json(indent=2))
    ]
    if embed == "never":
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"Not embedding by request (embed=never). "
                    f"Read the PDF from file_path: {doc.file_path}"
                ),
            )
        )
        return parts

    over_cap = doc.size_bytes > _MAX_EMBED_BYTES
    if embed == "auto" and over_cap:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — over the {_MAX_EMBED_BYTES}-byte "
                    f"embed cap. Read it from file_path: {doc.file_path} "
                    f"(or call read_filing_text for a page range)."
                ),
            )
        )
        return parts
    if embed == "always" and over_cap:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — too large to embed even with "
                    f"embed=always (cap {_MAX_EMBED_BYTES} bytes). "
                    f"Read it from file_path: {doc.file_path}"
                ),
            )
        )
        return parts

    try:
        uri = Path(doc.file_path).as_uri()
    except ValueError:
        uri = None
    if uri is not None:
        parts.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=uri,
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
                    f"PDF at {doc.file_path} could not be embedded "
                    f"(path is not absolute). Read it from that path."
                ),
            )
        )
    return parts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_get_filing.py -q`
Expected: PASS. (The existing `test_get_filing_skips_blob_when_too_large` still passes: it sets `_MAX_EMBED_BYTES=4`, default `embed="auto"`, so the honest over-cap `TextContent` with `file_path` is returned.)

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_get_filing.py
git commit -m "feat(mcp): get_filing embed tri-state, raise cap to 25MB"
```

---

## Task 8: `pdftext` — page-range parsing + page text extraction

**Files:**
- Create: `src/rejstrik/documents/pdftext.py`
- Test: `tests/documents/test_pdftext.py`

**Interfaces:**
- Consumes: `pypdf`.
- Produces in `pdftext.py`:
  - `class PageText(BaseModel)`: `page: int`, `has_text: bool`, `text: str`, `note: str | None = None`.
  - `parse_page_range(spec: str, *, page_count: int, max_pages: int = 20) -> tuple[list[int], str | None]` — 1-based, de-duplicated, ascending, clamped to `[1, page_count]`; returns `(pages, over_cap_message)`. Grammar: `"3"`, `"1-5"`, `"1-3,7"`.
  - `extract_pages_text(data: bytes, pages: list[int]) -> list[PageText]` — one `PageText` per requested page. Pages with no extractable text get `has_text=False`, `text=""`, and an explicit honesty `note`.

- [ ] **Step 1: Write the failing test**

Create `tests/documents/test_pdftext.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_pdftext.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rejstrik.documents.pdftext'`.

- [ ] **Step 3: Implement the module**

Create `src/rejstrik/documents/pdftext.py`:

```python
import io

from pydantic import BaseModel
from pypdf import PdfReader

_NO_TEXT_NOTE = (
    "No extractable text layer on this page — the filing is likely a scanned "
    "image. Use the keyed extract_financials tool, or read the PDF from "
    "file_path with your own capabilities."
)


class PageText(BaseModel):
    page: int
    has_text: bool
    text: str
    note: str | None = None


def parse_page_range(
    spec: str, *, page_count: int, max_pages: int = 20
) -> tuple[list[int], str | None]:
    wanted: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            wanted.extend(range(start, end + 1))
        else:
            wanted.append(int(part))
    seen: set[int] = set()
    ordered: list[int] = []
    for page in sorted(wanted):
        if 1 <= page <= page_count and page not in seen:
            seen.add(page)
            ordered.append(page)
    message: str | None = None
    if len(ordered) > max_pages:
        message = (
            f"Requested {len(ordered)} pages; capped to the first {max_pages}. "
            f"Call read_filing_text again with a later page range for the rest."
        )
        ordered = ordered[:max_pages]
    return ordered, message


def extract_pages_text(data: bytes, pages: list[int]) -> list[PageText]:
    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    out: list[PageText] = []
    for page in pages:
        if page < 1 or page > total:
            out.append(
                PageText(
                    page=page,
                    has_text=False,
                    text="",
                    note=f"Page {page} is out of range (document has {total} pages).",
                )
            )
            continue
        text = reader.pages[page - 1].extract_text() or ""
        if text.strip():
            out.append(PageText(page=page, has_text=True, text=text))
        else:
            out.append(
                PageText(page=page, has_text=False, text="", note=_NO_TEXT_NOTE)
            )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/documents/test_pdftext.py -q`
Expected: PASS. (pypdf logs a recoverable `incorrect startxref pointer` line while reading the hand-written fixture; this is stderr noise, not a test failure.)

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/documents/pdftext.py tests/documents/test_pdftext.py
git commit -m "feat(documents): keyless page-range text extraction (pypdf)"
```

---

## Task 9: `read_filing_text` tool + prompt + exposed-names update

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Create: `tests/mcp/test_read_filing_text.py`
- Modify: `tests/mcp/test_card_tool.py` (tool count 14 → 15)
- Modify: `tests/mcp/test_prompts.py`

**Interfaces:**
- Consumes: `_fetch_filing` → `(FilingDocument, PdfSource)`, `count_pdf_pages`, `parse_page_range`, `extract_pages_text`, `PageText`.
- Produces:
  - `class FilingText(BaseModel)`: `ico: str`, `year: int | None`, `page_count: int`, `requested_pages: list[int]`, `pages: list[PageText]`, `message: str | None`.
  - `read_filing_text(ico, year=None, filing_id=None, pages="1-10") -> FilingText`.
  - `read_filing_text` in `EXPOSED_TOOL_NAMES` (length 15).
  - `analyze_company_prompt` mentions `embed="never"` and `read_filing_text`.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_read_filing_text.py`:

```python
import asyncio
import io
import warnings

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


def _pdf_bytes() -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_TEXT_PDF_RAW)))
        writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)
    return buf.getvalue()


def _fake_fetch(pdf: bytes):
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
            page_count=2,
        )
        return doc, PdfSource(data=pdf, sha256=doc.sha256, filename="x.pdf")

    return _inner


def test_read_filing_text_returns_text_page(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes()))
    result = server.read_filing_text("00514152", pages="1")
    assert result.page_count == 2
    assert result.requested_pages == [1]
    assert result.pages[0].has_text is True
    assert "Rozvaha 2024" in result.pages[0].text


def test_read_filing_text_is_honest_about_scanned_page(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _fake_fetch(_pdf_bytes()))
    result = server.read_filing_text("00514152", pages="2")
    assert result.pages[0].has_text is False
    assert result.pages[0].note is not None
    assert result.pages[0].text == ""


def test_read_filing_text_registered_and_exposed():
    assert "read_filing_text" in server.EXPOSED_TOOL_NAMES
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "read_filing_text" in names
```

Update `tests/mcp/test_card_tool.py` count assertion:

```python
def test_card_tool_in_exposed_names():
    assert "analyze_company_card" in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 15
```

Update `tests/mcp/test_prompts.py` `test_analyze_company_prompt_mentions_tools_and_schema` — add two needles to the loop tuple:

```python
        "read_filing_text",
        'embed="never"',
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_read_filing_text.py tests/mcp/test_card_tool.py tests/mcp/test_prompts.py -q`
Expected: FAIL — `read_filing_text` undefined, count is 14, prompt lacks the new needles.

- [ ] **Step 3: Implement the tool, exposed name, and prompt update**

In `src/rejstrik/mcp/server.py`, add imports:

```python
from rejstrik.documents.pdftext import (
    FilingText as _FilingTextModel,  # only if you keep the model in pdftext; see below
)
```

Define `FilingText` in `server.py` (it composes `PageText` from `pdftext`). Add near the top imports:

```python
from rejstrik.documents.pdftext import PageText, extract_pages_text, parse_page_range
from rejstrik.service import count_pdf_pages
```

(Extend the existing `from rejstrik.service import (...)` block to include `count_pdf_pages` rather than adding a second import line.)

Add the response model and tool (place after `get_filing`):

```python
from pydantic import BaseModel as _BaseModel


class FilingText(_BaseModel):
    ico: str
    year: int | None = None
    page_count: int
    requested_pages: list[int]
    pages: list[PageText]
    message: str | None = None


@mcp.tool(annotations=_ro("Read filing text"))
def read_filing_text(
    ico: str,
    year: int | None = None,
    filing_id: str | None = None,
    pages: str = "1-10",
) -> FilingText:
    """Extract the embedded text layer of a statement PDF for a page range —
    keyless, no LLM, no OCR. Page grammar: "3", "1-5", "1-3,7" (default "1-10").
    At most 20 pages per call. Czech filings are often scanned images with no
    text layer; pages without text are reported honestly (has_text=false) with a
    note pointing to extract_financials or filesystem reading — never a silent
    empty string."""
    doc, source = _fetch_filing(ico, year=year, filing_id=filing_id)
    page_count = doc.page_count or count_pdf_pages(source.data) or 0
    requested, message = parse_page_range(pages, page_count=page_count)
    page_texts = extract_pages_text(source.data, requested)
    return FilingText(
        ico=doc.ico,
        year=doc.year,
        page_count=page_count,
        requested_pages=requested,
        pages=page_texts,
        message=message,
    )
```

> Note: the `_FilingTextModel` import line above is a stray — do NOT add it. `FilingText` is defined locally in `server.py`. Only import `PageText`, `extract_pages_text`, `parse_page_range` from `pdftext`, and `count_pdf_pages` from `service`.

Add `read_filing_text` to `EXPOSED_TOOL_NAMES` (append to the list):

```python
    "get_contracts",
    "read_filing_text",
]
```

Update `analyze_company_prompt`. Change step 3 and add a mention of `read_filing_text`. Replace step 3's text and step 6:

```python
3. For each year, call get_filing(ico, year=...). If you can read local files
   (Claude Code, Codex, Desktop with filesystem access), pass embed="never" and
   read the PDF from the returned file_path — filed statements are routinely
   20-25 MB and the path is strictly better than embedding. Otherwise use the
   embedded resource, or call read_filing_text(ico, year=..., pages="1-10") to
   pull the text layer in digestible slices.
```

(Keep steps 4, 5, 7 as-is; step 6 already mentions `render_card`.) Ensure the literal substring `embed="never"` and `read_filing_text` both appear in the returned string.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_read_filing_text.py tests/mcp/test_card_tool.py tests/mcp/test_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_read_filing_text.py tests/mcp/test_card_tool.py tests/mcp/test_prompts.py
git commit -m "feat(mcp): add keyless read_filing_text tool, steer hosts to embed=never"
```

---

## Task 10: Documentation — README + CHANGELOG for v0.5.0

**Files:**
- Modify: `README.md`
- Modify/Create: `CHANGELOG.md`
- Test: `tests/test_packaging.py` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces: docs listing `read_filing_text`, the `embed` tri-state, the 25 MB default, and the card's markdown fallback.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_packaging.py`:

```python
def test_changelog_documents_v0_5_0():
    text = (
        Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    ).read_text(encoding="utf-8")
    assert "0.5.0" in text
    assert "read_filing_text" in text


def test_readme_mentions_read_filing_text():
    text = (
        Path(__file__).resolve().parent.parent / "README.md"
    ).read_text(encoding="utf-8")
    assert "read_filing_text" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packaging.py -q`
Expected: FAIL (CHANGELOG missing / lacks `read_filing_text`; README lacks it).

- [ ] **Step 3: Write the docs**

Create/prepend `CHANGELOG.md` with a v0.5.0 entry:

```markdown
# Changelog

## 0.5.0 — Stage C: card delivery + large PDFs

- Card output now degrades gracefully: hosts that negotiate the MCP Apps
  capability get an interactive HTML card (registered as the `ui://rejstrik/report`
  resource); text-only hosts (Claude Code, etc.) get a compact markdown summary
  instead of raw HTML. The card now shows a multi-year figures table, ratios with
  plain-language one-liners, severity-sorted red flags, and a public-money section.
- `get_filing` gains an `embed` parameter (`"auto" | "always" | "never"`, default
  `"auto"`). The default embed cap is raised 15 MB → 25 MB
  (`REJSTRIK_MAX_EMBED_BYTES`). Large PDFs are never silently dropped — filesystem
  hosts are steered to `embed="never"` and the local `file_path`. Metadata now
  includes `page_count`.
- New keyless tool `read_filing_text(ico, year=None, filing_id=None, pages="1-10")`
  extracts the PDF text layer for a page range (pypdf, no LLM/OCR). Pages without a
  text layer are reported honestly rather than as empty strings.
- New dependency: `pypdf`.
```

In `README.md`, add `read_filing_text` to the tools list and note the `embed` tri-state near the `get_filing` description. Find the tools section (search for `get_filing`) and add a bullet such as:

```markdown
- `read_filing_text(ico, year=None, filing_id=None, pages="1-10")` — keyless
  extraction of the PDF text layer for a page range (no LLM/OCR). Filesystem
  hosts should call `get_filing(..., embed="never")` and read the `file_path`;
  others can slice text with `read_filing_text`.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_packaging.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md tests/test_packaging.py
git commit -m "docs: document Stage C (v0.5.0) card fallback, embed tri-state, read_filing_text"
```

---

## Acceptance checklist (maps to spec "Acceptance")

- **Card renders in Claude Desktop** — Task 5 registers `ui://rejstrik/report` + `_UI_META`; the Task 5 day-one verification step requires an MCP Inspector + Claude Desktop screenshot (feeds Stage E). Code default may need the meta-key adjustment noted there.
- **Claude Code gets readable markdown, no raw HTML** — `_host_supports_apps()` defaults to `False`, so `render_card` / `analyze_company_card` return `TextContent` markdown (Tasks 3, 5; guaranteed by `test_render_output_markdown_when_no_apps` and `test_card_tool_returns_markdown_by_default`).
- **25 MB fixture-path flow via `embed="never"` + path** — Task 7 (`test_get_filing_never_skips_blob`, `test_get_filing_default_embed_cap_is_25mb`).
- **`read_filing_text` returns real text for a text-layer PDF and an honest explanation for a scanned one** — Tasks 8, 9 (`test_extract_returns_text_for_text_layer`, `test_read_filing_text_is_honest_about_scanned_page`).

## Self-review notes

- **Spec coverage:** MCP Apps migration + graceful markdown degradation (Tasks 3, 5); enriched card content — header, multi-year table, ratios one-liners, sorted flags, public-money, footer (Tasks 2, 4); additive report extension (Task 2); `embed` tri-state + 25 MB default + `page_count` (Tasks 6, 7); `read_filing_text` with page grammar, per-page no-text honesty, and 20-page cap (Tasks 8, 9); `pypdf` dependency (Task 1); testing matrix and acceptance (all tasks). Out-of-scope items (OCR, interactive iframe actions) are correctly not implemented.
- **Type consistency:** `YearlyFigures`, `FilingDocument.page_count`, `PageText`, `FilingText`, `_render_card_output`, `_apps_capability`, `parse_page_range`, `extract_pages_text`, `count_pdf_pages` are used with identical signatures across tasks.
- **Known uncertainty (honest):** the exact MCP Apps `_meta` key / data-binding convention is verified on day one (Task 5, Step 7); the code ships a concrete, overridable default (`REJSTRIK_APPS_CAPABILITY_KEY`, `_UI_META`) rather than a placeholder.
