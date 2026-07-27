# Valuation: single adjusted-multiple method — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `estimate_valuation`'s five-method min/max range with one
point estimate: a sourced Damodaran Europe sector multiple adjusted by named
factors, with an explicit confidence label.

**Architecture:** A new pure module computes the adjustment chain
(`base × Π factors`, clamped to 3–18×). `valuation.py` gains EBITDA
normalization, then is rewritten to pick one primary method — EV/EBITDA for
going concerns, net assets as fallback — and report a point estimate plus a
confidence band. The MCP tool derives classification confidence from where
the industry key came from. No server-side LLM; classification stays with
the caller or CZ-NACE.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, ruff.

## Global Constraints

- Design authority: `docs/superpowers/specs/2026-07-27-valuation-adjusted-multiple-design.md`.
- Tests are offline and key-free. Never call the network in a test.
- TDD: failing test → minimal implementation → green → commit.
- Before every commit run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
- Adjustment factor values are ported verbatim from
  `~/projects/obchodni-rejstrik-ai/apps/api/services/multiple_adjustments.py`.
  Do not re-derive or "improve" them; they are calibrated against the
  identical Damodaran Europe base table this repo vendors.
- Money values are in thousands of CZK throughout.
- Use the project venv: `.venv/bin/python`, `.venv/bin/pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/rejstrik/analysis/multiple_adjustments.py` | **new** — factor functions + `resolve_adjusted_multiple`. Pure, no I/O. |
| `src/rejstrik/analysis/valuation.py` | **rewrite** — EBITDA normalization, method selection, result shape. |
| `src/rejstrik/mcp/server.py` | **modify** — tool docstring + classification-confidence source. |
| `tests/analysis/test_multiple_adjustments.py` | **new** — factor boundaries, clamps. |
| `tests/analysis/test_valuation.py` | **rewrite** — method selection, bands, fallbacks. |
| `tests/mcp/test_valuation_tool.py` | **modify** — confidence by key source. |

---

### Task 1: Adjustment factor module

**Files:**
- Create: `src/rejstrik/analysis/multiple_adjustments.py`
- Test: `tests/analysis/test_multiple_adjustments.py`

**Interfaces:**
- Consumes: `IndustryMultiple` from `rejstrik.analysis.industry_multiples`.
- Produces: `AdjustedMultiple` dataclass with fields `base_multiple: float`,
  `final_multiple: float`, `factors: dict[str, float]`, `industry_key: str`,
  `source_industry: str`, `source: str`, `source_url: str`, `as_of: str`,
  `classification_confidence: str`. Plus
  `resolve_adjusted_multiple(base, classification_confidence, *, revenue,
  ebitda, net_profit, operating_cash_flow, revenue_growth) -> AdjustedMultiple`.

- [ ] **Step 1: Write the failing tests**

Create `tests/analysis/test_multiple_adjustments.py`:

```python
import pytest

from rejstrik.analysis.industry_multiples import get_industry_multiple
from rejstrik.analysis.multiple_adjustments import (
    AdjustedMultiple,
    cash_conversion_factor,
    data_confidence_factor,
    growth_factor,
    profitability_factor,
    resolve_adjusted_multiple,
)


@pytest.mark.parametrize(
    "revenue, ebitda, net_profit, expected",
    [
        (1000.0, 200.0, 100.0, 1.10),   # EBITDA margin .20 >= .17
        (1000.0, 50.0, 40.0, 0.85),     # EBITDA margin .05 < .08
        (1000.0, 120.0, 100.0, 1.00),   # between thresholds
        (1000.0, 200.0, 20.0, 0.90),    # net margin .02 < .03 caps 1.10 -> .90
        (1000.0, 200.0, 40.0, 0.95),    # net margin .04 < .05 caps 1.10 -> .95
        (None, 200.0, 100.0, 0.95),     # no revenue
        (0.0, 200.0, 100.0, 0.95),      # zero revenue
    ],
)
def test_profitability_factor(revenue, ebitda, net_profit, expected):
    assert profitability_factor(revenue, ebitda, net_profit) == expected


@pytest.mark.parametrize(
    "growth, expected",
    [(0.15, 1.12), (0.10, 1.05), (0.03, 1.00), (0.0, 1.00), (-0.05, 0.82), (None, 0.95)],
)
def test_growth_factor(growth, expected):
    assert growth_factor(growth) == expected


@pytest.mark.parametrize(
    "ebitda, ocf, expected",
    [
        (100.0, 90.0, 1.00),
        (100.0, 60.0, 0.95),
        (100.0, 30.0, 0.90),
        (100.0, 10.0, 0.82),
        (100.0, -5.0, 0.75),
        (None, 50.0, 0.95),
        (-10.0, 50.0, 0.95),
        (100.0, None, 0.95),
    ],
)
def test_cash_conversion_factor(ebitda, ocf, expected):
    assert cash_conversion_factor(ebitda, ocf) == expected


@pytest.mark.parametrize(
    "confidence, expected",
    [("high", 1.00), ("medium", 0.95), ("low", 0.85), ("nonsense", 0.85)],
)
def test_data_confidence_factor(confidence, expected):
    assert data_confidence_factor(confidence) == expected


def test_robe_chain_matches_spec():
    """ROBE lighting 2023, agent-classified as electrical_equipment."""
    base = get_industry_multiple("electrical_equipment")
    adjusted = resolve_adjusted_multiple(
        base,
        "high",
        revenue=3_886_882.0,
        ebitda=965_188.0,
        net_profit=752_222.0,
        operating_cash_flow=362_734.0,
        revenue_growth=None,
    )
    assert isinstance(adjusted, AdjustedMultiple)
    assert adjusted.base_multiple == pytest.approx(18.9445, rel=1e-4)
    assert adjusted.final_multiple == 14.05
    assert adjusted.factors == {
        "country": 0.83,
        "private_liquidity": 0.95,
        "size": 1.00,
        "profitability": 1.10,
        "growth": 0.95,
        "cash_conversion": 0.90,
        "quality": 1.00,
        "data_confidence": 1.00,
    }
    assert adjusted.source_industry == "Electrical Equipment"
    assert adjusted.classification_confidence == "high"


def test_multiple_clamped_to_ceiling():
    base = get_industry_multiple("electrical_equipment")  # 18.94x
    adjusted = resolve_adjusted_multiple(
        base,
        "high",
        revenue=1000.0,
        ebitda=250.0,          # margin .25 -> 1.10
        net_profit=200.0,
        operating_cash_flow=225.0,  # ocf/ebitda .9 -> 1.00
        revenue_growth=0.20,        # -> 1.12
    )
    assert adjusted.final_multiple == 18.0


def test_multiple_clamped_to_floor():
    base = get_industry_multiple("telecom_services")  # ~7.19x
    adjusted = resolve_adjusted_multiple(
        base,
        "low",
        revenue=1000.0,
        ebitda=50.0,            # margin .05 -> 0.85
        net_profit=10.0,
        operating_cash_flow=-5.0,  # -> 0.75
        revenue_growth=-0.10,      # -> 0.82
    )
    assert adjusted.final_multiple == 3.0


def test_provenance_carried_from_base():
    base = get_industry_multiple("machinery")
    adjusted = resolve_adjusted_multiple(
        base, "medium", revenue=1000.0, ebitda=200.0,
        net_profit=100.0, operating_cash_flow=180.0, revenue_growth=0.05,
    )
    assert adjusted.industry_key == "machinery"
    assert adjusted.source_url == base.source_url
    assert adjusted.as_of == base.as_of
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_multiple_adjustments.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.analysis.multiple_adjustments'`

