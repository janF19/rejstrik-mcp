# Stage D: Analysis Depth — Canonical Fields, More Ratios, IN05, Trends, Valuation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen the pure analysis layer — canonical extracted figures that kill keyword fragility, six more ratios, the Czech IN05 distress index, full multi-year trend series with CAGR, new red flags, and a keyless indicative-valuation tool — all deterministic and offline-testable.

**Architecture:** All new logic lives in `src/rejstrik/analysis/` and `src/rejstrik/documents/schema.py` as pure functions and pydantic models with no I/O. `FinancialStatement` gains an optional `canonical` object the extractor fills directly; `normalize()` prefers it and falls back to a hardened keyword matcher. `analyze_statements` (in `service.py`) wires the new report fields; `mcp/server.py` exposes one new tool (`estimate_valuation`) and updates the `analyze-company` prompt and the report card. Every model change is strictly additive so existing callers and cached extractions keep working.

**Tech Stack:** Python 3.11+, pydantic v2, FastMCP (`mcp`), `mcp-ui-server`. Only the standard library `statistics` module is newly used; no new third-party dependency.

## Global Constraints

- Tests are offline and key-free. Mock the LLM via the `DocumentLLM` protocol and registry checks via the `*_check` injection points. Never make live HTTP calls in tests.
- Strict TDD: failing test → run it red → minimal implementation → run it green → commit. One logical change per commit.
- Every task ends by running, and requiring green from: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`.
- All model changes are strictly **additive**: new fields default to `None`/empty so `analyze_financials`, `analyze_company_financials`, and old cached `FinancialStatement` JSON keep validating.
- Every ratio, index, and valuation method is `None`-safe and never invents data. When a required input is missing, the result is `None` (or an explicit miss-list), never a partial or guessed number.
- IN05 formula (Neumaier & Neumaierová 2005): `IN05 = 0.13·A/CZ + 0.04·EBIT/U + 3.97·EBIT/A + 0.21·VYN/A + 0.09·OA/KZ`, where A=total assets, CZ=total liabilities (cizí zdroje), EBIT=operating profit, U=interest expense (nákladové úroky), VYN=revenue, OA=current assets, KZ=current liabilities. The `EBIT/U` term is capped at **9.0** (and equals 9.0 when U=0). Zones: `distress < 0.9`, `grey` in `[0.9, 1.6]`, `value_creating > 1.6`.
- Valuation defaults (all overridable via `ValuationAssumptions`): capitalization rate `0.12`, EV/EBIT multiple `5.0`, price/revenue multiple `0.5`, earnings-dispersion threshold (coefficient of variation) `0.5`. Fixed caveats list ends with "not investment advice"; the MCP tool description carries the disclaimer too.
- Package version bumps `0.5.0 → 0.6.0` (ships as v0.6.0).
- Exact repo-relative paths below. All commands run from the repo root `/home/jan/projects/rejstrik-mcp`.

---

## File map

- Modify `src/rejstrik/documents/schema.py` — add `CanonicalFigures`; add `canonical` field to `FinancialStatement`.
- Modify `tests/documents/test_schema.py` — cover `canonical`.
- Modify `src/rejstrik/analysis/normalize.py` — extend `NormalizedFinancials`; canonical-first `normalize()` with hardened keyword fallback.
- Modify `tests/analysis/test_normalize.py` — canonical-first + trap cases.
- Modify `src/rejstrik/analysis/ratios.py` — six new ratios.
- Modify `tests/analysis/test_ratios.py` — new ratios + `None`-propagation.
- Create `src/rejstrik/analysis/in05.py` — `IN05Result`, `compute_in05`.
- Create `tests/analysis/test_in05.py` — hand-computed fixture, cap, missing inputs.
- Modify `src/rejstrik/analysis/trends.py` — `TrendSeriesItem`, `compute_trend_series`.
- Modify `tests/analysis/test_trends.py` — series + CAGR edge cases.
- Modify `src/rejstrik/analysis/redflags.py` — `interest_coverage`, negative-OCF, IN05-zone flags.
- Modify `tests/analysis/test_redflags.py` — new flags.
- Modify `src/rejstrik/analysis/report.py` — add `in05`, `trend_series`.
- Modify `src/rejstrik/service.py` — compute and wire `in05`, `trend_series`, pass `in05` to red flags.
- Modify `tests/test_service_analyze_statements.py` — assert `in05` + `trend_series` on the report.
- Create `src/rejstrik/analysis/valuation.py` — `ValuationAssumptions`, `ValuationEstimate`, `estimate_valuation`.
- Create `tests/analysis/test_valuation.py` — method fixtures, overrides, dispersion.
- Modify `src/rejstrik/mcp/server.py` — `estimate_valuation` tool, `EXPOSED_TOOL_NAMES`, prompt update.
- Modify `tests/mcp/test_server.py`, `tests/mcp/test_breadth_tools.py`, `tests/mcp/test_card_tool.py` — tool count 15→16.
- Create `tests/mcp/test_valuation_tool.py` — tool exposure + call.
- Modify `tests/mcp/test_prompts.py` — prompt mentions canonical + `estimate_valuation`.
- Modify `src/rejstrik/mcp/card.py` — ratio blurbs for new ratios + IN05 section (HTML + markdown).
- Modify `tests/mcp/test_card.py` — IN05 rendering.
- Modify `pyproject.toml`, `src/rejstrik/__init__.py`, `CHANGELOG.md`, `README.md`, `tests/test_packaging.py` — v0.6.0 + docs.

---

## Task 1: Canonical figures on `FinancialStatement`

**Files:**
- Modify: `src/rejstrik/documents/schema.py`
- Test: `tests/documents/test_schema.py`

**Interfaces:**
- Consumes: existing `Figure`.
- Produces: `CanonicalFigures` (13 `Figure | None` fields, each `None` by default, each carrying a `description` naming the Czech statutory line); `FinancialStatement.canonical: CanonicalFigures | None = None`. Field names: `total_assets, current_assets, equity, total_liabilities, current_liabilities, revenue, operating_profit, net_profit, interest_expense, cash, inventories, receivables, operating_cash_flow`.

- [ ] **Step 1: Write the failing test**

Append to `tests/documents/test_schema.py`:

```python
def test_canonical_figures_default_none_and_round_trip():
    from rejstrik.documents.schema import CanonicalFigures

    fs = FinancialStatement()
    assert fs.canonical is None

    fs2 = FinancialStatement(
        canonical=CanonicalFigures(
            total_assets=Figure(label="Aktiva celkem", value=1000.0, source_page=3),
            net_profit=Figure(label="VH za účetní období", value=120.0),
        )
    )
    restored = FinancialStatement(**fs2.model_dump())
    assert restored.canonical.total_assets.value == 1000.0
    assert restored.canonical.total_assets.source_page == 3
    assert restored.canonical.equity is None


