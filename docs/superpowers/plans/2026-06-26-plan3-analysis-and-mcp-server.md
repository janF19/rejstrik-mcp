# Plan 3 — Analysis Layer + `analyze_company_financials` + MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the extracted financial data (Plan 2) into analysis — normalized line items, ratios, red flags, and year-over-year trends — wrap it in a one-call `analyze_company_financials` orchestrator, and expose the whole product as a Model Context Protocol server so it can be wired to Claude or any MCP-capable agent.

**Architecture:** Build on Plans 1–2. A new pure `analysis/` package (no I/O — fully unit-tested): `normalize` maps fuzzy Czech/English statement labels to canonical numeric fields; `ratios`, `redflags`, and `trends` compute over the normalized values. A thin `service.py` application layer orchestrates registry → filings → document engine → analysis into a `CompanyFinancialReport`. `mcp/server.py` registers five tools (FastMCP, stateless HTTP) that delegate to the registry, filings, document, and service functions. CLI gains an `analyze` command. The orchestration is unit-tested by patching the I/O-bound dependencies; the live MCP server is a manual smoke step.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP), `pydantic` v2, plus the existing stack (`anthropic`, `httpx`, `typer`, `selectolax`, `pytest`, `respx`).

## Global Constraints

- Python 3.11+; full type annotations; return Pydantic models, never raw dicts. (Inherited.)
- The `analysis/` package is **pure** — no network, no file, no Anthropic calls. Only `service.py` and `mcp/server.py` touch I/O.
- All numeric ratios guard against `None`/zero inputs and return `None` rather than raising.
- Diacritic-insensitive label matching uses one shared helper (`core/text.py`) — do not re-implement diacritic stripping per module.
- Model default stays `claude-opus-4-8` via Plan 2's `documents/config.py`; this plan adds no new model references.
- MCP server is **stateless HTTP** (`FastMCP(..., stateless_http=True, json_response=True)`), `streamable-http` transport — matches the "new stateless transport" goal and lets agents connect over HTTP.
- No network in tests. `service.py` orchestration tests patch `find_company` / `list_filings` / `load_pdf` / `extract_financials`. The live server is a manual smoke step only.

---

### Task 1: Shared text-normalization helper

**Files:**
- Create: `src/rejstrik/core/text.py`
- Test: `tests/core/test_text.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `normalize_label(text: str) -> str` — lowercases and strips diacritics (NFKD, drop combining marks). Used by the analysis label matcher.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_text.py
from rejstrik.core.text import normalize_label


def test_strips_diacritics_and_lowercases():
    assert normalize_label("Vlastní Kapitál") == "vlastni kapital"
    assert normalize_label("AKTIVA celkem") == "aktiva celkem"


def test_plain_ascii_unchanged():
    assert normalize_label("Revenue") == "revenue"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_text.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.core.text'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/core/text.py
import unicodedata


def normalize_label(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.lower().strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_text.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/core/text.py tests/core/test_text.py
git commit -m "feat: shared diacritic-insensitive label normalizer"
```

---

### Task 2: Normalize statement labels → canonical fields

**Files:**
- Create: `src/rejstrik/analysis/__init__.py`
- Create: `src/rejstrik/analysis/normalize.py`
- Test: `tests/analysis/test_normalize.py`
- Create: `tests/analysis/__init__.py`

**Interfaces:**
- Consumes: `FinancialStatement`, `Figure` (Plan 2 `documents/schema.py`), `normalize_label` (Task 1).
- Produces: `NormalizedFinancials` Pydantic model: `period_year: int | None`, and `float | None` fields `total_assets`, `equity`, `current_assets`, `current_liabilities`, `total_liabilities`, `revenue`, `net_profit`.
- Produces: `normalize(statement: FinancialStatement) -> NormalizedFinancials` — scans `balance_sheet` + `income_statement`, assigns each `Figure.value` to the first canonical field whose keyword set matches the (normalized) label; first match per field wins.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_normalize.py
from rejstrik.analysis.normalize import normalize, NormalizedFinancials
from rejstrik.documents.schema import FinancialStatement, Figure