- [ ] **Step 3: Write the implementation**

Create `src/rejstrik/analysis/multiple_adjustments.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from rejstrik.analysis.industry_multiples import IndustryMultiple

# Ported verbatim from obchodni-rejstrik-ai's multiple_adjustments.py, which
# calibrates them against the identical Damodaran Europe base table vendored
# in data/industry_multiples.json. The base is a *listed European* multiple;
# these factors carry it to a Czech private SME.
COUNTRY_FACTOR = 0.83
PRIVATE_LIQUIDITY_FACTOR = 0.95
SIZE_FACTOR = 1.00
QUALITY_FACTOR = 1.00

MULTIPLE_FLOOR = 3.0
MULTIPLE_CEILING = 18.0


@dataclass(frozen=True)
class AdjustedMultiple:
    base_multiple: float
    final_multiple: float
    factors: dict[str, float]
    industry_key: str
    source_industry: str
    source: str
    source_url: str
    as_of: str
    classification_confidence: str


def profitability_factor(
    revenue: float | None, ebitda: float | None, net_profit: float | None
) -> float:
    if not revenue or revenue <= 0:
        return 0.95
    ebitda_margin = (ebitda or 0.0) / revenue
    net_margin = (net_profit or 0.0) / revenue
    factor = 1.0
    if ebitda_margin >= 0.17:
        factor = 1.10
    elif ebitda_margin < 0.08:
        factor = 0.85
    if net_margin < 0.03:
        factor = min(factor, 0.90)
    elif net_margin < 0.05:
        factor = min(factor, 0.95)
    return factor


def growth_factor(revenue_growth: float | None) -> float:
    if revenue_growth is None:
        return 0.95
    if revenue_growth > 0.12:
        return 1.12
    if revenue_growth > 0.07:
        return 1.05
    if revenue_growth >= 0:
        return 1.00
    return 0.82


def cash_conversion_factor(
    ebitda: float | None, operating_cash_flow: float | None
) -> float:
    if ebitda is None or ebitda <= 0 or operating_cash_flow is None:
        return 0.95
    ratio = operating_cash_flow / ebitda
    if ratio < 0:
        return 0.75
    if ratio < 0.20:
        return 0.82
    if ratio < 0.50:
        return 0.90
    if ratio < 0.80:
        return 0.95
    return 1.00


def data_confidence_factor(classification_confidence: str) -> float:
    if classification_confidence == "high":
        return 1.00
    if classification_confidence == "medium":
        return 0.95
    return 0.85


def resolve_adjusted_multiple(
    base: IndustryMultiple,
    classification_confidence: str,
    *,
    revenue: float | None,
    ebitda: float | None,
    net_profit: float | None,
    operating_cash_flow: float | None,
    revenue_growth: float | None,
) -> AdjustedMultiple:
    factors = {
        "country": COUNTRY_FACTOR,
        "private_liquidity": PRIVATE_LIQUIDITY_FACTOR,
        "size": SIZE_FACTOR,
        "profitability": profitability_factor(revenue, ebitda, net_profit),
        "growth": growth_factor(revenue_growth),
        "cash_conversion": cash_conversion_factor(ebitda, operating_cash_flow),
        "quality": QUALITY_FACTOR,
        "data_confidence": data_confidence_factor(classification_confidence),
    }
    final = base.ev_ebitda
    for value in factors.values():
        final *= value
    final = max(MULTIPLE_FLOOR, min(MULTIPLE_CEILING, final))
    return AdjustedMultiple(
        base_multiple=base.ev_ebitda,
        final_multiple=round(final, 2),
        factors=factors,
        industry_key=base.industry_key,
        source_industry=base.source_industry,
        source=base.source,
        source_url=base.source_url,
        as_of=base.as_of,
        classification_confidence=classification_confidence,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/analysis/test_multiple_adjustments.py -q`