def test_canonical_schema_names_czech_lines():
    schema = FinancialStatement.model_json_schema()
    dumped = str(schema)
    assert "Aktiva celkem" in dumped
    assert "nákladové úroky" in dumped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_schema.py -q`
Expected: FAIL (`ImportError` / `CanonicalFigures` not defined).

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/rejstrik/documents/schema.py` with:

```python
from pydantic import BaseModel, Field


class Figure(BaseModel):
    label: str
    value: float | None = None
    source_page: int | None = None


class NoteItem(BaseModel):
    topic: str
    summary: str
    source_page: int | None = None


class CanonicalFigures(BaseModel):
    """Key statutory lines mapped to stable fields. The extractor fills these
    directly; each description names the exact Czech line so a host model (or a
    keyed server prompt) knows which figure feeds which field."""

    total_assets: Figure | None = Field(
        default=None, description="Aktiva celkem (total assets)"
    )
    current_assets: Figure | None = Field(
        default=None, description="Oběžná aktiva (current assets)"
    )
    equity: Figure | None = Field(
        default=None, description="Vlastní kapitál (equity)"
    )
    total_liabilities: Figure | None = Field(
        default=None, description="Cizí zdroje (total liabilities)"
    )
    current_liabilities: Figure | None = Field(
        default=None, description="Krátkodobé závazky (current liabilities)"
    )
    revenue: Figure | None = Field(
        default=None,
        description="Tržby z prodeje výrobků, služeb a zboží (revenue)",
    )
    operating_profit: Figure | None = Field(
        default=None,
        description="Provozní výsledek hospodaření (operating profit / EBIT)",
    )
    net_profit: Figure | None = Field(
        default=None,
        description="Výsledek hospodaření za účetní období (net profit)",
    )
    interest_expense: Figure | None = Field(
        default=None, description="Nákladové úroky (interest expense)"
    )
    cash: Figure | None = Field(
        default=None,
        description="Peněžní prostředky (cash and cash equivalents)",
    )
    inventories: Figure | None = Field(
        default=None, description="Zásoby (inventories)"
    )
    receivables: Figure | None = Field(
        default=None, description="Pohledávky (receivables)"
    )
    operating_cash_flow: Figure | None = Field(
        default=None,
        description="Peněžní tok z provozní činnosti (operating cash flow)",
    )


class FinancialStatement(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    canonical: CanonicalFigures | None = None
    balance_sheet: list[Figure] = []
    income_statement: list[Figure] = []
    cash_flow: list[Figure] = []
    notes: list[NoteItem] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/documents/schema.py tests/documents/test_schema.py
git commit -m "feat(schema): add CanonicalFigures to FinancialStatement"
```

---

## Task 2: Canonical-first normalization with hardened keyword fallback

**Files:**
- Modify: `src/rejstrik/analysis/normalize.py`
- Test: `tests/analysis/test_normalize.py`

**Interfaces:**
- Consumes: `FinancialStatement`, `CanonicalFigures`, `normalize_label`.
- Produces: `NormalizedFinancials` extended with `operating_profit, interest_expense, cash, inventories, receivables, operating_cash_flow` (all `float | None`, default `None`; existing fields unchanged). `normalize(statement) -> NormalizedFinancials` prefers `statement.canonical`, else keyword fallback that (a) rejects asset-sale revenue lines and (b) requires "za ucetni obdobi" context for net profit.

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_normalize.py`:

```python
from rejstrik.documents.schema import CanonicalFigures


def test_canonical_takes_precedence_over_keywords():
    fs = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            revenue=Figure(label="Tržby", value=999.0),
        ),
        income_statement=[Figure(label="Tržby z prodeje výrobků", value=2000.0)],
    )
    assert normalize(fs).revenue == 999.0


def test_fallback_ignores_asset_sale_revenue():
    fs = FinancialStatement(
        income_statement=[
            Figure(label="Tržby z prodeje dlouhodobého majetku a materiálu", value=5.0),
            Figure(label="Tržby z prodeje výrobků a služeb", value=2000.0),
        ]
    )
    assert normalize(fs).revenue == 2000.0


def test_fallback_separates_operating_and_net_result():
    fs = FinancialStatement(
        income_statement=[
            Figure(label="Provozní výsledek hospodaření", value=300.0),
            Figure(label="Výsledek hospodaření za účetní období", value=150.0),
        ]
    )
    n = normalize(fs)
    assert n.operating_profit == 300.0
    assert n.net_profit == 150.0


def test_fallback_bare_result_is_not_net_profit():
    fs = FinancialStatement(
        income_statement=[Figure(label="Provozní výsledek hospodaření", value=300.0)]
    )
    n = normalize(fs)
    assert n.operating_profit == 300.0
    assert n.net_profit is None


def test_fallback_maps_new_fields():
    fs = FinancialStatement(
        balance_sheet=[
            Figure(label="Zásoby", value=40.0),
            Figure(label="Krátkodobé pohledávky", value=60.0),
            Figure(label="Peněžní prostředky", value=25.0),
        ],
        income_statement=[Figure(label="Nákladové úroky", value=12.0)],
        cash_flow=[
            Figure(label="Čistý peněžní tok z provozní činnosti", value=180.0)
        ],
    )
    n = normalize(fs)
    assert n.inventories == 40.0
    assert n.receivables == 60.0
    assert n.cash == 25.0
    assert n.interest_expense == 12.0
    assert n.operating_cash_flow == 180.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: FAIL (`NormalizedFinancials` has no `operating_profit`; canonical/trap logic missing).

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/rejstrik/analysis/normalize.py` with:

```python
from pydantic import BaseModel

from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import Figure, FinancialStatement

# Per-field matching rules over normalized (accent-stripped, lowercased) labels.
#   prefix  — label starts with any of these
#   exact   — label equals any of these
#   any     — any substring appears in the label
#   exclude — if any appears, the label is rejected (checked first)
_FIELD_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "total_assets": {"any": ("aktiva celkem", "total assets")},
    "current_assets": {"any": ("obezna aktiva", "current assets")},
    "equity": {"any": ("vlastni kapital", "equity")},
    "current_liabilities": {"any": ("kratkodobe zavazky", "current liabilities")},
    "total_liabilities": {"any": ("cizi zdroje", "total liabilities")},
    "revenue": {
        "prefix": (
            "trzby z prodeje vyrobk",
            "trzby z prodeje sluzeb",
            "trzby z prodeje zbozi",
            "trzby za prodej vlastnich",
            "trzby za prodej zbozi",
        ),
        "exact": ("trzby", "vynosy", "revenue", "turnover"),
        "exclude": ("dlouhodob", "majetk"),
    },
    "operating_profit": {
        "any": ("provozni vysledek hospodareni", "operating profit")
    },
    "net_profit": {
        "any": (
            "vysledek hospodareni za ucetni obdobi",
            "zisk za ucetni obdobi",
            "net profit",
            "net income",
        )
    },
    "interest_expense": {"any": ("nakladove uroky", "interest expense")},
    "cash": {"any": ("penezni prostredky", "cash and cash equivalents")},
    "inventories": {"any": ("zasoby", "inventories")},
    "receivables": {"any": ("pohledavky", "receivables")},
    "operating_cash_flow": {
        "any": (
            "penezni tok z provozni",
            "cash flow from operat",
        )
    },
}