def test_maps_czech_labels_to_fields():
    fs = FinancialStatement(
        period_year=2023,
        balance_sheet=[
            Figure(label="Aktiva celkem", value=1000.0),
            Figure(label="Vlastní kapitál", value=400.0),
            Figure(label="Oběžná aktiva", value=600.0),
            Figure(label="Krátkodobé závazky", value=300.0),
            Figure(label="Cizí zdroje", value=600.0),
        ],
        income_statement=[
            Figure(label="Tržby z prodeje výrobků a služeb", value=2000.0),
            Figure(label="Výsledek hospodaření za účetní období", value=150.0),
        ],
    )
    n = normalize(fs)
    assert isinstance(n, NormalizedFinancials)
    assert n.period_year == 2023
    assert n.total_assets == 1000.0
    assert n.equity == 400.0
    assert n.current_assets == 600.0
    assert n.current_liabilities == 300.0
    assert n.total_liabilities == 600.0
    assert n.revenue == 2000.0
    assert n.net_profit == 150.0


def test_missing_fields_stay_none():
    n = normalize(FinancialStatement(period_year=2022, balance_sheet=[Figure(label="Aktiva celkem", value=10.0)]))
    assert n.total_assets == 10.0
    assert n.equity is None
    assert n.revenue is None


def test_english_labels_also_match():
    fs = FinancialStatement(balance_sheet=[Figure(label="Total assets", value=5.0)],
                            income_statement=[Figure(label="Revenue", value=9.0)])
    n = normalize(fs)
    assert n.total_assets == 5.0
    assert n.revenue == 9.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/analysis/__init__.py
```

```python
# src/rejstrik/analysis/normalize.py
from pydantic import BaseModel

from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import FinancialStatement, Figure

# canonical field -> ordered keyword fragments (already diacritic-stripped, lowercase)
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "total_assets": ("aktiva celkem", "total assets"),
    "current_assets": ("obezna aktiva", "current assets"),
    "equity": ("vlastni kapital", "equity"),
    "current_liabilities": ("kratkodobe zavazky", "current liabilities"),
    "total_liabilities": ("cizi zdroje", "total liabilities"),
    "revenue": ("trzby", "vynosy", "revenue", "turnover"),
    "net_profit": ("vysledek hospodareni", "net profit", "net income", "zisk za"),
}


class NormalizedFinancials(BaseModel):
    period_year: int | None = None
    total_assets: float | None = None
    equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    total_liabilities: float | None = None
    revenue: float | None = None
    net_profit: float | None = None


def normalize(statement: FinancialStatement) -> NormalizedFinancials:
    values: dict[str, float] = {}
    figures: list[Figure] = [*statement.balance_sheet, *statement.income_statement]
    for fig in figures:
        if fig.value is None:
            continue
        label = normalize_label(fig.label)
        for field, keywords in _FIELD_KEYWORDS.items():
            if field in values:
                continue
            if any(kw in label for kw in keywords):
                values[field] = fig.value
                break
    return NormalizedFinancials(period_year=statement.period_year, **values)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_normalize.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/ tests/analysis/
git commit -m "feat: normalize statement labels to canonical fields"
```

---

### Task 3: Financial ratios

**Files:**
- Create: `src/rejstrik/analysis/ratios.py`
- Test: `tests/analysis/test_ratios.py`

**Interfaces:**
- Consumes: `NormalizedFinancials` (Task 2).
- Produces: `Ratios` Pydantic model with `float | None` fields: `current_ratio`, `equity_ratio`, `debt_to_equity`, `net_margin`, `return_on_equity`.
- Produces: `compute_ratios(n: NormalizedFinancials) -> Ratios` — safe division; any ratio whose inputs are `None` or whose denominator is `0` is `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_ratios.py
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import compute_ratios, Ratios


def test_computes_all_ratios():
    n = NormalizedFinancials(total_assets=1000.0, equity=400.0, current_assets=600.0,
                             current_liabilities=300.0, total_liabilities=600.0,
                             revenue=2000.0, net_profit=150.0)
    r = compute_ratios(n)
    assert isinstance(r, Ratios)
    assert r.current_ratio == 2.0          # 600 / 300
    assert r.equity_ratio == 0.4           # 400 / 1000
    assert r.debt_to_equity == 1.5         # 600 / 400
    assert r.net_margin == 0.075           # 150 / 2000
    assert r.return_on_equity == 0.375     # 150 / 400


def test_missing_inputs_yield_none():
    r = compute_ratios(NormalizedFinancials(equity=400.0))
    assert r.current_ratio is None
    assert r.return_on_equity is None  # net_profit missing


def test_zero_denominator_is_none():
    r = compute_ratios(NormalizedFinancials(current_assets=10.0, current_liabilities=0.0))
    assert r.current_ratio is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_ratios.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/analysis/ratios.py
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials


class Ratios(BaseModel):
    current_ratio: float | None = None
    equity_ratio: float | None = None
    debt_to_equity: float | None = None
    net_margin: float | None = None
    return_on_equity: float | None = None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_ratios(n: NormalizedFinancials) -> Ratios:
    return Ratios(
        current_ratio=_div(n.current_assets, n.current_liabilities),
        equity_ratio=_div(n.equity, n.total_assets),
        debt_to_equity=_div(n.total_liabilities, n.equity),
        net_margin=_div(n.net_profit, n.revenue),
        return_on_equity=_div(n.net_profit, n.equity),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_ratios.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/ratios.py tests/analysis/test_ratios.py
git commit -m "feat: financial ratio computation"
```

---

### Task 4: Red-flag detection

**Files:**
- Create: `src/rejstrik/analysis/redflags.py`
- Test: `tests/analysis/test_redflags.py`

**Interfaces:**
- Consumes: `NormalizedFinancials` (Task 2), `Ratios` (Task 3), `NoteItem` (Plan 2 schema), `normalize_label` (Task 1).
- Produces: `RedFlag` Pydantic model: `code: str`, `severity: str` (`"critical" | "warning" | "info"`), `message: str`.
- Produces: `detect_red_flags(n: NormalizedFinancials, ratios: Ratios, notes: list[NoteItem], insolvent: bool | None = None) -> list[RedFlag]`. Rules: negative equity → critical; net loss (`net_profit < 0`) → warning; `current_ratio < 1` → warning; `debt_to_equity > 3` → warning; a note whose topic/summary matches going-concern keywords (`going concern`, `nepretrzite trvani`) → critical; a note matching related-party keywords (`related part`, `spojene osob`, `spriznene`) → info; `insolvent is True` → critical.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_redflags.py
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import detect_red_flags, RedFlag
from rejstrik.documents.schema import NoteItem


def _codes(flags):
    return {f.code for f in flags}


def test_negative_equity_is_critical():
    flags = detect_red_flags(NormalizedFinancials(equity=-50.0), Ratios(), [])
    neg = next(f for f in flags if f.code == "negative_equity")
    assert neg.severity == "critical"


def test_liquidity_leverage_and_loss_warnings():
    n = NormalizedFinancials(net_profit=-10.0)
    r = Ratios(current_ratio=0.5, debt_to_equity=4.0)
    codes = _codes(detect_red_flags(n, r, []))
    assert {"low_liquidity", "high_leverage", "net_loss"} <= codes


def test_going_concern_and_related_party_notes():
    notes = [
        NoteItem(topic="Going concern", summary="Material uncertainty about going concern."),
        NoteItem(topic="Spřízněné osoby", summary="Půjčka jednateli."),
    ]
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), notes)
    by_code = {f.code: f for f in flags}
    assert by_code["going_concern"].severity == "critical"
    assert by_code["related_party"].severity == "info"


def test_insolvency_cross_check():
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), [], insolvent=True)
    assert any(f.code == "insolvency" and f.severity == "critical" for f in flags)


def test_clean_company_has_no_flags():
    n = NormalizedFinancials(equity=400.0, net_profit=150.0)
    r = Ratios(current_ratio=2.0, debt_to_equity=1.0)
    assert detect_red_flags(n, r, []) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_redflags.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/analysis/redflags.py
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import NoteItem

_GOING_CONCERN = ("going concern", "nepretrzite trvani")
_RELATED_PARTY = ("related part", "spojene osob", "spriznene")


class RedFlag(BaseModel):
    code: str
    severity: str
    message: str


def detect_red_flags(
    n: NormalizedFinancials,
    ratios: Ratios,
    notes: list[NoteItem],
    insolvent: bool | None = None,
) -> list[RedFlag]:
    flags: list[RedFlag] = []

    if n.equity is not None and n.equity < 0:
        flags.append(RedFlag(code="negative_equity", severity="critical",
                             message="Negative equity — liabilities exceed assets."))
    if n.net_profit is not None and n.net_profit < 0:
        flags.append(RedFlag(code="net_loss", severity="warning",
                             message="Company reported a net loss for the period."))
    if ratios.current_ratio is not None and ratios.current_ratio < 1:
        flags.append(RedFlag(code="low_liquidity", severity="warning",
                             message="Current ratio below 1 — short-term liabilities exceed current assets."))
    if ratios.debt_to_equity is not None and ratios.debt_to_equity > 3:
        flags.append(RedFlag(code="high_leverage", severity="warning",
                             message="Debt-to-equity above 3 — heavily leveraged."))

    for note in notes:
        text = normalize_label(f"{note.topic} {note.summary}")
        if any(kw in text for kw in _GOING_CONCERN):
            flags.append(RedFlag(code="going_concern", severity="critical",
                                 message=f"Going-concern note: {note.summary}"))
        if any(kw in text for kw in _RELATED_PARTY):
            flags.append(RedFlag(code="related_party", severity="info",
                                 message=f"Related-party note: {note.summary}"))

    if insolvent is True:
        flags.append(RedFlag(code="insolvency", severity="critical",
                             message="Company appears in the insolvency register (ISIR)."))

    return flags
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_redflags.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/redflags.py tests/analysis/test_redflags.py
git commit -m "feat: red-flag detection over normalized financials + notes"
```

---

### Task 5: Year-over-year trends

**Files:**
- Create: `src/rejstrik/analysis/trends.py`
- Test: `tests/analysis/test_trends.py`

**Interfaces:**
- Consumes: `NormalizedFinancials` (Task 2).
- Produces: `TrendItem` Pydantic model: `metric: str`, `current: float | None`, `prior: float | None`, `pct_change: float | None`.
- Produces: `compute_trends(current: NormalizedFinancials, prior: NormalizedFinancials) -> list[TrendItem]` — one item per metric in `("revenue", "net_profit", "total_assets", "equity")`; `pct_change = (current - prior) / abs(prior)` when both present and `prior != 0`, else `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/analysis/test_trends.py
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.trends import compute_trends, TrendItem


def test_pct_change_per_metric():
    cur = NormalizedFinancials(revenue=1200.0, net_profit=100.0, total_assets=2000.0, equity=800.0)
    prior = NormalizedFinancials(revenue=1000.0, net_profit=200.0, total_assets=2000.0, equity=400.0)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == 0.2       # +20%
    assert items["net_profit"].pct_change == -0.5   # -50%
    assert items["total_assets"].pct_change == 0.0
    assert items["equity"].pct_change == 1.0        # +100%
    assert isinstance(items["revenue"], TrendItem)


def test_missing_or_zero_prior_yields_none():
    cur = NormalizedFinancials(revenue=1200.0, equity=10.0)
    prior = NormalizedFinancials(revenue=None, equity=0.0)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change is None
    assert items["equity"].pct_change is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_trends.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/analysis/trends.py
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_METRICS = ("revenue", "net_profit", "total_assets", "equity")


class TrendItem(BaseModel):
    metric: str
    current: float | None = None
    prior: float | None = None
    pct_change: float | None = None


def compute_trends(current: NormalizedFinancials, prior: NormalizedFinancials) -> list[TrendItem]:
    items: list[TrendItem] = []
    for metric in _METRICS:
        cur = getattr(current, metric)
        pri = getattr(prior, metric)
        pct = (cur - pri) / abs(pri) if (cur is not None and pri not in (None, 0)) else None
        items.append(TrendItem(metric=metric, current=cur, prior=pri, pct_change=pct))
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_trends.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/trends.py tests/analysis/test_trends.py
git commit -m "feat: year-over-year trend computation"
```

---

### Task 6: Report model + service orchestrator

**Files:**
- Create: `src/rejstrik/analysis/report.py`
- Create: `src/rejstrik/service.py`
- Test: `tests/analysis/test_report.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `Company` (registry), `FinancialStatement` (documents), `NormalizedFinancials`, `Ratios`, `RedFlag`, `TrendItem`, `find_company`, `list_filings`, `pick_latest_financial_filing`, `load_pdf`, `extract_financials`.
- Produces: `CompanyFinancialReport` model: `company_name: str | None`, `ico: str | None`, `period_year: int | None`, `currency: str | None`, `statement: FinancialStatement`, `normalized: NormalizedFinancials`, `ratios: Ratios`, `red_flags: list[RedFlag]`, `trends: list[TrendItem] = []`, `source_filing_title: str | None`.
- Produces: `class NoStatementFound(Exception)`.
- Produces: `resolve_statement_source(query: str, client=None) -> tuple[Company, PdfSource]` — find → list → pick latest financial statement → `load_pdf`; raises `NoStatementFound` if none.
- Produces: `analyze_company_financials(query: str, *, llm=None) -> CompanyFinancialReport` — resolve → `extract_financials` → `normalize` → `compute_ratios` → `detect_red_flags` → assemble report.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis/test_report.py
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.documents.schema import FinancialStatement


def test_report_constructs_with_defaults():
    rep = CompanyFinancialReport(
        company_name="Test s.r.o.", ico="00006947", period_year=2023, currency="CZK",
        statement=FinancialStatement(), normalized=NormalizedFinancials(), ratios=Ratios(),
        red_flags=[], source_filing_title="Účetní závěrka 2023",
    )
    assert rep.trends == []
    assert rep.ico == "00006947"
```

```python
# tests/test_service.py
from unittest.mock import patch

import pytest

import rejstrik.service as service
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.schema import FinancialStatement, Figure, NoteItem
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company

COMPANY = Company(ico="00006947", name="Test s.r.o.")
FILINGS = [Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True)]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")
STATEMENT = FinancialStatement(
    company_name="Test s.r.o.", ico="00006947", period_year=2023, currency="CZK",
    balance_sheet=[Figure(label="Aktiva celkem", value=1000.0), Figure(label="Vlastní kapitál", value=-50.0)],
    income_statement=[Figure(label="Výsledek hospodaření za účetní období", value=-10.0)],
    notes=[NoteItem(topic="Going concern", summary="Material uncertainty about going concern.")],
)


def test_resolve_statement_source_returns_company_and_pdf():
    with patch.object(service, "find_company", return_value=COMPANY), \
         patch.object(service, "list_filings", return_value=FILINGS), \
         patch.object(service, "load_pdf", return_value=SRC):
        company, src = service.resolve_statement_source("Test")
    assert company.ico == "00006947"
    assert src is SRC


def test_resolve_raises_when_no_statement():
    with patch.object(service, "find_company", return_value=COMPANY), \
         patch.object(service, "list_filings", return_value=[]):
        with pytest.raises(service.NoStatementFound):
            service.resolve_statement_source("Test")


def test_analyze_company_financials_assembles_report_with_flags():
    with patch.object(service, "find_company", return_value=COMPANY), \
         patch.object(service, "list_filings", return_value=FILINGS), \
         patch.object(service, "load_pdf", return_value=SRC), \
         patch.object(service, "extract_financials", return_value=STATEMENT):
        report = service.analyze_company_financials("Test")
    assert isinstance(report, CompanyFinancialReport)
    assert report.ico == "00006947"
    assert report.normalized.total_assets == 1000.0
    codes = {f.code for f in report.red_flags}
    assert {"negative_equity", "net_loss", "going_concern"} <= codes
    assert report.source_filing_title == "Účetní závěrka 2023"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analysis/test_report.py tests/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/analysis/report.py
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement


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
    source_filing_title: str | None = None
```

```python
# src/rejstrik/service.py
import httpx

from rejstrik.analysis.normalize import normalize
from rejstrik.analysis.ratios import compute_ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.llm import DocumentLLM
from rejstrik.documents.pick import pick_latest_financial_filing
from rejstrik.documents.source import PdfSource, load_pdf
from rejstrik.filings.justice import list_filings
from rejstrik.registry.ares import find_company
from rejstrik.registry.models import Company


class NoStatementFound(Exception):
    pass


def resolve_statement_source(
    query: str, client: httpx.Client | None = None
) -> tuple[Company, PdfSource]:
    company = find_company(query, client=client)
    filing = pick_latest_financial_filing(list_filings(company.ico, client=client))
    if filing is None:
        raise NoStatementFound(f"No financial statement in Sbírka listin for {company.ico}")
    return company, load_pdf(filing, client=client)


def analyze_company_financials(
    query: str, *, llm: DocumentLLM | None = None
) -> CompanyFinancialReport:
    company, source = resolve_statement_source(query)
    statement = extract_financials(source, llm=llm)
    normalized = normalize(statement)
    ratios = compute_ratios(normalized)
    red_flags = detect_red_flags(normalized, ratios, statement.notes)
    return CompanyFinancialReport(
        company_name=statement.company_name or company.name,
        ico=statement.ico or company.ico,
        period_year=statement.period_year,
        currency=statement.currency,
        statement=statement,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        source_filing_title=pick_latest_financial_filing(list_filings(company.ico)).title
        if False else None,  # title captured below
    )
```

> **Implementer note for Step 3:** the `source_filing_title` line above is deliberately a placeholder to avoid a second `list_filings` call — replace it by capturing the filing in `resolve_statement_source`. Implement it cleanly as follows instead (this is the version to ship):

```python
# src/rejstrik/service.py  (final form)
import httpx

from rejstrik.analysis.normalize import normalize
from rejstrik.analysis.ratios import compute_ratios
from rejstrik.analysis.redflags import detect_red_flags
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.llm import DocumentLLM
from rejstrik.documents.pick import pick_latest_financial_filing
from rejstrik.documents.source import PdfSource, load_pdf
from rejstrik.filings.justice import list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company
from rejstrik.registry.models import Company


class NoStatementFound(Exception):
    pass


def resolve_statement_source(
    query: str, client: httpx.Client | None = None
) -> tuple[Company, Filing, PdfSource]:
    company = find_company(query, client=client)
    filing = pick_latest_financial_filing(list_filings(company.ico, client=client))
    if filing is None:
        raise NoStatementFound(f"No financial statement in Sbírka listin for {company.ico}")
    return company, filing, load_pdf(filing, client=client)


def analyze_company_financials(
    query: str, *, llm: DocumentLLM | None = None
) -> CompanyFinancialReport:
    company, filing, source = resolve_statement_source(query)
    statement = extract_financials(source, llm=llm)
    normalized = normalize(statement)
    ratios = compute_ratios(normalized)
    red_flags = detect_red_flags(normalized, ratios, statement.notes)
    return CompanyFinancialReport(
        company_name=statement.company_name or company.name,
        ico=statement.ico or company.ico,
        period_year=statement.period_year,
        currency=statement.currency,
        statement=statement,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        source_filing_title=filing.title,
    )
```

> Ship the **final form** only. The test for `resolve_statement_source` expects a 3-tuple `(company, filing, src)`; update Step 1's `test_resolve_statement_source_returns_company_and_pdf` to unpack three values: `company, filing, src = service.resolve_statement_source("Test")` and assert `filing.year == 2023`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/test_report.py tests/test_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/report.py src/rejstrik/service.py tests/analysis/test_report.py tests/test_service.py
git commit -m "feat: CompanyFinancialReport + analyze_company_financials service"
```

---

### Task 7: MCP server

**Files:**
- Modify: `pyproject.toml` (add `mcp` dependency + `rejstrik-mcp` script entry)
- Create: `src/rejstrik/mcp/__init__.py`
- Create: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_server.py`
- Create: `tests/mcp/__init__.py`

**Interfaces:**
- Consumes: `find_company`, `list_filings`, `resolve_statement_source`, `analyze_company_financials`, `extract_financials`, `ask_filing`, and the return models.
- Produces: module-level `mcp` (a `FastMCP` instance, stateless HTTP) with five registered tools: `find_company`, `list_filings`, `extract_financials`, `ask_filing`, `analyze_company_financials`.
- Produces: `EXPOSED_TOOL_NAMES: list[str]` (the five names) and `main() -> None` that runs `mcp.run(transport="streamable-http")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_server.py
import asyncio

from rejstrik.mcp import server


def test_exposed_tool_names():
    assert server.EXPOSED_TOOL_NAMES == [
        "find_company", "list_filings", "extract_financials", "ask_filing", "analyze_company_financials"
    ]


def test_tools_registered_on_server():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert set(server.EXPOSED_TOOL_NAMES) <= names


def test_main_is_callable():
    assert callable(server.main)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.mcp'`

- [ ] **Step 3: Write minimal implementation**

Add `"mcp>=1.2"` to `dependencies` in `pyproject.toml`, and add under `[project.scripts]`:
```toml
rejstrik-mcp = "rejstrik.mcp.server:main"
```

```python
# src/rejstrik/mcp/__init__.py
```

```python
# src/rejstrik/mcp/server.py
from mcp.server.fastmcp import FastMCP

from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.documents.answer import Answer
from rejstrik.documents.ask import ask_filing as _ask_filing
from rejstrik.documents.extract import extract_financials as _extract_financials
from rejstrik.documents.schema import FinancialStatement
from rejstrik.filings.justice import list_filings as _list_filings
from rejstrik.filings.models import Filing
from rejstrik.registry.ares import find_company as _find_company
from rejstrik.registry.models import Company
from rejstrik.service import analyze_company_financials as _analyze, resolve_statement_source

mcp = FastMCP("rejstrik", stateless_http=True, json_response=True)

EXPOSED_TOOL_NAMES = [
    "find_company",
    "list_filings",
    "extract_financials",
    "ask_filing",
    "analyze_company_financials",
]


@mcp.tool()
def find_company(query: str) -> Company:
    """Resolve a Czech company by name or IČO via the ARES registry."""
    return _find_company(query)


@mcp.tool()
def list_filings(ico: str) -> list[Filing]:
    """List a company's Sbírka listin documents (financial statements first)."""
    return _list_filings(ico)


@mcp.tool()
def extract_financials(ico: str) -> FinancialStatement:
    """Extract structured, page-cited financials from the company's latest financial statement PDF."""
    _company, _filing, source = resolve_statement_source(ico)
    return _extract_financials(source)


@mcp.tool()
def ask_filing(ico: str, question: str) -> Answer:
    """Answer a free-form question about the company's latest financial statement, with page citations."""
    _company, _filing, source = resolve_statement_source(ico)
    return _ask_filing(source, question)


@mcp.tool()
def analyze_company_financials(query: str) -> CompanyFinancialReport:
    """Full financial report for a company: extract + ratios + red flags, page-cited. The flagship one-call tool."""
    return _analyze(query)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]" && python -m pytest tests/mcp/test_server.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/rejstrik/mcp/ tests/mcp/
git commit -m "feat: MCP server exposing 5 tools (stateless streamable-http)"
```

---

### Task 8: CLI `analyze` command + DRY the loader

**Files:**
- Modify: `src/rejstrik/cli/main.py`
- Test: `tests/cli/test_analyze_cli.py`

**Interfaces:**
- Consumes: `analyze_company_financials` (service), `CompanyFinancialReport`.
- Produces CLI command `analyze <query>` → prints company/year, key ratios, and each red flag as `[SEVERITY] message`.
- Refactor: replace the existing private `_load_latest_statement(ico)` in `cli/main.py` with a call to `service.resolve_statement_source` (now returns a 3-tuple) so the loader logic lives in one place.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_analyze_cli.py
from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.documents.schema import FinancialStatement

runner = CliRunner()

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.", ico="00006947", period_year=2023, currency="CZK",
    statement=FinancialStatement(), normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.5, equity_ratio=0.4),
    red_flags=[RedFlag(code="low_liquidity", severity="warning", message="Current ratio below 1.")],
    source_filing_title="Účetní závěrka 2023",
)