Expected: PASS (all parametrized cases green)

- [ ] **Step 5: Run gates and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add src/rejstrik/analysis/multiple_adjustments.py tests/analysis/test_multiple_adjustments.py
git commit -m "feat(valuation): add sector-multiple adjustment chain

Ports the calibrated factor chain from obchodni-rejstrik-ai: a listed
European Damodaran multiple is carried to a Czech private SME via named
country, liquidity, profitability, growth and cash-conversion factors,
clamped to 3-18x.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: EBITDA normalization helpers

**Files:**
- Modify: `src/rejstrik/analysis/valuation.py` (add helpers; leave `estimate_valuation` untouched this task)
- Test: `tests/analysis/test_valuation.py` (append)

**Interfaces:**
- Produces: `normalize_ebitda(series: list[float]) -> tuple[float | None, str | None]`
  returning `(value, basis)` where basis is `"recency-weighted"` or
  `"latest-year"`; and `ebitda_stable(series: list[float]) -> bool`.
- The series is ordered **newest first**.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analysis/test_valuation.py`:

```python
from rejstrik.analysis.valuation import ebitda_stable, normalize_ebitda


def test_normalize_ebitda_recency_weighted():
    # newest first: (2*300 + 150) / 3
    assert normalize_ebitda([300.0, 150.0]) == (250.0, "recency-weighted")


def test_normalize_ebitda_single_year():
    assert normalize_ebitda([300.0]) == (300.0, "latest-year")


def test_normalize_ebitda_skips_non_positive_years():
    assert normalize_ebitda([300.0, -20.0, 150.0]) == (250.0, "recency-weighted")


def test_normalize_ebitda_all_negative_returns_none():
    assert normalize_ebitda([-50.0, -20.0]) == (None, None)


def test_normalize_ebitda_empty_returns_none():
    assert normalize_ebitda([]) == (None, None)


def test_ebitda_stable_true_for_flat_series():
    assert ebitda_stable([100.0, 100.0]) is True


def test_ebitda_stable_false_for_volatile_series():
    assert ebitda_stable([300.0, 50.0]) is False