_FIELDS: tuple[str, ...] = (
    "total_assets",
    "current_assets",
    "equity",
    "total_liabilities",
    "current_liabilities",
    "revenue",
    "operating_profit",
    "net_profit",
    "interest_expense",
    "cash",
    "inventories",
    "receivables",
    "operating_cash_flow",
)


class NormalizedFinancials(BaseModel):
    period_year: int | None = None
    total_assets: float | None = None
    equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    total_liabilities: float | None = None
    revenue: float | None = None
    operating_profit: float | None = None
    net_profit: float | None = None
    interest_expense: float | None = None
    cash: float | None = None
    inventories: float | None = None
    receivables: float | None = None
    operating_cash_flow: float | None = None


def _rule_matches(rule: dict[str, tuple[str, ...]], label: str) -> bool:
    if any(token in label for token in rule.get("exclude", ())):
        return False
    if any(label.startswith(prefix) for prefix in rule.get("prefix", ())):
        return True
    if label in rule.get("exact", ()):
        return True
    return any(token in label for token in rule.get("any", ()))


def _keyword_value(field: str, figures: list[Figure]) -> float | None:
    rule = _FIELD_RULES[field]
    for figure in figures:
        if figure.value is None:
            continue
        if _rule_matches(rule, normalize_label(figure.label)):
            return figure.value
    return None


def normalize(statement: FinancialStatement) -> NormalizedFinancials:
    figures: list[Figure] = [
        *statement.balance_sheet,
        *statement.income_statement,
        *statement.cash_flow,
    ]
    canonical = statement.canonical
    values: dict[str, float] = {}
    for field in _FIELDS:
        if canonical is not None:
            fig = getattr(canonical, field)
            if fig is not None and fig.value is not None:
                values[field] = fig.value
                continue
        value = _keyword_value(field, figures)
        if value is not None:
            values[field] = value
    return NormalizedFinancials(period_year=statement.period_year, **values)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_normalize.py -q`
Expected: PASS (including the pre-existing normalize tests).

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/normalize.py tests/analysis/test_normalize.py
git commit -m "feat(analysis): canonical-first normalize with hardened keyword fallback"
```

---

## Task 3: Ratio expansion

**Files:**
- Modify: `src/rejstrik/analysis/ratios.py`
- Test: `tests/analysis/test_ratios.py`

**Interfaces:**
- Consumes: `NormalizedFinancials` (Task 2 fields).
- Produces: `Ratios` extended with `quick_ratio, return_on_assets, asset_turnover, interest_coverage, operating_margin, ocf_to_liabilities` (all `float | None`); `compute_ratios` fills them. Existing five ratios unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_ratios.py`:

```python
def test_computes_new_ratios():
    n = NormalizedFinancials(
        total_assets=1000.0,
        equity=400.0,
        current_assets=600.0,
        current_liabilities=300.0,
        total_liabilities=600.0,
        revenue=2000.0,
        operating_profit=100.0,
        net_profit=150.0,
        interest_expense=20.0,
        inventories=150.0,
        operating_cash_flow=180.0,
    )
    r = compute_ratios(n)
    assert r.quick_ratio == 1.5  # (600 - 150) / 300
    assert r.return_on_assets == 0.15  # 150 / 1000
    assert r.asset_turnover == 2.0  # 2000 / 1000
    assert r.interest_coverage == 5.0  # 100 / 20
    assert r.operating_margin == 0.05  # 100 / 2000
    assert r.ocf_to_liabilities == 0.3  # 180 / 600


def test_new_ratios_none_when_inputs_missing():
    r = compute_ratios(NormalizedFinancials(current_assets=600.0))
    assert r.quick_ratio is None  # inventories missing
    assert r.interest_coverage is None
    assert r.ocf_to_liabilities is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_ratios.py -q`
Expected: FAIL (`Ratios` has no `quick_ratio`).

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/rejstrik/analysis/ratios.py` with:

```python
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials


class Ratios(BaseModel):
    current_ratio: float | None = None
    equity_ratio: float | None = None
    debt_to_equity: float | None = None
    net_margin: float | None = None
    return_on_equity: float | None = None
    quick_ratio: float | None = None
    return_on_assets: float | None = None
    asset_turnover: float | None = None
    interest_coverage: float | None = None
    operating_margin: float | None = None
    ocf_to_liabilities: float | None = None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_ratios(financials: NormalizedFinancials) -> Ratios:
    if financials.current_assets is not None and financials.inventories is not None:
        quick_num: float | None = financials.current_assets - financials.inventories
    else:
        quick_num = None
    return Ratios(
        current_ratio=_div(
            financials.current_assets,
            financials.current_liabilities,
        ),
        equity_ratio=_div(financials.equity, financials.total_assets),
        debt_to_equity=_div(financials.total_liabilities, financials.equity),
        net_margin=_div(financials.net_profit, financials.revenue),
        return_on_equity=_div(financials.net_profit, financials.equity),
        quick_ratio=_div(quick_num, financials.current_liabilities),
        return_on_assets=_div(financials.net_profit, financials.total_assets),
        asset_turnover=_div(financials.revenue, financials.total_assets),
        interest_coverage=_div(
            financials.operating_profit, financials.interest_expense
        ),
        operating_margin=_div(financials.operating_profit, financials.revenue),
        ocf_to_liabilities=_div(
            financials.operating_cash_flow, financials.total_liabilities
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_ratios.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/ratios.py tests/analysis/test_ratios.py
git commit -m "feat(analysis): add six None-safe ratios"
```

---

## Task 4: IN05 distress index

**Files:**
- Create: `src/rejstrik/analysis/in05.py`
- Test: `tests/analysis/test_in05.py`

**Interfaces:**
- Consumes: `NormalizedFinancials`.
- Produces: `IN05Result(value: float | None, zone: Literal["distress","grey","value_creating"] | None, missing_inputs: list[str])` and `compute_in05(financials) -> IN05Result`. Computes only when all seven required inputs are present and the three balance denominators are non-zero; otherwise returns a miss-list and `value=None`.