def test_analyze_cli_prints_ratios_and_flags():
    with patch("rejstrik.cli.main.analyze_company_financials", return_value=REPORT):
        result = runner.invoke(app, ["analyze", "Test"])
    assert result.exit_code == 0
    assert "Test s.r.o." in result.stdout
    assert "current_ratio" in result.stdout
    assert "WARNING" in result.stdout
    assert "Current ratio below 1." in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_analyze_cli.py -v`
Expected: FAIL — `ImportError` / `AttributeError` (command not defined)

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/cli/main.py`: add imports and the command; refactor `_load_latest_statement`.

```python
# add to imports in src/rejstrik/cli/main.py
from rejstrik.service import analyze_company_financials, resolve_statement_source
```

Replace the body of the existing `_load_latest_statement` helper so it delegates to the service (keeping its `(company, source)` return shape for the `extract`/`ask` commands):

```python
def _load_latest_statement(ico: str):
    """Resolve a company to its latest financial-statement PDF via the service layer."""
    from rejstrik.service import NoStatementFound

    try:
        company, _filing, source = resolve_statement_source(ico)
    except NoStatementFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    return company, source
```

Add the `analyze` command:

```python
@app.command()
def analyze(query: str) -> None:
    """Full financial analysis: extract + ratios + red flags for a company's latest statement."""
    report = analyze_company_financials(query)
    typer.echo(f"{report.company_name}  ({report.period_year or '----'})  [{report.ico}]")
    typer.echo("Ratios:")
    for name, value in report.ratios.model_dump().items():
        shown = f"{value:.3f}" if value is not None else "-"
        typer.echo(f"  {name}: {shown}")
    if report.red_flags:
        typer.echo("Red flags:")
        for f in report.red_flags:
            typer.echo(f"  [{f.severity.upper()}] {f.message}")
    else:
        typer.echo("No red flags detected.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_analyze_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS (Plans 1–3, including the existing `extract`/`ask` CLI tests still green after the loader refactor).

- [ ] **Step 6: Manual smoke test (real API + live server — NOT in CI)**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# 1. one-call analysis via CLI
rejstrik analyze "Budějovický Budvar"
# 2. start the MCP server and confirm it serves the streamable-http endpoint
rejstrik-mcp &        # serves http://127.0.0.1:8000/mcp by default
curl -s http://127.0.0.1:8000/mcp -H "Accept: text/event-stream" -o /dev/null -w "%{http_code}\n"
kill %1
```

