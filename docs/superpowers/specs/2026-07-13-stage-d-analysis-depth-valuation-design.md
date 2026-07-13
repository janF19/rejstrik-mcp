# Stage D: Analysis Depth — Canonical Fields, More Ratios, IN05, Trends, Indicative Valuation

**Date:** 2026-07-13
**Status:** Approved design, pending implementation plan
**Parent:** `2026-07-13-roadmap-overview.md`
**Ships as:** v0.6.0

## Problem

The analysis layer is the differentiator vs registry-only MCPs, and it is
currently the thinnest part:

- **Silent wrong numbers.** `analysis/normalize.py` maps free-form figure
  labels to fields by first-substring-match: "trzby" can match *Tržby z
  prodeje dlouhodobého majetku* before actual revenue; "vysledek
  hospodareni" matches *Provozní výsledek hospodaření* as readily as the
  net result. Which figure wins depends on extraction order. For a
  finance tool this is the worst failure mode.
- 5 ratios, no interest coverage / ROA / turnover, no distress score,
  no cash-flow use at all.
- With 5 years fetched, trends still compare only latest vs one prior.
- No valuation, despite the product goal explicitly including it.

## Design

### 1. Canonical fields in `FinancialStatement` (kills keyword fragility)

Extend `documents/schema.py` additively:

```python
class CanonicalFigures(BaseModel):
    total_assets: Figure | None = None
    current_assets: Figure | None = None
    equity: Figure | None = None
    total_liabilities: Figure | None = None
    current_liabilities: Figure | None = None
    revenue: Figure | None = None            # trzby z prodeje vyrobku/sluzeb/zbozi
    operating_profit: Figure | None = None   # provozni vysledek hospodareni
    net_profit: Figure | None = None         # vysledek hospodareni za ucetni obdobi
    interest_expense: Figure | None = None   # nakladove uroky
    cash: Figure | None = None
    inventories: Figure | None = None
    receivables: Figure | None = None
    operating_cash_flow: Figure | None = None

class FinancialStatement(...):
    canonical: CanonicalFigures | None = None   # new
    # balance_sheet/income_statement/cash_flow lists stay, as audit trail
```

- The **extractor fills `canonical` directly** — in keyless mode the
  `analyze-company` prompt schema/instructions tell the host model
  exactly which Czech statutory line feeds each field (each field's
  description carries the Czech line name, as above); in keyed mode the
  server-side extraction prompt does the same. `Figure` keeps
  `source_page`, so citations survive.
- `normalize()` prefers `canonical` when present and falls back to the
  existing keyword matching for backward compatibility (old callers,
  old cached extractions). Keyword fallback fixes its two known traps:
  prefer exact/prefix matches for revenue and require "za ucetni obdobi"
  context for net profit before accepting bare "vysledek hospodareni".

### 2. Ratio expansion (`analysis/ratios.py`, all `None`-safe)

Add: `quick_ratio`, `return_on_assets`, `asset_turnover`,
`interest_coverage` (operating_profit / interest_expense),
`operating_margin`, `ocf_to_liabilities`. Keep the existing five.
Same `_div` guard pattern; no ratio invents data.

### 3. IN05 distress index (Czech-native headline feature)

`analysis/in05.py`:
`IN05 = 0.13·A/CZ + 0.04·EBIT/U + 3.97·EBIT/A + 0.21·VYN/A + 0.09·OA/KZ`
(Neumaier & Neumaierová 2005). Standard bounded-EBIT/U treatment (cap at
9) to avoid the known interest-expense blowup. Output: value + zone
(`distress < 0.9`, `grey`, `value-creating > 1.6`) + which inputs were
missing (compute only when all required inputs exist; otherwise return
the miss-list, never a partial score). Feeds a red flag:
`in05_distress` (critical) / `in05_grey_zone` (info).

### 4. Full multi-year trend series

`compute_trends` gains a series form: for each metric, the full
year-by-year list plus CAGR when ≥3 years and endpoints positive.
`TrendItem` stays for compatibility; `CompanyFinancialReport` gains
`trend_series` additively. The card (Stage C) and prompts consume it.

### 5. `estimate_valuation` tool (indicative, deterministic, keyless)

New `analysis/valuation.py` + MCP tool
`estimate_valuation(statements: list[FinancialStatement], assumptions: ValuationAssumptions | None)`:

Three standard small-business methods, all arithmetic, all
assumption-transparent:

1. **Book value** (equity, latest year).
2. **Capitalized earnings**: sustainable earnings (avg net profit over
   provided years, flag if dispersion high) / capitalization rate
   (default 12% for private CZ SME; overridable via assumptions).
3. **Multiples**: EV ≈ multiple × EBIT (default 5×) and price ≈
   multiple × revenue (default 0.5×), defaults overridable and clearly
   labeled as generic, not industry-calibrated.

Output model: per-method value, the assumptions used, an overall
**range** (min–max of methods), and a fixed caveats list (thousands-CZK
units, book values ≠ market values, no industry calibration, minority /
marketability discounts not applied, **not investment advice**). The tool
description carries the disclaimer too.

YAGNI line: no DCF (requires forecasts we don't have), no WACC modeling,
no industry multiple tables (future data project).

### 6. Red-flag additions

`interest_coverage < 1` (critical), `negative_operating_cash_flow` with
positive net profit (warning — profit-quality signal), IN05 zones (above).

## Testing

Pure-function layer → straightforward unit tests: canonical-first
normalization, keyword-fallback trap cases (asset-sale revenue, operating
vs net result), each new ratio incl. None-propagation, IN05 against a
hand-computed fixture + missing-input behavior + EBIT/U cap, trend series
+ CAGR edge cases (zero/negative endpoints), valuation methods against
hand-computed fixtures + assumption overrides + dispersion flag.
Prompt tests: schema text mentions canonical fields and Czech line names.

## Acceptance

Budvar 3-year keyless run (live, post-Stage-A) produces: cited canonical
figures, ≥11 ratios, IN05 with zone, 3-year series with CAGR, and a
valuation range with stated assumptions — all deterministic given the
same extracted statements.