- [ ] **Step 1: Write the failing test**

Create `tests/analysis/test_in05.py`:

```python
import pytest

from rejstrik.analysis.in05 import IN05Result, compute_in05
from rejstrik.analysis.normalize import NormalizedFinancials


def _full(**overrides) -> NormalizedFinancials:
    base = dict(
        total_assets=1000.0,
        total_liabilities=500.0,
        operating_profit=100.0,
        interest_expense=20.0,
        revenue=2000.0,
        current_assets=600.0,
        current_liabilities=300.0,
    )
    base.update(overrides)
    return NormalizedFinancials(**base)


def test_in05_hand_computed_grey_zone():
    result = compute_in05(_full())
    # 0.13*2 + 0.04*5 + 3.97*0.1 + 0.21*2 + 0.09*2 = 1.457
    assert result.value == pytest.approx(1.457)
    assert result.zone == "grey"
    assert result.missing_inputs == []


def test_in05_ebit_interest_cap_pushes_value_creating():
    # EBIT/U = 100/1 = 100 -> capped at 9 -> 0.04*9 = 0.36
    result = compute_in05(_full(interest_expense=1.0))
    assert result.value == pytest.approx(1.617)
    assert result.zone == "value_creating"


def test_in05_zero_interest_uses_cap():
    result = compute_in05(_full(interest_expense=0.0))
    assert result.value == pytest.approx(1.617)


def test_in05_distress_zone():
    result = compute_in05(
        _full(operating_profit=-100.0, revenue=100.0, total_liabilities=2000.0)
    )
    assert result.value < 0.9
    assert result.zone == "distress"


def test_in05_missing_input_returns_miss_list():
    result = compute_in05(_full(interest_expense=None))
    assert isinstance(result, IN05Result)
    assert result.value is None
    assert result.zone is None
    assert "interest_expense" in result.missing_inputs


def test_in05_zero_denominator_reported():
    result = compute_in05(_full(total_assets=0.0))
    assert result.value is None
    assert "total_assets" in result.missing_inputs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_in05.py -q`
Expected: FAIL (`ModuleNotFoundError: rejstrik.analysis.in05`).

- [ ] **Step 3: Write minimal implementation**

Create `src/rejstrik/analysis/in05.py`:

```python
from typing import Literal

from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_EBIT_INTEREST_CAP = 9.0

_REQUIRED = (
    "total_assets",
    "total_liabilities",
    "operating_profit",
    "interest_expense",
    "revenue",
    "current_assets",
    "current_liabilities",
)

# Denominators that must be non-zero to form the required ratios.
_NONZERO_DENOMINATORS = ("total_assets", "total_liabilities", "current_liabilities")


class IN05Result(BaseModel):
    value: float | None = None
    zone: Literal["distress", "grey", "value_creating"] | None = None
    missing_inputs: list[str] = []


def compute_in05(financials: NormalizedFinancials) -> IN05Result:
    missing = [name for name in _REQUIRED if getattr(financials, name) is None]
    if missing:
        return IN05Result(missing_inputs=missing)

    a = financials.total_assets
    cz = financials.total_liabilities
    ebit = financials.operating_profit
    u = financials.interest_expense
    vyn = financials.revenue
    oa = financials.current_assets
    kz = financials.current_liabilities

    zero_denominators = [
        name for name in _NONZERO_DENOMINATORS if getattr(financials, name) == 0
    ]
    if zero_denominators:
        return IN05Result(missing_inputs=zero_denominators)

    ebit_interest = _EBIT_INTEREST_CAP if u == 0 else min(ebit / u, _EBIT_INTEREST_CAP)
    value = (
        0.13 * (a / cz)
        + 0.04 * ebit_interest
        + 3.97 * (ebit / a)
        + 0.21 * (vyn / a)
        + 0.09 * (oa / kz)
    )
    if value < 0.9:
        zone: Literal["distress", "grey", "value_creating"] = "distress"
    elif value > 1.6:
        zone = "value_creating"
    else:
        zone = "grey"
    return IN05Result(value=value, zone=zone)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_in05.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/in05.py tests/analysis/test_in05.py
git commit -m "feat(analysis): add IN05 distress index"
```

---

## Task 5: Full multi-year trend series with CAGR

**Files:**
- Modify: `src/rejstrik/analysis/trends.py`
- Test: `tests/analysis/test_trends.py`

**Interfaces:**
- Consumes: `NormalizedFinancials`.
- Produces: `TrendSeriesItem(metric: str, years: list[int | None], values: list[float | None], cagr: float | None)` and `compute_trend_series(chronological: list[NormalizedFinancials]) -> list[TrendSeriesItem]` where input is **oldest-first**. CAGR is computed only for ≥3 data points with positive first and last values. `TrendItem` and `compute_trends` are unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_trends.py`:

```python
from rejstrik.analysis.trends import TrendSeriesItem, compute_trend_series


def _n(year, revenue):
    return NormalizedFinancials(period_year=year, revenue=revenue)