Confirm `analyze` prints ratios + flags, and the server starts and responds on `/mcp`. (To wire into Claude, point an MCP client at the streamable-http URL.)

- [ ] **Step 7: Commit**

```bash
git add src/rejstrik/cli/main.py tests/cli/test_analyze_cli.py
git commit -m "feat: CLI analyze command + DRY statement loader via service"
```

---

### Task 9: README + lint

**Files:**
- Modify: `README.md`
- Modify: any files flagged by `ruff`.

- [ ] **Step 1: Update README**

Add: an "Analysis" section (`rejstrik analyze <query>` example output with ratios + red flags); an "MCP server" section (`rejstrik-mcp` starts a stateless streamable-http server on `/mcp`, lists the five tools, and notes how to connect an MCP client / Claude); and a forward note that registry breadth tools (insolvency, statutory bodies, VAT — adapted from cz-agents-mcp, MIT) arrive in Plan 4.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: clean (run `ruff format src/ tests/` to fix, then re-run).

- [ ] **Step 3: Run full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md src/ tests/
git commit -m "docs: README analysis + MCP server sections; lint clean"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- Computed ratios + trends → Tasks 3, 5 (`compute_ratios`, `compute_trends`). ✓
- Red-flag detection (negative equity, going concern, leverage, insolvency cross-check) → Task 4. ✓
- Footnote/notes intelligence → `detect_red_flags` reads `FinancialStatement.notes` (going-concern + related-party); deeper free-form note querying remains `ask_filing` (Plan 2). ✓
- `analyze_company_financials` flagship orchestrator (find → pick → extract → analyze → report) → Task 6. ✓
- MCP server, stateless transport, the 5 tools → Task 7. ✓
- "one core, three faces" — MCP face now exists alongside CLI; both call the same `service`/`analysis`/`documents` core. ✓
- Insolvency cross-check is **wired but defaults to `None`** in the orchestrator — the actual ISIR lookup is a Plan 4 breadth tool; `detect_red_flags` already accepts the `insolvent` flag so Plan 4 only has to pass it. ✓
- Breadth tools (insolvency/statutory/VAT adapted from cz-agents-mcp, MIT attribution) → **Plan 4 by design** (independent registry integrations, each needing its own fixture discovery). ✓
- Interactive MCP App card (HTML result) → not in this plan; the tools return structured Pydantic data (MCP structured output). The App card is an optional presentation layer that can follow once the data tools are proven. Noted as a deliberate deferral, not a silent gap.

