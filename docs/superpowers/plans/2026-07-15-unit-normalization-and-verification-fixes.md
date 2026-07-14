# Unit Normalization & Verification-Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-year financial analysis immune to cross-year unit mismatches (CZK vs thousands of CZK), and land the smaller fixes found in the 2026-07-15 launch-readiness audit.

**Architecture:** Record the reported scale on each `FinancialStatement` (`unit` field), convert everything to a canonical thousands-of-CZK in `normalize()`, and add a deterministic ~1000× mismatch guard in `trends.py` that suppresses `pct_change`/`cagr` and raises a red flag instead of emitting false −99.9% collapses. The smoke script learns to fail on implausible trends.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest (offline, key-free), ruff. No new dependencies.

**Design spec:** `docs/superpowers/specs/2026-07-15-unit-normalization-design.md`

## Global Constraints

- Tests are offline and key-free; mock the LLM via the `DocumentLLM` protocol and registry checks via the `*_check` injection points (CLAUDE.md).
- Before every commit run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` — all green. (If `ruff format --check` complains, run `ruff format src/ tests/` and re-check.)
- Canonical unit after `normalize()` is **thousands of CZK**. `unit=None` means "unknown, treat as already in thousands" (no conversion) — this preserves current behavior for all existing fixtures.
- Never auto-rescale on suspected mismatch — flag and suppress only.
- Final version is **0.7.1** and must agree across `pyproject.toml`, `server.json` (top-level and `packages[0].version`), `mcpb/manifest.json`, `src/rejstrik/__init__.py`, and the hardcoded assert in `tests/test_smoke.py`.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Commit the two in-tree audit fixes with a version-pin regression test

Two fixes from the audit are already in the working tree, uncommitted:
`scripts/__init__.py` (new, empty — pins `scripts` as a regular package so
`tests/test_smoke.py`'s `from scripts import smoke` can't be shadowed by a
same-named package elsewhere in the environment) and the `serverInfo.version`
pin in `src/rejstrik/mcp/server.py`. This task adds a regression test for the
pin and commits all three files.

**Files:**
- Modify: `tests/mcp/test_server.py` (append one test)
- Already modified (verify present, do not rewrite): `src/rejstrik/mcp/server.py` — import `from rejstrik import __version__` and, right after `mcp = FastMCP(...)`, the line `mcp._mcp_server.version = __version__`
- Already created (verify present): `scripts/__init__.py` (empty file)

**Interfaces:**
- Produces: nothing new — `rejstrik.mcp.server.mcp._mcp_server.version` now equals `rejstrik.__version__`.

- [ ] **Step 1: Verify the in-tree fixes exist**

Run: `git status --short` — expect `?? scripts/__init__.py` and `M src/rejstrik/mcp/server.py` (plus this plan/spec).
Run: `grep -n "_mcp_server.version" src/rejstrik/mcp/server.py` — expect one hit near the `FastMCP(` line. If either is missing, apply it:

```python
# in src/rejstrik/mcp/server.py, with the other rejstrik imports:
from rejstrik import __version__

# immediately after: mcp = FastMCP("rejstrik", stateless_http=True, json_response=True)
# FastMCP has no version kwarg; without this, serverInfo.version reports the MCP
# SDK version instead of ours. Pin it to the package version so hosts show 0.7.0.
mcp._mcp_server.version = __version__
```

- [ ] **Step 2: Append the regression test**

Append to `tests/mcp/test_server.py`:

```python
def test_server_reports_package_version():
    from rejstrik import __version__
    from rejstrik.mcp.server import mcp

    assert mcp._mcp_server.version == __version__
```

- [ ] **Step 3: Red-green check the test**

Temporarily comment out the `mcp._mcp_server.version = __version__` line in `src/rejstrik/mcp/server.py`, then:

Run: `python -m pytest tests/mcp/test_server.py::test_server_reports_package_version -q`
Expected: FAIL (`assert None == '0.7.0'` — FastMCP leaves version None; the SDK substitutes its own only at initialize time).

Uncomment the line, re-run the same command. Expected: PASS.

- [ ] **Step 4: Full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (283 + 1 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py src/rejstrik/mcp/server.py tests/mcp/test_server.py docs/superpowers/specs/2026-07-15-unit-normalization-design.md docs/superpowers/plans/2026-07-15-unit-normalization-and-verification-fixes.md
git commit -m "fix: report package version in serverInfo; pin scripts as regular package

Audit findings 2 and 3 from docs/superpowers/specs/2026-07-15-unit-normalization-design.md.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `unit` field on `FinancialStatement`

**Files:**
- Modify: `src/rejstrik/documents/schema.py`
- Test: `tests/documents/test_schema.py`

**Interfaces:**
- Produces: `FinancialStatement.unit: Literal["czk", "thousands_czk", "millions_czk"] | None` (default `None`). Tasks 3–7 rely on exactly these three string values.

- [ ] **Step 1: Write the failing tests**

Append to `tests/documents/test_schema.py` (add `import pytest` and `from pydantic import ValidationError` to the imports if not present):

```python
def test_statement_unit_accepts_known_scales():
    assert FinancialStatement(unit="thousands_czk").unit == "thousands_czk"
    assert FinancialStatement(unit="czk").unit == "czk"
    assert FinancialStatement(unit="millions_czk").unit == "millions_czk"
    assert FinancialStatement().unit is None


def test_statement_unit_rejects_unknown_scale():
    with pytest.raises(ValidationError):
        FinancialStatement(unit="bushels")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/documents/test_schema.py -q`
Expected: FAIL — `FinancialStatement` has no field `unit` (pydantic raises or the attribute is missing).

- [ ] **Step 3: Implement**

In `src/rejstrik/documents/schema.py`, change the imports and `FinancialStatement`:

```python
from typing import Literal

from pydantic import BaseModel, Field
```

```python
class FinancialStatement(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    unit: Literal["czk", "thousands_czk", "millions_czk"] | None = Field(
        default=None,
        description=(
            "Scale the figures are printed in, as declared on the statement "
            "(usually on the first page of the rozvaha): 'v celých tisících Kč' "
            "→ thousands_czk, plain Kč → czk, 'v celých milionech Kč' → "
            "millions_czk. Record every figure verbatim as printed and set this "
            "field instead of converting; None means unknown and is treated as "
            "thousands_czk, the Czech statutory default."
        ),
    )
    canonical: CanonicalFigures | None = None
    balance_sheet: list[Figure] = []
    income_statement: list[Figure] = []
    cash_flow: list[Figure] = []
    notes: list[NoteItem] = []
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/documents/test_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (the field is optional; no existing test constructs it).

```bash
git add src/rejstrik/documents/schema.py tests/documents/test_schema.py
git commit -m "feat(schema): record reported unit scale on FinancialStatement

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `normalize()` converts to canonical thousands of CZK

**Files:**
- Modify: `src/rejstrik/analysis/normalize.py`
- Test: `tests/analysis/test_normalize.py`

**Interfaces:**
- Consumes: `FinancialStatement.unit` from Task 2.
- Produces: `normalize(statement)` returns `NormalizedFinancials` whose values are always thousands of CZK; `_UNIT_TO_THOUSANDS` mapping `{"czk": 0.001, "thousands_czk": 1.0, "millions_czk": 1000.0}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analysis/test_normalize.py` (ensure `import pytest` and `from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement` are among the imports; the file already imports `normalize`):

```python
def test_normalize_converts_czk_to_thousands():
    stmt = FinancialStatement(
        unit="czk",
        canonical=CanonicalFigures(
            total_assets=Figure(label="Aktiva celkem", value=5_754_734_000.0),
            revenue=Figure(label="Tržby", value=3_666_523_000.0),
        ),
    )
    n = normalize(stmt)
    assert n.total_assets == pytest.approx(5_754_734.0)
    assert n.revenue == pytest.approx(3_666_523.0)


def test_normalize_converts_millions_to_thousands():
    stmt = FinancialStatement(
        unit="millions_czk",
        canonical=CanonicalFigures(revenue=Figure(label="Tržby", value=3_648.0)),
    )
    assert normalize(stmt).revenue == pytest.approx(3_648_000.0)


def test_normalize_thousands_and_unknown_left_as_filed():
    for unit in ("thousands_czk", None):
        stmt = FinancialStatement(
            unit=unit,
            canonical=CanonicalFigures(revenue=Figure(label="Tržby", value=1000.0)),
        )
        assert normalize(stmt).revenue == 1000.0


def test_normalize_converts_keyword_matched_figures_too():
    stmt = FinancialStatement(
        unit="czk",
        balance_sheet=[Figure(label="Aktiva celkem", value=2_000_000.0)],
    )
    assert normalize(stmt).total_assets == pytest.approx(2_000.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: the two conversion tests FAIL (values come back unconverted).

- [ ] **Step 3: Implement**

In `src/rejstrik/analysis/normalize.py`, add below `_FIELDS`:

```python
# Conversion factors to the canonical unit (thousands of CZK). None/unknown
# converts by 1.0 — Czech statutory statements are filed in whole thousands,
# so "unknown" and "thousands" behave identically.
_UNIT_TO_THOUSANDS: dict[str, float] = {
    "czk": 0.001,
    "thousands_czk": 1.0,
    "millions_czk": 1000.0,
}
```

Update the `NormalizedFinancials` docstring and `normalize()`:

```python
class NormalizedFinancials(BaseModel):
    """Headline figures in thousands of CZK (converted per statement.unit)."""

    period_year: int | None = None
    ...  # existing fields unchanged
```

```python
def normalize(statement: FinancialStatement) -> NormalizedFinancials:
    figures: list[Figure] = [
        *statement.balance_sheet,
        *statement.income_statement,
        *statement.cash_flow,
    ]
    multiplier = _UNIT_TO_THOUSANDS.get(statement.unit or "thousands_czk", 1.0)
    canonical = statement.canonical
    values: dict[str, float] = {}
    for field in _FIELDS:
        if canonical is not None:
            fig = getattr(canonical, field)
            if fig is not None and fig.value is not None:
                values[field] = fig.value * multiplier
                continue
        value = _keyword_value(field, figures)
        if value is not None:
            values[field] = value * multiplier
    return NormalizedFinancials(period_year=statement.period_year, **values)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add src/rejstrik/analysis/normalize.py tests/analysis/test_normalize.py
git commit -m "feat(analysis): normalize figures to thousands of CZK per statement unit

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Extractor instructions — verbatim figures, declared unit

**Files:**
- Modify: `src/rejstrik/documents/extract.py`
- Test: `tests/documents/test_extract.py`

**Interfaces:**
- Consumes: the `unit` field name from Task 2 (the instructions name it literally).

- [ ] **Step 1: Write the failing test**

Append to `tests/documents/test_extract.py`:

```python
def test_extract_instructions_demand_verbatim_figures_and_unit():
    low = EXTRACT_INSTRUCTIONS.lower()
    assert "verbatim" in low
    assert "`unit`" in EXTRACT_INSTRUCTIONS
    assert "thousands_czk" in EXTRACT_INSTRUCTIONS
    assert "tisících" in EXTRACT_INSTRUCTIONS
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/documents/test_extract.py -q`
Expected: FAIL (current instructions say "Use CZK unless the document states otherwise").

- [ ] **Step 3: Implement**

Replace `EXTRACT_INSTRUCTIONS` in `src/rejstrik/documents/extract.py` with:

```python
EXTRACT_INSTRUCTIONS = (
    "This is a Czech company financial statement (účetní závěrka). "
    "Extract the balance sheet (rozvaha), income statement (výkaz zisku a ztráty), "
    "cash flow if present, and the narrative notes (příloha). "
    "For every figure and note, record the source_page it was found on (1-indexed). "
    "Record every figure verbatim as printed — never rescale or convert. "
    "Statements declare their scale near the top of the rozvaha (usually "
    "'v celých tisících Kč'); set the `unit` field to match: thousands_czk for "
    "'v tisících Kč', czk for plain Kč, millions_czk for 'v milionech Kč'. "
    "If a value is not present, leave it null rather than guessing."
)
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/documents/test_extract.py -q`
Expected: PASS (including the pre-existing `test_extract_instructions_mention_czech_statements_and_pages` — "rozvaha" and "page" are still present).

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add src/rejstrik/documents/extract.py tests/documents/test_extract.py
git commit -m "feat(extract): instruct verbatim figures with declared unit scale

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Unit-mismatch guard in trends

**Files:**
- Modify: `src/rejstrik/analysis/trends.py`
- Test: `tests/analysis/test_trends.py`

**Interfaces:**
- Produces: `suspected_unit_mismatch(current: NormalizedFinancials, prior: NormalizedFinancials) -> bool` (module-level in `rejstrik.analysis.trends`; Task 6 imports it). `compute_trends` keeps its signature but returns `pct_change=None` for every metric when the pair is mismatch-suspect; `compute_trend_series` keeps its signature but returns `cagr=None` for every metric when any adjacent chronological pair is mismatch-suspect.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analysis/test_trends.py` (add `suspected_unit_mismatch` to the `from rejstrik.analysis.trends import (...)` block):

```python
def test_uniform_thousandfold_shift_suppresses_pct_change():
    cur = NormalizedFinancials(
        revenue=3_647_852.0,
        net_profit=356_318.0,
        total_assets=5_408_329.0,
        equity=4_398_302.0,
    )
    prior = NormalizedFinancials(
        revenue=3_666_523_000.0,
        net_profit=371_051_000.0,
        total_assets=5_754_734_000.0,
        equity=4_549_753_000.0,
    )
    assert suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert all(t.pct_change is None for t in items.values())
    # raw values stay visible — suppression must be honest, not silent
    assert items["revenue"].current == 3_647_852.0
    assert items["revenue"].prior == 3_666_523_000.0


def test_single_metric_thousandfold_move_is_not_suppressed():
    cur = NormalizedFinancials(revenue=1_000.0)
    prior = NormalizedFinancials(revenue=1_000_000.0)
    assert not suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == pytest.approx(-0.999)


def test_large_but_divergent_moves_are_not_suppressed():
    cur = NormalizedFinancials(revenue=5_000.0, net_profit=50.0)
    prior = NormalizedFinancials(revenue=1_000.0, net_profit=200.0)
    assert not suspected_unit_mismatch(cur, prior)
    items = {t.metric: t for t in compute_trends(cur, prior)}
    assert items["revenue"].pct_change == pytest.approx(4.0)


def test_series_cagr_suppressed_on_adjacent_unit_mismatch():
    consistent = NormalizedFinancials(
        period_year=2021, revenue=100.0, total_assets=200.0
    )
    also_consistent = NormalizedFinancials(
        period_year=2022, revenue=120.0, total_assets=210.0
    )
    scaled_up = NormalizedFinancials(
        period_year=2023, revenue=144_000.0, total_assets=220_000.0
    )
    series = compute_trend_series([consistent, also_consistent, scaled_up])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None
    assert revenue.values == [100.0, 120.0, 144_000.0]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/analysis/test_trends.py -q`
Expected: FAIL — `suspected_unit_mismatch` does not exist (ImportError).

- [ ] **Step 3: Implement**

In `src/rejstrik/analysis/trends.py`, add after `_METRICS`:

```python
def suspected_unit_mismatch(
    current: NormalizedFinancials, prior: NormalizedFinancials
) -> bool:
    """True when every headline metric present in both years moved >=100x in
    the same direction — the signature of statements read at different scales
    (CZK vs thousands of CZK), not of a real business event. Requires at
    least two comparable metrics so a genuine single-line collapse is never
    suppressed."""
    ratios: list[float] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        if (
            current_value is not None
            and prior_value is not None
            and current_value > 0
            and prior_value > 0
        ):
            ratios.append(current_value / prior_value)
    if len(ratios) < 2:
        return False
    return all(r >= 100 for r in ratios) or all(r <= 0.01 for r in ratios)
```

Rework `compute_trends` to consult it:

```python
def compute_trends(
    current: NormalizedFinancials,
    prior: NormalizedFinancials,
) -> list[TrendItem]:
    mismatch = suspected_unit_mismatch(current, prior)
    items: list[TrendItem] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        pct_change = None
        if (
            not mismatch
            and current_value is not None
            and prior_value is not None
            and prior_value != 0
        ):
            pct_change = (current_value - prior_value) / abs(prior_value)
        items.append(
            TrendItem(
                metric=metric,
                current=current_value,
                prior=prior_value,
                pct_change=pct_change,
            )
        )
    return items
```

Rework `compute_trend_series` (input is oldest-first, so `newer` is `current`):

```python
def compute_trend_series(
    chronological: list[NormalizedFinancials],
) -> list[TrendSeriesItem]:
    """Full year-by-year series per metric. Input is oldest-first."""
    mismatch = any(
        suspected_unit_mismatch(newer, older)
        for older, newer in zip(chronological, chronological[1:])
    )
    items: list[TrendSeriesItem] = []
    for metric in _METRICS:
        values = [getattr(n, metric) for n in chronological]
        items.append(
            TrendSeriesItem(
                metric=metric,
                years=[n.period_year for n in chronological],
                values=values,
                cagr=None if mismatch else _cagr(values),
            )
        )
    return items
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/analysis/test_trends.py -q`
Expected: PASS, including all pre-existing tests (normal pairs are unaffected: their ratios never reach 100×).

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add src/rejstrik/analysis/trends.py tests/analysis/test_trends.py
git commit -m "feat(analysis): suppress trends on suspected cross-year unit mismatch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Red flag for unit mismatch in `analyze_statements`

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service_analyze_statements.py`

**Interfaces:**
- Consumes: `suspected_unit_mismatch` from Task 5; `RedFlag` model from `rejstrik.analysis.redflags` (fields: `code: str`, `severity: Literal["critical","warning","info"]`, `message: str`).
- Produces: reports may carry `RedFlag(code="unit_mismatch_suspected", severity="warning")`. Task 8's smoke guard keys on this exact code string.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service_analyze_statements.py`:

```python
def _two_metric_statement(year: int, scale: float) -> FinancialStatement:
    return FinancialStatement(
        company_name="Budvar",
        ico="00514152",
        period_year=year,
        currency="CZK",
        income_statement=[Figure(label="Tržby", value=1_000.0 * scale)],
        balance_sheet=[Figure(label="Aktiva celkem", value=2_000.0 * scale)],
    )


def test_analyze_statements_flags_cross_year_unit_mismatch():
    report = analyze_statements(
        [_two_metric_statement(2024, 1.0), _two_metric_statement(2023, 1_000.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    flag = next(f for f in report.red_flags if f.code == "unit_mismatch_suspected")
    assert flag.severity == "warning"
    assert all(t.pct_change is None for t in report.trends)


def test_analyze_statements_consistent_years_carry_no_mismatch_flag():
    report = analyze_statements(
        [_two_metric_statement(2024, 1.1), _two_metric_statement(2023, 1.0)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert not any(f.code == "unit_mismatch_suspected" for f in report.red_flags)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_service_analyze_statements.py -q`
Expected: `test_analyze_statements_flags_cross_year_unit_mismatch` FAILS on the `next(...)` (StopIteration → no such flag). The `pct_change is None` half already holds via Task 5.

- [ ] **Step 3: Implement**

In `src/rejstrik/service.py`:

Change the imports:

```python
from rejstrik.analysis.redflags import RedFlag, detect_red_flags
from rejstrik.analysis.trends import (
    compute_trend_series,
    compute_trends,
    suspected_unit_mismatch,
)
```

In `analyze_statements`, right after the `red_flags = detect_red_flags(...)` call and before `trends = ...` (note `normalized_all` is newest-first, so index `i` is current and `i + 1` is prior):

```python
    if any(
        suspected_unit_mismatch(normalized_all[i], normalized_all[i + 1])
        for i in range(len(normalized_all) - 1)
    ):
        red_flags.append(
            RedFlag(
                code="unit_mismatch_suspected",
                severity="warning",
                message=(
                    "Headline figures shift ~1000x between years — the "
                    "statements were likely read at different scales (CZK vs "
                    "thousands of CZK). Year-over-year changes are suppressed; "
                    "check each statement's unit field and re-extract."
                ),
            )
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_service_analyze_statements.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add src/rejstrik/service.py tests/test_service_analyze_statements.py
git commit -m "feat(service): raise unit_mismatch_suspected red flag on ~1000x year shifts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Teach MCP tool docs and the analyze-company prompt about `unit`

**Files:**
- Modify: `src/rejstrik/mcp/server.py` (docstrings of `analyze_financials` and `estimate_valuation`; step 4 of the `analyze-company` prompt)
- Test: `tests/mcp/test_annotations.py` (append)

**Interfaces:**
- Consumes: the `unit` field (Task 2) — descriptions must name the literal values `czk`, `thousands_czk`, `millions_czk`.

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_annotations.py` (add `import asyncio` and `from rejstrik.mcp.server import mcp` if not already imported there; if the file imports the server module differently, follow its existing style):

```python
def test_keyless_analysis_tools_document_unit_field():
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for name in ("analyze_financials", "estimate_valuation"):
        desc = tools[name].description
        assert "unit" in desc, name
        assert "thousands_czk" in desc, name


def test_analyze_company_prompt_mentions_unit_field():
    from rejstrik.mcp.server import analyze_company_prompt

    text = analyze_company_prompt("Budvar", years=2)
    assert "`unit`" in text
    assert "thousands_czk" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/mcp/test_annotations.py -q`
Expected: the two new tests FAIL (descriptions don't mention `thousands_czk` yet).

- [ ] **Step 3: Implement**

In `src/rejstrik/mcp/server.py`:

Replace the `analyze_financials` docstring with:

```python
    """Deterministic financial report from statements YOU extracted from the
    get_filing PDF(s): normalize → ratios → red flags → trends (with 2+ years).
    Record figures verbatim as printed and set each statement's unit field
    ("czk" | "thousands_czk" | "millions_czk") to the scale the statement
    declares (usually 'v celých tisících Kč' → thousands_czk); the server
    converts everything to thousands of CZK, so multi-year trends stay
    comparable. Pass the ico to enrich red flags with insolvency and
    unreliable-VAT-payer checks."""
```

In the `estimate_valuation` docstring, replace the sentence
`Amounts are thousands of CZK as filed; book values are not market values. NOT investment advice.` with:

```python
    Set each statement's unit field ("czk" | "thousands_czk" | "millions_czk")
    and pass figures verbatim as printed; results are in thousands of CZK.
    Book values are not market values. NOT investment advice."""
```

In `analyze_company_prompt`, replace step 4's parenthetical
`(amounts in Czech statements are usually reported in thousands of CZK — keep them as printed and set currency to "CZK"; set period_year to the statement year; cite source_page for every figure)` with:

```text
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema (record figures verbatim as printed and set the `unit` field to the
   scale the statement declares — usually 'v celých tisících Kč' →
   thousands_czk; set currency to "CZK"; set period_year to the statement
   year; cite source_page for every figure). ALSO fill the `canonical`
```

(the rest of step 4 and the schema block stay as they are).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/mcp/test_annotations.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_annotations.py
git commit -m "docs(mcp): document unit field in keyless analysis tools and prompt

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Smoke script fails on implausible trends

**Files:**
- Modify: `scripts/smoke.py`
- Test: `tests/test_smoke.py` (append)

**Interfaces:**
- Consumes: `TrendItem` from `rejstrik.analysis.trends`; red-flag code `unit_mismatch_suspected` from Task 6.
- Produces: `smoke.trend_plausibility_issues(report) -> list[str]` — duck-typed over any object with `.red_flags` and `.trends`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_smoke.py`:

```python
def test_trend_plausibility_flags_mismatch_and_wild_swings():
    from types import SimpleNamespace

    from rejstrik.analysis.redflags import RedFlag
    from rejstrik.analysis.trends import TrendItem

    report = SimpleNamespace(
        red_flags=[
            RedFlag(code="unit_mismatch_suspected", severity="warning", message="m")
        ],
        trends=[
            TrendItem(metric="revenue", current=1.0, prior=1000.0, pct_change=-0.999)
        ],
    )
    issues = smoke.trend_plausibility_issues(report)
    assert len(issues) == 2


def test_trend_plausibility_accepts_normal_year():
    from types import SimpleNamespace

    from rejstrik.analysis.trends import TrendItem

    report = SimpleNamespace(
        red_flags=[],
        trends=[
            TrendItem(metric="revenue", current=110.0, prior=100.0, pct_change=0.1)
        ],
    )
    assert smoke.trend_plausibility_issues(report) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_smoke.py -q`
Expected: FAIL — `smoke` has no attribute `trend_plausibility_issues`.

- [ ] **Step 3: Implement**

In `scripts/smoke.py`, add after `canary()`:

```python
def trend_plausibility_issues(report) -> list[str]:
    """Sanity-check a multi-year report: unit-mismatch flags or >90% headline
    swings mean the numbers are almost certainly unit-inconsistent, and the
    smoke run must fail rather than print SMOKE OK over garbage."""
    issues = [
        f"red flag: {flag.message}"
        for flag in report.red_flags
        if flag.code == "unit_mismatch_suspected"
    ]
    for trend in report.trends:
        if trend.pct_change is not None and abs(trend.pct_change) > 0.9:
            issues.append(
                f"implausible {trend.metric} change {trend.pct_change:+.1%} "
                f"(current={trend.current}, prior={trend.prior})"
            )
    return issues
```

In `main()`, inside the `if has_llm_key():` branch, after the existing `for trend in multi_year_report.trends:` loop:

```python
        issues = trend_plausibility_issues(multi_year_report)
        if issues:
            for issue in issues:
                print(f"[5/5] IMPLAUSIBLE: {issue}")
            sys.exit("SMOKE FAILED: multi-year figures look unit-inconsistent")
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_smoke.py -q`
Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`

```bash
git add scripts/smoke.py tests/test_smoke.py
git commit -m "feat(smoke): fail the live smoke on unit-inconsistent multi-year trends

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Restore the PyPI badge in README

**Files:**
- Modify: `README.md` (line 3)

**Interfaces:** none.

- [ ] **Step 1: Edit**

Replace README line 3 (the CI badge line whose trailing comment says "PyPI badge hidden until first publish (Stage E T5/T6); restore this line: ...") with:

```markdown
[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/)
```

- [ ] **Step 2: Verify and commit**

Run: `grep -c "img.shields.io/pypi" README.md` — expected output: `1`.

```bash
git add README.md
git commit -m "docs: restore PyPI badge now that 0.7.0 is published

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Version bump to 0.7.1 and final gate

**Files:**
- Modify: `pyproject.toml` (`version = "0.7.1"`)
- Modify: `server.json` (top-level `"version"` AND `packages[0].version` — both currently `"0.7.0"`)
- Modify: `mcpb/manifest.json` (`"version": "0.7.1"` — do NOT touch `"manifest_version"`)
- Modify: `src/rejstrik/__init__.py` (`__version__ = "0.7.1"`)
- Modify: `tests/test_smoke.py` (`assert rejstrik.__version__ == "0.7.1"`)

**Interfaces:**
- Consumes: `tests/test_version_sync.py` (exists; enforces the five version fields agree).

- [ ] **Step 1: Bump all six occurrences**

Change every `0.7.0` version field listed above to `0.7.1`. Check nothing was missed:

Run: `grep -rn "0\.7\.0" pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py tests/test_smoke.py`
Expected: no output.

- [ ] **Step 2: Run the sync test**

Run: `python -m pytest tests/test_version_sync.py tests/test_smoke.py tests/mcp/test_server.py -q`
Expected: PASS (the Task 1 version-pin test now asserts 0.7.1).

- [ ] **Step 3: Full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py tests/test_smoke.py
git commit -m "chore(release): bump version to 0.7.1

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: STOP — human decisions**

Do **not** tag or push without explicit go-ahead. Remaining release steps are the user's call:

1. `git push` the commits; then tag `v0.7.1` and push the tag — this triggers `release.yml` (PyPI publish + GitHub release artifacts).
2. Before tagging, run the live check once: `python scripts/smoke.py` — it must print `SMOKE OK` and, with an LLM key set, must NOT report `IMPLAUSIBLE` lines (this is the end-to-end proof that the unit fix works on real Budvar data).
3. The MCP registry entry (`io.github.janf19/rejstrik-mcp`) is still unpublished; when publishing, use the updated `server.json` (0.7.1).