def test_series_lists_years_and_values_oldest_first():
    series = compute_trend_series([_n(2021, 100.0), _n(2022, 120.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert isinstance(revenue, TrendSeriesItem)
    assert revenue.years == [2021, 2022, 2023]
    assert revenue.values == [100.0, 120.0, 144.0]


def test_series_cagr_three_years_positive_endpoints():
    series = compute_trend_series([_n(2021, 100.0), _n(2022, 120.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr == pytest.approx(0.2)  # (144/100)**(1/2) - 1


def test_series_cagr_none_for_two_years():
    series = compute_trend_series([_n(2022, 100.0), _n(2023, 144.0)])
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None


def test_series_cagr_none_for_nonpositive_endpoint():
    series = compute_trend_series(
        [_n(2021, -10.0), _n(2022, 50.0), _n(2023, 100.0)]
    )
    revenue = next(s for s in series if s.metric == "revenue")
    assert revenue.cagr is None
```

Add `import pytest` at the top of `tests/analysis/test_trends.py` if not already present.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_trends.py -q`
Expected: FAIL (`ImportError: TrendSeriesItem`).

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/rejstrik/analysis/trends.py` with:

```python
from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials

_METRICS = ("revenue", "net_profit", "total_assets", "equity")


class TrendItem(BaseModel):
    metric: str
    current: float | None = None
    prior: float | None = None
    pct_change: float | None = None


class TrendSeriesItem(BaseModel):
    metric: str
    years: list[int | None] = []
    values: list[float | None] = []
    cagr: float | None = None


def compute_trends(
    current: NormalizedFinancials,
    prior: NormalizedFinancials,
) -> list[TrendItem]:
    items: list[TrendItem] = []
    for metric in _METRICS:
        current_value = getattr(current, metric)
        prior_value = getattr(prior, metric)
        pct_change = None
        if current_value is not None and prior_value is not None and prior_value != 0:
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


def _cagr(values: list[float | None]) -> float | None:
    if len(values) < 3:
        return None
    start, end = values[0], values[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    periods = len(values) - 1
    return (end / start) ** (1 / periods) - 1


def compute_trend_series(
    chronological: list[NormalizedFinancials],
) -> list[TrendSeriesItem]:
    """Full year-by-year series per metric. Input is oldest-first."""
    items: list[TrendSeriesItem] = []
    for metric in _METRICS:
        values = [getattr(n, metric) for n in chronological]
        items.append(
            TrendSeriesItem(
                metric=metric,
                years=[n.period_year for n in chronological],
                values=values,
                cagr=_cagr(values),
            )
        )
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_trends.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/trends.py tests/analysis/test_trends.py
git commit -m "feat(analysis): add multi-year trend series with CAGR"
```

---

## Task 6: Red-flag additions

**Files:**
- Modify: `src/rejstrik/analysis/redflags.py`
- Test: `tests/analysis/test_redflags.py`

**Interfaces:**
- Consumes: `NormalizedFinancials`, `Ratios`, `IN05Result` (Task 4).
- Produces: `detect_red_flags(..., in05: IN05Result | None = None)` gains flags `low_interest_coverage` (critical, `ratios.interest_coverage < 1`), `negative_operating_cash_flow` (warning, `operating_cash_flow < 0` **and** `net_profit > 0`), `in05_distress` (critical), `in05_grey_zone` (info). New `in05` parameter is the last keyword argument; existing call sites keep working.

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_redflags.py`:

```python
def test_low_interest_coverage_is_critical():
    flags = detect_red_flags(
        NormalizedFinancials(), Ratios(interest_coverage=0.5), []
    )
    flag = next(f for f in flags if f.code == "low_interest_coverage")
    assert flag.severity == "critical"


def test_negative_ocf_with_positive_profit_is_warning():
    n = NormalizedFinancials(operating_cash_flow=-50.0, net_profit=30.0)
    flags = detect_red_flags(n, Ratios(), [])
    flag = next(f for f in flags if f.code == "negative_operating_cash_flow")
    assert flag.severity == "warning"


def test_negative_ocf_not_flagged_when_loss_making():
    n = NormalizedFinancials(operating_cash_flow=-50.0, net_profit=-30.0)
    flags = detect_red_flags(n, Ratios(), [])
    assert not any(f.code == "negative_operating_cash_flow" for f in flags)


def test_in05_zone_flags():
    from rejstrik.analysis.in05 import IN05Result

    distress = detect_red_flags(
        NormalizedFinancials(), Ratios(), [], in05=IN05Result(value=0.5, zone="distress")
    )
    assert any(
        f.code == "in05_distress" and f.severity == "critical" for f in distress
    )
    grey = detect_red_flags(
        NormalizedFinancials(), Ratios(), [], in05=IN05Result(value=1.2, zone="grey")
    )
    assert any(f.code == "in05_grey_zone" and f.severity == "info" for f in grey)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_redflags.py -q`
Expected: FAIL (`in05` is not a valid argument / new codes absent).

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/analysis/redflags.py`, add the import near the top (after the existing `from rejstrik.analysis.ratios import Ratios` line):

```python
from rejstrik.analysis.in05 import IN05Result
```

Change the `detect_red_flags` signature to add the `in05` keyword argument (append it as the last parameter):

```python
def detect_red_flags(
    financials: NormalizedFinancials,
    ratios: Ratios,
    notes: list[NoteItem],
    insolvent: bool | None = None,
    unreliable_vat: bool | None = None,
    public_money_ratio: float | None = None,
    in05: IN05Result | None = None,
) -> list[RedFlag]:
```

Immediately after the existing `high_leverage` block (the `if ratios.debt_to_equity is not None and ratios.debt_to_equity > 3:` block), insert:

```python
    if ratios.interest_coverage is not None and ratios.interest_coverage < 1:
        flags.append(
            RedFlag(
                code="low_interest_coverage",
                severity="critical",
                message=(
                    "Interest coverage below 1 - operating profit does not "
                    "cover interest expense."
                ),
            )
        )
    if (
        financials.operating_cash_flow is not None
        and financials.operating_cash_flow < 0
        and financials.net_profit is not None
        and financials.net_profit > 0
    ):
        flags.append(
            RedFlag(
                code="negative_operating_cash_flow",
                severity="warning",
                message=(
                    "Negative operating cash flow despite a reported profit - "
                    "possible earnings-quality issue."
                ),
            )
        )
    if in05 is not None and in05.zone == "distress":
        flags.append(
            RedFlag(
                code="in05_distress",
                severity="critical",
                message="IN05 index in the distress zone (below 0.9).",
            )
        )
    if in05 is not None and in05.zone == "grey":
        flags.append(
            RedFlag(
                code="in05_grey_zone",
                severity="info",
                message="IN05 index in the grey zone (0.9-1.6).",
            )
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_redflags.py -q`
Expected: PASS (existing red-flag tests still green).

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/redflags.py tests/analysis/test_redflags.py
git commit -m "feat(analysis): interest-coverage, negative-OCF, and IN05-zone red flags"
```

---

## Task 7: Wire IN05 and trend series into the report

**Files:**
- Modify: `src/rejstrik/analysis/report.py`
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service_analyze_statements.py`

**Interfaces:**
- Consumes: `compute_in05`, `compute_trend_series`, extended `detect_red_flags` (Tasks 4-6).
- Produces: `CompanyFinancialReport` gains `in05: IN05Result | None = None` and `trend_series: list[TrendSeriesItem] = []`. `analyze_statements` computes `in05` from the latest normalized statement, `trend_series` from all statements oldest-first, and passes `in05` to `detect_red_flags`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_service_analyze_statements.py`:

```python
def test_report_carries_in05_and_trend_series():
    def _rich(year, factor):
        return FinancialStatement(
            company_name="Budvar",
            ico="00514152",
            period_year=year,
            currency="CZK",
            balance_sheet=[
                Figure(label="Aktiva celkem", value=1000.0 * factor),
                Figure(label="Cizí zdroje", value=500.0 * factor),
                Figure(label="Oběžná aktiva", value=600.0 * factor),
                Figure(label="Krátkodobé závazky", value=300.0 * factor),
            ],
            income_statement=[
                Figure(label="Tržby z prodeje výrobků a služeb", value=2000.0 * factor),
                Figure(label="Provozní výsledek hospodaření", value=100.0 * factor),
                Figure(label="Nákladové úroky", value=20.0),
                Figure(label="Výsledek hospodaření za účetní období", value=90.0 * factor),
            ],
        )

    report = analyze_statements(
        [_rich(2021, 1.0), _rich(2022, 1.1), _rich(2023, 1.2)],
        insolvency_check=_no_insolvency,
        vat_check=_clean_vat,
    )
    assert report.in05 is not None
    assert report.in05.value is not None
    revenue_series = next(s for s in report.trend_series if s.metric == "revenue")
    assert revenue_series.years == [2021, 2022, 2023]
    assert revenue_series.cagr is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_analyze_statements.py -q`
Expected: FAIL (`CompanyFinancialReport` has no `in05` / `trend_series`).

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/analysis/report.py`, add imports below the existing analysis imports:

```python
from rejstrik.analysis.in05 import IN05Result
from rejstrik.analysis.trends import TrendItem, TrendSeriesItem
```

(Replace the existing `from rejstrik.analysis.trends import TrendItem` line with the combined import above.)

Add two fields to `CompanyFinancialReport` (after the existing `trends` field):

```python
    trend_series: list[TrendSeriesItem] = []
    in05: IN05Result | None = None
```

In `src/rejstrik/service.py`, update the analysis imports:

```python
from rejstrik.analysis.in05 import compute_in05
from rejstrik.analysis.trends import compute_trends, compute_trend_series
```

(Replace the existing `from rejstrik.analysis.trends import compute_trends` line.)

In `analyze_statements`, after `ratios = compute_ratios(normalized)`, add:

```python
    in05 = compute_in05(normalized)
```

Change the `detect_red_flags(...)` call to pass `in05=in05` as the final argument:

```python
    red_flags = detect_red_flags(
        normalized,
        ratios,
        current.notes,
        insolvent=insolvent,
        unreliable_vat=unreliable_vat,
        public_money_ratio=public_money_ratio,
        in05=in05,
    )
```

After the existing `trends = ...` line, add:

```python
    trend_series = compute_trend_series(list(reversed(normalized_all)))
```

Add both new fields to the returned `CompanyFinancialReport(...)` (alongside `trends=trends`):

```python
        trends=trends,
        trend_series=trend_series,
        in05=in05,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_service_analyze_statements.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/report.py src/rejstrik/service.py tests/test_service_analyze_statements.py
git commit -m "feat(service): wire IN05 and trend series into the report"
```

---

## Task 8: Indicative valuation module

**Files:**
- Create: `src/rejstrik/analysis/valuation.py`
- Test: `tests/analysis/test_valuation.py`

**Interfaces:**
- Consumes: `FinancialStatement`, `normalize` (Task 2).
- Produces:
  - `ValuationAssumptions(capitalization_rate=0.12, ebit_multiple=5.0, revenue_multiple=0.5, dispersion_threshold=0.5)`.
  - `ValuationEstimate(book_value, capitalized_earnings, ev_ebit_multiple, price_revenue_multiple, value_low, value_high, earnings_dispersion_flag, assumptions, caveats)`.
  - `estimate_valuation(statements: list[FinancialStatement], assumptions: ValuationAssumptions | None = None) -> ValuationEstimate`.

- [ ] **Step 1: Write the failing test**

Create `tests/analysis/test_valuation.py`:

```python
import pytest

from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    estimate_valuation,
)
from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement


def _stmt(year, *, equity=None, ebit=None, revenue=None, net_profit=None):
    return FinancialStatement(
        period_year=year,
        canonical=CanonicalFigures(
            equity=None if equity is None else Figure(label="Vlastní kapitál", value=equity),
            operating_profit=None
            if ebit is None
            else Figure(label="Provozní VH", value=ebit),
            revenue=None if revenue is None else Figure(label="Tržby", value=revenue),
            net_profit=None
            if net_profit is None
            else Figure(label="VH za účetní období", value=net_profit),
        ),
    )


def test_valuation_methods_hand_computed():
    result = estimate_valuation(
        [
            _stmt(2022, net_profit=80.0),
            _stmt(2023, equity=800.0, ebit=100.0, revenue=2000.0, net_profit=120.0),
        ]
    )
    assert isinstance(result, ValuationEstimate)
    assert result.book_value == 800.0
    assert result.capitalized_earnings == pytest.approx(833.333, rel=1e-3)  # 100/0.12
    assert result.ev_ebit_multiple == 500.0  # 5 * 100
    assert result.price_revenue_multiple == 1000.0  # 0.5 * 2000
    assert result.value_low == 500.0
    assert result.value_high == 1000.0
    assert result.earnings_dispersion_flag is False
    assert result.caveats[-1].endswith("not investment advice.")


def test_valuation_assumption_overrides():
    result = estimate_valuation(
        [_stmt(2023, ebit=100.0, revenue=2000.0, net_profit=120.0)],
        ValuationAssumptions(ebit_multiple=6.0, capitalization_rate=0.10),
    )
    assert result.ev_ebit_multiple == 600.0
    assert result.capitalized_earnings == pytest.approx(1200.0)  # 120/0.10


def test_valuation_flags_high_earnings_dispersion():
    result = estimate_valuation(
        [_stmt(2022, net_profit=10.0), _stmt(2023, net_profit=190.0)]
    )
    assert result.earnings_dispersion_flag is True


def test_valuation_missing_inputs_stay_none():
    result = estimate_valuation([_stmt(2023)])
    assert result.book_value is None
    assert result.capitalized_earnings is None
    assert result.value_low is None
    assert result.value_high is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_valuation.py -q`
Expected: FAIL (`ModuleNotFoundError: rejstrik.analysis.valuation`).

- [ ] **Step 3: Write minimal implementation**

Create `src/rejstrik/analysis/valuation.py`:

```python
from statistics import fmean, pstdev

from pydantic import BaseModel, Field

from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Multiples are generic defaults, not industry-calibrated.",
    "Minority and marketability discounts are not applied.",
    "This is an indicative estimate, not investment advice.",
]


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
) -> ValuationEstimate:
    assumptions = assumptions or ValuationAssumptions()
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

    methods = [
        v for v in (book_value, capitalized, ev, price) if v is not None
    ]
    value_low = min(methods) if methods else None
    value_high = max(methods) if methods else None

    return ValuationEstimate(
        book_value=book_value,
        capitalized_earnings=capitalized,
        ev_ebit_multiple=ev,
        price_revenue_multiple=price,
        value_low=value_low,
        value_high=value_high,
        earnings_dispersion_flag=dispersion_flag,
        assumptions=assumptions,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/analysis/test_valuation.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/valuation.py tests/analysis/test_valuation.py
git commit -m "feat(analysis): add indicative valuation module"
```

---

## Task 9: `estimate_valuation` MCP tool

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Modify: `tests/mcp/test_server.py`
- Modify: `tests/mcp/test_breadth_tools.py`
- Modify: `tests/mcp/test_card_tool.py`
- Test: `tests/mcp/test_valuation_tool.py`

**Interfaces:**
- Consumes: `estimate_valuation`, `ValuationAssumptions`, `ValuationEstimate` (Task 8).
- Produces: MCP tool `estimate_valuation(statements: list[FinancialStatement], assumptions: ValuationAssumptions | None = None) -> ValuationEstimate`, appended to `EXPOSED_TOOL_NAMES` (now 16). Keyless (no API key required).

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp/test_valuation_tool.py`:

```python
import asyncio

from rejstrik.documents.schema import CanonicalFigures, Figure, FinancialStatement
from rejstrik.mcp import server


def test_valuation_tool_exposed():
    assert "estimate_valuation" in server.EXPOSED_TOOL_NAMES
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "estimate_valuation" in names


def test_valuation_tool_runs_keyless():
    stmt = FinancialStatement(
        period_year=2023,
        canonical=CanonicalFigures(
            equity=Figure(label="Vlastní kapitál", value=800.0),
        ),
    )
    result = server.estimate_valuation([stmt])
    assert result.book_value == 800.0
    assert result.caveats[-1].endswith("not investment advice.")
```

Update `tests/mcp/test_server.py`: add `"estimate_valuation"` as the final entry of the `EXPOSED_TOOL_NAMES` list literal in `test_exposed_tool_names` (after `"read_filing_text"`).

Update `tests/mcp/test_breadth_tools.py`: change `assert len(server.EXPOSED_TOOL_NAMES) == 15` to `== 16`.

Update `tests/mcp/test_card_tool.py`: change `assert len(server.EXPOSED_TOOL_NAMES) == 15` to `== 16`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_valuation_tool.py tests/mcp/test_server.py tests/mcp/test_breadth_tools.py tests/mcp/test_card_tool.py -q`
Expected: FAIL (tool not registered; count assertions off).

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/mcp/server.py`, add the import near the other analysis imports:

```python
from rejstrik.analysis.valuation import (
    ValuationAssumptions,
    ValuationEstimate,
    estimate_valuation as _estimate_valuation,
)
```

Append `"estimate_valuation"` to the `EXPOSED_TOOL_NAMES` list (after `"read_filing_text"`).

Add the tool definition (place it after the `analyze_financials` tool):

```python
@mcp.tool(annotations=_ro("Estimate indicative valuation"))
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
) -> ValuationEstimate:
    """Indicative, deterministic valuation from statements YOU extracted:
    book value, capitalized earnings, and generic EV/EBIT and price/revenue
    multiples, with an overall range and the assumptions used. Amounts are
    thousands of CZK as filed. Multiples are generic, not industry-calibrated;
    book values are not market values. This is NOT investment advice."""
    return _estimate_valuation(statements, assumptions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_valuation_tool.py tests/mcp/test_server.py tests/mcp/test_breadth_tools.py tests/mcp/test_card_tool.py tests/mcp/test_annotations.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_valuation_tool.py tests/mcp/test_server.py tests/mcp/test_breadth_tools.py tests/mcp/test_card_tool.py
git commit -m "feat(mcp): add keyless estimate_valuation tool"
```

---

## Task 10: `analyze-company` prompt mentions canonical fields and valuation

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_prompts.py`

**Interfaces:**
- Consumes: the `FinancialStatement` JSON schema (now carries `canonical` with Czech line descriptions from Task 1) and the `estimate_valuation` tool (Task 9).
- Produces: the `analyze-company` prompt text steers the host to fill `canonical` and to call `estimate_valuation`.

- [ ] **Step 1: Write the failing test**

In `tests/mcp/test_prompts.py`, extend the needle tuple in `test_analyze_company_prompt_mentions_tools_and_schema` to also require:

```python
        "canonical",
        "Aktiva celkem",
        "estimate_valuation",
```

(Add these three strings to the existing `for needle in (...)` tuple.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_prompts.py -q`
Expected: FAIL (`estimate_valuation` not in the prompt text).

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/mcp/server.py`, in `analyze_company_prompt`, replace step 4's parenthetical guidance and add valuation guidance. Change the step-4 sentence to end with an instruction to populate `canonical`, and add a new step. Concretely, update the numbered list so it reads:

```python
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema (amounts in Czech statements are usually reported in thousands of CZK
   — keep them as printed and set currency to "CZK"; set period_year to the
   statement year; cite source_page for every figure). ALSO fill the `canonical`
   object: each of its fields' descriptions names the exact Czech statutory line
   that feeds it (e.g. total_assets ← "Aktiva celkem", net_profit ← "Výsledek
   hospodaření za účetní období") — this is what makes the analysis reliable:
{schema}
5. Call analyze_financials(statements=[...], ico=ico) with ALL extracted
   statements in one call to get ratios, red flags, the IN05 distress index,
   and year-over-year trends.
6. Optionally call estimate_valuation(statements=[...]) for an indicative
   valuation range (book value, capitalized earnings, generic multiples) — it
   is not investment advice.
7. If your client renders MCP UI resources, also call render_card(report).
8. Summarize: overall health, notable trends, every red flag with its
   severity, and page citations for key numbers."""
```

(The old steps 5-7 shift down to 5-8; keep the `{schema}` interpolation exactly where shown.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mcp/test_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_prompts.py
git commit -m "docs(mcp): steer analyze-company prompt to canonical fields and valuation"
```

---

## Task 11: Card renders IN05 and new-ratio blurbs

**Files:**
- Modify: `src/rejstrik/mcp/card.py`
- Test: `tests/mcp/test_card.py`

**Interfaces:**
- Consumes: `CompanyFinancialReport.in05` (Task 7), the new ratio names (Task 3).
- Produces: `render_report_card` and `render_report_markdown` show an IN05 section when `report.in05.value` is set, and carry plain-language blurbs for the six new ratios.

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_card.py`:

```python
from rejstrik.analysis.in05 import IN05Result
from rejstrik.mcp.card import render_report_markdown

IN05_REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.",
    ico="00006947",
    period_year=2023,
    currency="CZK",
    statement=FinancialStatement(),
    normalized=NormalizedFinancials(),
    ratios=Ratios(interest_coverage=4.0),
    in05=IN05Result(value=1.457, zone="grey"),
    source_filing_title="Ucetni zaverka 2023",
)


def test_card_shows_in05_section_html():
    html = render_report_card(IN05_REPORT)
    assert "IN05" in html
    assert "grey" in html


def test_card_shows_in05_section_markdown():
    md = render_report_markdown(IN05_REPORT)
    assert "IN05" in md
    assert "grey" in md


def test_card_new_ratio_has_blurb():
    html = render_report_card(IN05_REPORT)
    assert "interest" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card.py -q`
Expected: FAIL (no IN05 section rendered).

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/mcp/card.py`, extend the `_RATIO_BLURB` dict with the six new ratios:

```python
    "quick_ratio": "liquidity excluding inventories",
    "return_on_assets": "net profit per unit of assets",
    "asset_turnover": "revenue per unit of assets",
    "interest_coverage": "operating profit vs interest expense",
    "operating_margin": "operating profit per unit of revenue",
    "ocf_to_liabilities": "operating cash flow vs total liabilities",
```

In `render_report_card`, after the `ratio_rows = ...` assignment, add an IN05 block:

```python
    if report.in05 is not None and report.in05.value is not None:
        in05_html = (
            "<h2>IN05 distress index</h2>"
            f"<div class='pm'>IN05 = {_esc(round(report.in05.value, 2))} — "
            f"{_esc((report.in05.zone or '').replace('_', ' '))} zone.</div>"
        )
    else:
        in05_html = ""
```

Insert `{in05_html}` into the returned HTML template, immediately after the ratios table (after the `<table>{ratio_rows}</table>` line and before `<h2>Red flags</h2>`):

```python
  <h2>Ratios</h2>
  <table>{ratio_rows}</table>
  {in05_html}
  <h2>Red flags</h2>
```

In `render_report_markdown`, after the ratios loop block (after the `lines.append("")` that follows the ratios `for` loop), add:

```python
    if report.in05 is not None and report.in05.value is not None:
        lines.append("### IN05 distress index")
        zone = (report.in05.zone or "").replace("_", " ")
        lines.append(f"- IN05 = {round(report.in05.value, 2)} — {zone} zone")
        lines.append("")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mcp/test_card.py tests/mcp/test_card_markdown.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/mcp/card.py tests/mcp/test_card.py
git commit -m "feat(mcp): render IN05 and new-ratio blurbs on the report card"
```

---

## Task 12: Version bump to v0.6.0 and docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/rejstrik/__init__.py`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `version = "0.6.0"` in `pyproject.toml` and `__version__ = "0.6.0"`; CHANGELOG and README document Stage D (IN05, ratios, trend series, `estimate_valuation`).

- [ ] **Step 1: Write the failing test**

In `tests/test_packaging.py`, rename and update the version test, and add a Stage-D doc test:

```python
def test_pyproject_bumped_to_v0_6_0():
    text = _PYPROJECT.read_text(encoding="utf-8")
    assert 'version = "0.6.0"' in text


def test_changelog_documents_v0_6_0():
    text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert "0.6.0" in text
    assert "estimate_valuation" in text


def test_readme_mentions_estimate_valuation():
    text = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    assert "estimate_valuation" in text
```

(Delete the old `test_pyproject_bumped_to_v0_5_0` function; keep `test_pyproject_declares_pypdf`, `test_changelog_documents_v0_5_0`, and `test_readme_mentions_read_filing_text` as-is — they still hold.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packaging.py -q`
Expected: FAIL (version still `0.5.0`; README/CHANGELOG lack `estimate_valuation`).

- [ ] **Step 3: Write minimal implementation**

In `pyproject.toml`, change `version = "0.5.0"` to `version = "0.6.0"`.

In `src/rejstrik/__init__.py`, change `__version__ = "0.4.0"` to `__version__ = "0.6.0"`.

Prepend a new section to `CHANGELOG.md` (above the `## 0.5.0` heading):

```markdown
## 0.6.0 — Stage D: analysis depth + indicative valuation

- Extraction now fills a `canonical` object on each `FinancialStatement`
  (total assets, equity, revenue, operating/net profit, interest expense,
  cash, inventories, receivables, operating cash flow) keyed to the exact
  Czech statutory lines. `normalize()` prefers these canonical figures and
  falls back to a hardened keyword matcher that no longer mistakes asset-sale
  revenue for turnover or the operating result for the net result.
- Six new ratios: quick ratio, return on assets, asset turnover, interest
  coverage, operating margin, and operating-cash-flow-to-liabilities.
- New `IN05` distress index (Neumaier & Neumaierová) with distress / grey /
  value-creating zones, feeding `in05_distress` (critical) and `in05_grey_zone`
  (info) red flags. New red flags: `low_interest_coverage` (critical) and
  `negative_operating_cash_flow` with a reported profit (warning).
- Reports now carry a full multi-year `trend_series` (year-by-year values plus
  CAGR when ≥3 years with positive endpoints), in addition to the latest-vs-prior
  `trends`.
- New keyless tool `estimate_valuation(statements, assumptions=None)`: book
  value, capitalized earnings, and generic EV/EBIT and price/revenue multiples,
  with an overall range, the assumptions used, and a caveats list. Indicative
  only — not investment advice.

```

In `README.md`, add a row to the tools table (the section with `| \`analyze_financials\` | ... |` rows):

```markdown
| `estimate_valuation` | Your extracted figures in → indicative valuation range (book value, capitalized earnings, multiples), no LLM. Not investment advice |
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_packaging.py -q`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/rejstrik/__init__.py CHANGELOG.md README.md tests/test_packaging.py
git commit -m "chore: release v0.6.0 (Stage D)"
```

---

## Self-review notes (spec coverage)

- **Canonical fields** → Task 1 (schema) + Task 2 (canonical-first normalize).
- **Keyword-fallback trap fixes** (asset-sale revenue; operating vs net result; "za ucetni obdobi" gate) → Task 2.
- **Ratio expansion** (quick, ROA, turnover, interest coverage, operating margin, OCF/liabilities) → Task 3.
- **IN05** (formula, EBIT/U cap, zones, miss-list, red flags) → Task 4 (index) + Task 6 (flags).
- **Full trend series + CAGR edge cases** → Task 5, wired in Task 7.
- **`estimate_valuation`** (three methods, assumptions, range, caveats, disclaimer, keyless tool) → Task 8 (module) + Task 9 (tool).
- **Red-flag additions** (interest coverage < 1; negative OCF with positive profit; IN05 zones) → Task 6.
- **Prompt mentions canonical + Czech line names** → Task 1 (schema descriptions) + Task 10 (prompt text).
- **Card/prompts consume new analysis** → Task 10 (prompt) + Task 11 (card IN05 + ratio blurbs).
- **Ships as v0.6.0** → Task 12.