**Placeholder scan:** Task 6 Step 3 intentionally shows a first-draft `service.py` immediately followed by the **final form** to ship, with an explicit instruction to ship only the final form and update the one affected test to a 3-tuple unpack. This is a teaching contrast, not a leftover placeholder — the final code is complete. No other TBD/TODO. The live-server/real-API behavior is covered by the explicit manual smoke step (Task 8, Step 6).

**Type consistency:** `NormalizedFinancials` fields identical across Tasks 2/3/4/5/6. `Ratios` identical across 3/4/6/8. `RedFlag` identical across 4/6/8. `TrendItem` across 5/6. `CompanyFinancialReport` across 6/7/8. `resolve_statement_source` returns a 3-tuple `(Company, Filing, PdfSource)` consistently in service (Task 6 final form), MCP tools (Task 7), and the CLI loader (Task 8). MCP tool names in `EXPOSED_TOOL_NAMES` match the five `@mcp.tool()` function names (Task 7). ✓

**MCP-correctness notes for the implementer:**
- `FastMCP(name, stateless_http=True, json_response=True)` and `mcp.run(transport="streamable-http")` are the current SDK API (`pip install "mcp"`); Pydantic return types become structured output automatically.
- The default streamable-http endpoint is the `/mcp` subpath on `127.0.0.1:8000` — adjust host/port via FastMCP settings if needed.
- `mcp.list_tools()` is async — the test wraps it in `asyncio.run(...)`.