def test_ebitda_stable_false_for_single_year():
    assert ebitda_stable([100.0]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_valuation.py -k "normalize_ebitda or ebitda_stable" -q`
Expected: FAIL — `ImportError: cannot import name 'normalize_ebitda'`

- [ ] **Step 3: Write the implementation**

Add to `src/rejstrik/analysis/valuation.py` (module level, above `estimate_valuation`):

```python
def normalize_ebitda(series: list[float]) -> tuple[float | None, str | None]:
    """Recency-weighted representative EBITDA over positive years.

    `series` is ordered newest first. Damps a single outlier year without
    discarding history."""
    positives = [v for v in (series or []) if isinstance(v, (int, float)) and v > 0]
    if not positives:
        return None, None
    if len(positives) >= 2:
        latest, prior = positives[0], positives[1]
        return (2 * latest + prior) / 3, "recency-weighted"
    return positives[0], "latest-year"


def ebitda_stable(series: list[float]) -> bool:
    """True when positive EBITDA years vary by less than 35% of their mean."""
    positives = [v for v in (series or []) if isinstance(v, (int, float)) and v > 0]
    if len(positives) < 2:
        return False
    mean = sum(positives) / len(positives)
    if mean <= 0:
        return False
    variance = sum((v - mean) ** 2 for v in positives) / len(positives)
    return (variance**0.5) / mean < 0.35
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/analysis/test_valuation.py -k "normalize_ebitda or ebitda_stable" -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Run gates and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add src/rejstrik/analysis/valuation.py tests/analysis/test_valuation.py
git commit -m "feat(valuation): add recency-weighted EBITDA normalization

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Rewrite `estimate_valuation` to a single adjusted-multiple method

This is the breaking change. It removes `capitalized_earnings`,
`ev_ebit_multiple`, `price_revenue_multiple` and the three arbitrary
constants, and replaces the min/max range with a point estimate plus a
confidence band.

**Files:**
- Modify: `src/rejstrik/analysis/valuation.py`
- Test: `tests/analysis/test_valuation.py` (replace obsolete tests)

**Interfaces:**
- Consumes: `resolve_adjusted_multiple`, `AdjustedMultiple` (Task 1);
  `normalize_ebitda`, `ebitda_stable` (Task 2);
  `get_industry_multiple` from `rejstrik.analysis.industry_multiples`;
  `normalize` from `rejstrik.analysis.normalize` returning
  `NormalizedFinancials` (fields include `period_year`, `total_assets`,
  `equity`, `total_liabilities`, `revenue`, `operating_profit`,
  `net_profit`, `operating_cash_flow`, `depreciation_amortization`).
- Produces: `estimate_valuation(statements, assumptions=None,
  industry_key=None, industry_reason=None, classification_confidence=None)
  -> ValuationEstimate` with the new field set below.

- [ ] **Step 1: Write the failing tests**

Replace the whole body of `tests/analysis/test_valuation.py` that tests the
old five methods (the tests named `test_valuation_methods_hand_computed`,
`test_valuation_assumption_overrides`, `test_valuation_missing_inputs_stay_none`,
`test_industry_key_applies_ev_ebitda_when_da_present`,
`test_industry_key_without_da_does_not_apply_ebitda_multiple`,
`test_statements_only_output_unchanged_by_industry_feature`) with these.
Keep `test_valuation_flags_high_earnings_dispersion` and
`test_valuation_empty_statements_raises_valueerror` if they still hold; if
`earnings_dispersion_flag` is retained they do.

```python
import pytest

from rejstrik.analysis.valuation import ValuationAssumptions, estimate_valuation
from rejstrik.documents.schema import CanonicalFigures, FinancialStatement, Figure


def _fig(label, value):
    return Figure(label=label, value=value)


def _statement(
    year=2023,
    revenue=3_886_882.0,
    operating_profit=903_044.0,
    net_profit=752_222.0,
    da=62_144.0,
    ocf=362_734.0,
    total_assets=3_541_478.0,
    total_liabilities=499_199.0,
    equity=3_039_871.0,
):
    return FinancialStatement(
        company_name="ROBE lighting s.r.o.",
        ico="64088791",
        period_year=year,
        unit="thousands_czk",
        canonical=CanonicalFigures(
            total_assets=_fig("Aktiva celkem", total_assets),
            equity=_fig("Vlastní kapitál", equity),
            total_liabilities=_fig("Cizí zdroje", total_liabilities),
            revenue=_fig("Tržby", revenue),
            operating_profit=_fig("Provozní VH", operating_profit),
            net_profit=_fig("VH za účetní období", net_profit),
            operating_cash_flow=_fig("Provozní CF", ocf),
            depreciation_amortization=_fig("Odpisy", da),
        ),
    )


def test_robe_single_year_point_estimate():
    result = estimate_valuation(
        [_statement()],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    assert result.primary_method == "multiples"
    assert result.ebitda == pytest.approx(965_188.0)
    assert result.ebitda_basis == "latest-year"
    assert result.final_multiple == 14.05
    assert result.base_multiple == pytest.approx(18.9445, rel=1e-4)
    assert result.point_estimate == pytest.approx(965_188.0 * 14.05)
    # one filed year + specific sector -> medium -> +-25%
    assert result.confidence == "medium"
    assert result.value_low == pytest.approx(result.point_estimate * 0.75)
    assert result.value_high == pytest.approx(result.point_estimate * 1.25)


def test_two_stable_years_give_high_confidence_and_narrow_band():
    latest = _statement(year=2023)
    prior = _statement(
        year=2022, operating_profit=880_000.0, da=60_000.0, revenue=3_600_000.0
    )
    result = estimate_valuation(
        [latest, prior],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    assert result.ebitda_basis == "recency-weighted"
    assert result.confidence == "high"
    assert result.value_low == pytest.approx(result.point_estimate * 0.85)
    assert result.value_high == pytest.approx(result.point_estimate * 1.15)


def test_fallback_sector_lowers_confidence():
    result = estimate_valuation([_statement()])  # no industry key at all
    assert result.confidence == "low"
    assert result.value_low == pytest.approx(result.point_estimate * 0.60)
    assert result.value_high == pytest.approx(result.point_estimate * 1.40)


def test_negative_ebitda_falls_back_to_net_assets():
    result = estimate_valuation(
        [_statement(operating_profit=-500_000.0, da=1_000.0, net_profit=-400_000.0)],
        industry_key="electrical_equipment",
    )
    assert result.primary_method == "asset"
    assert result.point_estimate == pytest.approx(3_541_478.0 - 499_199.0)
    assert result.confidence == "low"
    assert result.value_low == pytest.approx(result.point_estimate * 0.85)
    assert result.value_high == pytest.approx(result.point_estimate * 1.15)
    assert result.final_multiple is None


def test_insufficient_data_when_nothing_usable():
    statement = FinancialStatement(
        company_name="Prázdná s.r.o.",
        ico="00000000",
        period_year=2023,
        unit="thousands_czk",
        canonical=CanonicalFigures(),
    )
    result = estimate_valuation([statement])
    assert result.primary_method == "insufficient_data"
    assert result.point_estimate is None
    assert result.value_low is None
    assert result.value_high is None


def test_explicit_multiple_override_wins():
    result = estimate_valuation(
        [_statement()],
        assumptions=ValuationAssumptions(ebitda_multiple=8.0),
        industry_key="electrical_equipment",
    )
    assert result.final_multiple == 8.0
    assert result.point_estimate == pytest.approx(965_188.0 * 8.0)


def test_sales_anchor_blends_down_an_inflated_ebitda_value():
    # anchor = revenue * 1.0 = 1000; ebitda value = 200 * 18 = 3600 > 1250
    # blended = 0.7 * 1000 + 0.3 * 3600 = 1780
    result = estimate_valuation(
        [
            _statement(
                revenue=1000.0,
                operating_profit=200.0,
                net_profit=180.0,
                da=0.0,
                ocf=190.0,
                total_assets=900.0,
                total_liabilities=100.0,
                equity=800.0,
            )
        ],
        assumptions=ValuationAssumptions(
            ebitda_multiple=18.0, ev_sales_anchor_multiple=1.0
        ),
        industry_key="electrical_equipment",
    )
    assert result.sales_anchor_applied is True
    assert result.point_estimate == pytest.approx(0.7 * 1000.0 + 0.3 * 3600.0)


def test_removed_legacy_fields_are_gone():
    result = estimate_valuation([_statement()], industry_key="machinery")
    for gone in ("capitalized_earnings", "ev_ebit_multiple", "price_revenue_multiple"):
        assert not hasattr(result, gone)


def test_caveats_keep_damodaran_provenance_and_disclaimer():
    result = estimate_valuation(
        [_statement()],
        industry_key="electrical_equipment",
        classification_confidence="high",
    )
    joined = " ".join(result.caveats)
    assert "Damodaran" in joined
    assert "Electrical Equipment" in joined
    assert "not investment advice" in joined.lower()


def test_empty_statements_raises_valueerror():
    with pytest.raises(ValueError):
        estimate_valuation([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/analysis/test_valuation.py -q`
Expected: FAIL — `TypeError: estimate_valuation() got an unexpected keyword argument 'classification_confidence'` and attribute errors on the new fields.

- [ ] **Step 3: Write the implementation**

Replace `src/rejstrik/analysis/valuation.py` below the imports (keep
`normalize_ebitda` / `ebitda_stable` from Task 2):

```python
from pydantic import BaseModel, Field

from rejstrik.analysis.industry_multiples import (
    FALLBACK_INDUSTRY_KEY,
    get_industry_multiple,
)
from rejstrik.analysis.multiple_adjustments import resolve_adjusted_multiple
from rejstrik.analysis.normalize import normalize
from rejstrik.documents.schema import FinancialStatement

_DISCLAIMER = "This is an indicative estimate, not investment advice."
_BASE_CAVEATS = [
    "Figures are in thousands of CZK as filed.",
    "Book values are not market values.",
    "Minority and marketability discounts are not applied.",
    _DISCLAIMER,
]
_CONFIDENCE_BAND = {"high": 0.15, "medium": 0.25, "low": 0.40}
_ASSET_BAND = 0.15


class ValuationAssumptions(BaseModel):
    """Caller overrides. Leave unset to use the sector-derived multiple."""

    ebitda_multiple: float | None = None
    ev_sales_anchor_multiple: float | None = None
    dispersion_threshold: float = 0.5


class ValuationEstimate(BaseModel):
    point_estimate: float | None = None
    value_low: float | None = None
    value_high: float | None = None
    primary_method: str = "insufficient_data"
    confidence: str = "low"
    book_value: float | None = None
    ebitda: float | None = None
    ebitda_basis: str | None = None
    base_multiple: float | None = None
    final_multiple: float | None = None
    adjustment_factors: dict[str, float] = Field(default_factory=dict)
    industry_key: str | None = None
    source_industry: str | None = None
    sales_anchor_applied: bool = False
    earnings_dispersion_flag: bool = False
    as_of_year: int | None = None
    assumptions: ValuationAssumptions
    caveats: list[str] = Field(default_factory=lambda: list(_BASE_CAVEATS))


def _ebitda_of(normalized) -> float | None:
    if normalized.operating_profit is None:
        return None
    return normalized.operating_profit + (normalized.depreciation_amortization or 0.0)


def _revenue_growth(ordered) -> float | None:
    if len(ordered) < 2:
        return None
    latest, prior = ordered[0].revenue, ordered[1].revenue
    if latest is None or prior is None or prior <= 0:
        return None
    return latest / prior - 1


def _band(point: float, confidence: str) -> tuple[float, float]:
    spread = _CONFIDENCE_BAND.get(confidence, 0.40)
    return point * (1 - spread), point * (1 + spread)


def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    industry_reason: str | None = None,
    classification_confidence: str | None = None,
) -> ValuationEstimate:
    """Indicative enterprise value from a sector multiple adjusted for a Czech
    private SME. One primary method: EV/EBITDA for going concerns, net assets
    as fallback."""
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

    series = [e for e in (_ebitda_of(n) for n in ordered) if e is not None]
    representative, basis = normalize_ebitda(series)

    net_assets = None
    if latest.total_assets is not None and latest.total_liabilities is not None:
        net_assets = max(0.0, latest.total_assets - latest.total_liabilities)

    earnings = [n.net_profit for n in normalized if n.net_profit is not None]
    dispersion_flag = False
    if len(earnings) > 1:
        mean = sum(earnings) / len(earnings)
        if mean != 0:
            variance = sum((e - mean) ** 2 for e in earnings) / len(earnings)
            dispersion_flag = (
                (variance**0.5) / abs(mean) > assumptions.dispersion_threshold
            )

    base = get_industry_multiple(industry_key)
    specific_sector = base.industry_key != FALLBACK_INDUSTRY_KEY
    confidence_in = classification_confidence or (
        "high" if industry_key else "low"
    )
    adjusted = resolve_adjusted_multiple(
        base,
        confidence_in,
        revenue=latest.revenue,
        ebitda=representative,
        net_profit=latest.net_profit,
        operating_cash_flow=latest.operating_cash_flow,
        revenue_growth=_revenue_growth(ordered),
    )

    caveats = list(_BASE_CAVEATS)
    caveats.insert(
        1,
        f"Base EV/EBITDA {adjusted.base_multiple:.2f}x for "
        f"'{adjusted.source_industry}' adjusted to {adjusted.final_multiple:.2f}x "
        f"for a Czech private company. Damodaran {base.region}, {base.firms} firms, "
        f"as of {base.as_of}. Source: {base.source_url}",
    )
    if industry_reason:
        caveats.insert(2, f"Industry chosen: {industry_reason}.")

    if representative is not None and representative > 0:
        multiple = (
            assumptions.ebitda_multiple
            if assumptions.ebitda_multiple is not None
            else adjusted.final_multiple
        )
        point = representative * multiple
        anchor_applied = False
        anchor_multiple = assumptions.ev_sales_anchor_multiple
        if anchor_multiple and latest.revenue and latest.revenue > 0:
            anchor = latest.revenue * anchor_multiple
            if point > anchor * 1.25:
                point = anchor * 0.70 + point * 0.30
                anchor_applied = True

        positives = [v for v in series if v > 0]
        if len(positives) >= 2:
            confidence = (
                "high" if (ebitda_stable(series) and specific_sector) else "medium"
            )
        else:
            confidence = "medium" if specific_sector else "low"

        low, high = _band(point, confidence)
        return ValuationEstimate(
            point_estimate=point,
            value_low=low,
            value_high=high,
            primary_method="multiples",
            confidence=confidence,
            book_value=book_value,
            ebitda=representative,
            ebitda_basis=basis,
            base_multiple=adjusted.base_multiple,
            final_multiple=multiple,
            adjustment_factors=adjusted.factors,
            industry_key=adjusted.industry_key,
            source_industry=adjusted.source_industry,
            sales_anchor_applied=anchor_applied,
            earnings_dispersion_flag=dispersion_flag,
            as_of_year=latest.period_year,
            assumptions=assumptions,
            caveats=caveats,
        )

    if net_assets is not None and net_assets > 0:
        return ValuationEstimate(
            point_estimate=net_assets,
            value_low=net_assets * (1 - _ASSET_BAND),
            value_high=net_assets * (1 + _ASSET_BAND),
            primary_method="asset",
            confidence="low",
            book_value=book_value,
            ebitda=representative,
            ebitda_basis=basis,
            earnings_dispersion_flag=dispersion_flag,
            as_of_year=latest.period_year,
            assumptions=assumptions,
            caveats=caveats,
        )

    return ValuationEstimate(
        primary_method="insufficient_data",
        confidence="low",
        book_value=book_value,
        as_of_year=latest.period_year,
        assumptions=assumptions,
        caveats=caveats,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/analysis/test_valuation.py -q`
Expected: PASS. Then run the full suite: `.venv/bin/python -m pytest -q` —
expect failures only in `tests/mcp/test_valuation_tool.py` (fixed in Task 4).

- [ ] **Step 5: Run gates and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/
git add src/rejstrik/analysis/valuation.py tests/analysis/test_valuation.py
git commit -m "feat(valuation)!: single adjusted-multiple estimate, not a five-method range

BREAKING CHANGE: ValuationEstimate drops capitalized_earnings,
ev_ebit_multiple and price_revenue_multiple, and ValuationAssumptions drops
capitalization_rate, ebit_multiple and revenue_multiple. Those three
constants (12%, 5x, 0.5x) were arbitrary and produced a 5x-wide range.

Output is now one point estimate from a sector multiple adjusted for a
Czech private SME, with a confidence-derived band and named factors.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire classification confidence through the MCP tool

**Files:**
- Modify: `src/rejstrik/mcp/server.py:335-361` (the `estimate_valuation` tool)
- Test: `tests/mcp/test_valuation_tool.py`

**Interfaces:**
- Consumes: `estimate_valuation(..., classification_confidence=...)` from Task 3.
- Produces: no new symbols; the tool's confidence mapping is
  agent key → `"high"`, NACE-derived → `"medium"`, neither → `"low"`.

- [ ] **Step 1: Write the failing tests**

Replace `test_explicit_assumptions_take_precedence_over_industry` (it asserts
`ev_ebit_multiple`, now gone) and add confidence tests in
`tests/mcp/test_valuation_tool.py`:

```python
def test_agent_supplied_key_is_high_confidence():
    result = estimate_valuation(
        [_statement()], industry_key="electrical_equipment"
    )
    assert result.adjustment_factors["data_confidence"] == 1.00
    assert result.industry_key == "electrical_equipment"


def test_nace_derived_key_is_medium_confidence(monkeypatch):
    monkeypatch.setattr(
        "rejstrik.mcp.server._find_company",
        lambda ico: SimpleNamespace(nace_codes=["471", "261", "952"]),
    )
    result = estimate_valuation([_statement()], ico="64088791")
    assert result.industry_key == "electronics_general"
    assert result.adjustment_factors["data_confidence"] == 0.95


def test_no_classification_is_low_confidence():
    result = estimate_valuation([_statement()])
    assert result.industry_key == "total_market_ex_financials"
    assert result.adjustment_factors["data_confidence"] == 0.85


def test_explicit_multiple_overrides_sector():
    result = estimate_valuation(
        [_statement()],
        assumptions=ValuationAssumptions(ebitda_multiple=6.0),
        industry_key="electrical_equipment",
    )
    assert result.final_multiple == 6.0
```

Add at the top of the file whatever imports these need — `SimpleNamespace`
from `types`, `ValuationAssumptions` from `rejstrik.analysis.valuation`, and
a local `_statement()` helper identical to the one in
`tests/analysis/test_valuation.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/mcp/test_valuation_tool.py -q`
Expected: FAIL — `data_confidence` is 0.85 for the agent-supplied case because the tool does not pass `classification_confidence` yet.

- [ ] **Step 3: Write the implementation**

In `src/rejstrik/mcp/server.py`, replace the tool body and docstring:

```python
@mcp.tool(annotations=_ro("Estimate indicative valuation"))
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
    industry_key: str | None = None,
    ico: str | None = None,
) -> ValuationEstimate:
    """Indicative, deterministic enterprise value from statements YOU extracted.

    One primary method: EV/EBITDA (EBITDA = operating profit + depreciation),
    where the multiple is a Damodaran Europe sector figure adjusted for a Czech
    private company (country, liquidity, profitability, growth and cash-
    conversion factors, clamped to 3-18x). Companies with non-positive EBITDA
    fall back to net assets. Returns a point estimate with a confidence band,
    plus every factor applied.

    Classify the industry yourself from what the filing says the company does —
    you read it, and that beats a registry code. Pass `industry_key`. Failing
    that, pass `ico` to map CZ-NACE to a sector at lower confidence. Set each
    statement's unit field ("czk" | "thousands_czk" | "millions_czk") and pass
    figures verbatim as printed; results are in thousands of CZK.

    Book values are not market values. NOT investment advice."""
    resolved_key: str | None = None
    reason: str | None = None
    confidence = "low"
    if industry_key:
        resolved_key = industry_key
        reason = f"industry_key '{industry_key}' given by caller"
        confidence = "high"
    elif ico:
        company = _find_company(ico)
        resolved_key, reason = industry_key_for_nace(company.nace_codes)
        confidence = "medium"
    return _estimate_valuation(
        statements,
        assumptions,
        industry_key=resolved_key,
        industry_reason=reason,
        classification_confidence=confidence,
    )
```

Note the precedence change: `assumptions` no longer suppresses sector
resolution, because it now only overrides the multiple, not the method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/mcp/ -q`
Expected: PASS

- [ ] **Step 5: Run gates and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add src/rejstrik/mcp/server.py tests/mcp/test_valuation_tool.py
git commit -m "feat(mcp): derive valuation classification confidence from key source

Agent-supplied industry_key is high confidence, CZ-NACE-derived is medium,
none is low. The tool description now tells the agent to classify from the
filing rather than the registry code.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Version bump and README

**Files:**
- Modify: `pyproject.toml`, `server.json` (top-level **and** `packages[0].version`), `mcpb/manifest.json`, `src/rejstrik/__init__.py`
- Modify: `README.md` (the `estimate_valuation` row in the tools table, and the valuation example prompt)

**Interfaces:**
- Consumes: nothing. Produces: nothing. Documentation and metadata only.

- [ ] **Step 1: Confirm the version-sync test guards all four files**

Run: `.venv/bin/python -m pytest tests/test_version_sync.py -q`
Expected: PASS at the current version.

- [ ] **Step 2: Bump the minor version in all four files**

Current is 0.8.0; this is a breaking output change pre-1.0, so go to **0.9.0**.
Edit each of `pyproject.toml`, `server.json` (both places), `mcpb/manifest.json`,
`src/rejstrik/__init__.py`.

- [ ] **Step 3: Run the sync test**

Run: `.venv/bin/python -m pytest tests/test_version_sync.py -q`
Expected: PASS

- [ ] **Step 4: Update the README tools table row**

Replace the `estimate_valuation` row with:

```markdown
| `estimate_valuation` | Vaše vytěžené hodnoty → orientační hodnota firmy: sektorový násobek EV/EBITDA (Damodaran Europe) upravený na český soukromý podnik, bodový odhad s pásmem spolehlivosti a výpisem všech korekcí. Bez LLM. Není investiční doporučení |
```

And update the third example prompt's description to:

```markdown
Vrátí bodový odhad hodnoty s pásmem spolehlivosti, použitý násobek
(základ z Damodaran Europe + jmenované korekce) a upozornění, že nejde o
investiční doporučení.
```

- [ ] **Step 5: Run gates and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py README.md
git commit -m "chore: bump to 0.9.0 for the valuation output change

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Czech showcase card for the README

The original ask. Produces `docs/media/report-card.png` — the filename
`docs/REMAINING.md` already reserves — and makes it the README hero, keeping
the terminal GIF below as proof the flow is live.

**Files:**
- Create: `scripts/render_showcase_card.py`
- Create: `docs/media/report-card.png` (generated)
- Modify: `README.md` (hero image)
- Modify: `docs/REMAINING.md` (item 3 no longer blocks the screenshot)

**Interfaces:**
- Consumes: `estimate_valuation` (Task 3), `analyze_financials` from
  `rejstrik.mcp.server`, `render_report_card` from `rejstrik.mcp.card`.
- Produces: a script that writes an HTML file for screenshotting.

- [ ] **Step 1: Write the generator script**

Create `scripts/render_showcase_card.py`. It must build the card from a real
`analyze_financials` + `estimate_valuation` run on ROBE's filed 2023 figures
(the same figures `scripts/demo_analyze.py` replays), render Czech labels,
**omit IN05**, and include the valuation line. Write the HTML to a path given
by `--out` (default `.showcase-card.html`, which must be added to
`.gitignore`).

The card content, in Czech:

- Heading `ROBE lighting s.r.o.`, subtitle `IČO 64088791 · období 2023 · v tis. Kč`
- Source line `Zdroj: účetní závěrka 2023 (Sbírka listin)`
- `Hodnoty po letech` table: Tržby / Čistý zisk / Aktiva celkem / Vlastní kapitál
- `Poměrové ukazatele` table with Czech names (Běžná likvidita, Kapitálová
  vybavenost, Zadluženost, Čistá marže, ROE, Rychlá likvidita, ROA, Obrat
  aktiv, Úrokové krytí, Provozní marže, Provozní CF / závazky)
- `Orientační hodnota` block: point estimate formatted in mld Kč, the band,
  the multiple (`14,05× EBITDA — základ Damodaran Europe 18,94× × korekce 0,74`),
  and `spolehlivost: střední`
- `Rizikové signály`: green `Žádné rizikové signály.`
- Footer with the Damodaran source line and `Není investiční doporučení.`

Reuse `_STYLE` from `rejstrik.mcp.card` so the card matches the product's
own styling, scoping its `body{` rule to `.card` and wrapping it in a
`#eef2f6` stage with a soft shadow at 600px width.

- [ ] **Step 2: Generate the HTML and screenshot it**

```bash
.venv/bin/python scripts/render_showcase_card.py --out .showcase-card.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=690,1200 \
  --screenshot=docs/media/report-card.png \
  "file://$PWD/.showcase-card.html"
```

Expected: `docs/media/report-card.png` exists, roughly 1380px wide.

- [ ] **Step 3: Verify the image**

Open `docs/media/report-card.png` and confirm: all text is Czech, no IN05
section, the valuation line reads ~13,6 mld Kč, nothing is clipped at the
bottom, and no scrollbar is visible. If clipped, raise `--window-size`
height and re-run Step 2.

- [ ] **Step 4: Update the README hero and REMAINING.md**

In `README.md`, put the card above the GIF:

```markdown
![Report card: ROBE lighting — finanční ukazatele a orientační ocenění z podané účetní závěrky](docs/media/report-card.png)
```

Keep the existing GIF line directly below it, prefixed with a caption line:

```markdown
*Celý průběh v terminálu — bez jakéhokoli API klíče:*
```

In `docs/REMAINING.md` item 3, note that the markdown/HTML card screenshot is
now captured; only the *interactive host rendering* check remains blocked on
ext-apps#671.

- [ ] **Step 5: Run gates and commit**

```bash
echo ".showcase-card.html" >> .gitignore
ruff check src/ tests/ && ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add scripts/render_showcase_card.py docs/media/report-card.png README.md docs/REMAINING.md .gitignore
git commit -m "docs(readme): add Czech report-card showcase image

Renders the real card from a live analyze_financials + estimate_valuation
run on ROBE's filed 2023 statement. IN05 omitted; valuation shown as a
point estimate with its band and the multiple's provenance.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Adjusted multiple | 1 |
| §2 Sector classification + confidence sources | 4 |
| §3 Normalized EBITDA | 2 |
| §4 Soft sales anchor | 3 |
| §4a Confidence band | 3 |
| §5 Asset fallback | 3 |
| §6 Result shape | 3 |
| ROBE worked example | 1 (chain), 3 (end-to-end) |
| Testing section | 1, 2, 3, 4 |
| Risks: breaking change → version bump | 5 |
| Showcase card | 6 |

**Placeholder scan:** none — every code step carries full code; Task 6 Step 1
specifies exact card content rather than "render a card".

**Type consistency:** `AdjustedMultiple.final_multiple` (Task 1) is read as
`adjusted.final_multiple` in Task 3. `normalize_ebitda` returns
`(value, basis)` in Task 2 and is unpacked as `representative, basis` in
Task 3. `classification_confidence` is the keyword in Tasks 3 and 4.
`ValuationAssumptions.ebitda_multiple` is set in Task 3 tests and read in
Task 4's override test.

**Known deviation from upstream:** the confidence band (§4a) is applied to
the multiples range; upstream defines `_CONFIDENCE_BAND` but never reads it.
Deliberate, and recorded in the spec.
