# Valuation: single adjusted-multiple method — design

Date: 2026-07-27
Status: proposed
Author: janf19

## Context

`estimate_valuation` currently returns five parallel numbers and reports
their min/max as a range. For ROBE lighting s.r.o. (2023) that is
**1.9 – 10.4 bn CZK** — a 5× spread, too wide to mean anything.

Three of the five methods rest on constants hardcoded in
`analysis/valuation.py`:

| Method | Constant | Grounded? |
|---|---|---|
| Book value (equity) | — | yes, straight from the balance sheet |
| Capitalized earnings | `capitalization_rate = 0.12` | no — arbitrary |
| EV/EBIT | `ebit_multiple = 5.0` | no — arbitrary |
| P/Revenue | `revenue_multiple = 0.5` | no — arbitrary |
| EV/EBITDA | Damodaran Europe | yes, sourced + dated |

The code labels them honestly ("generic defaults, not industry-calibrated"),
but honest labelling of an arbitrary number does not make it informative.
The EV/EBITDA branch is the only sector-aware one, and it is applied raw:
Damodaran's `electrical_equipment` is **18.94×**, derived from *listed
European* firms. Applied unadjusted to a Czech private SME it yields
~18 bn CZK.

The sibling project `obchodni-rejstrik-ai` ("financialsAI") solved this. It
vendors **the identical data file** — same 94 Damodaran Europe rows, same
`source_url`, same `as_of: 2026-01-05` — but treats the sector multiple as a
*starting point* to be adjusted, and reports one number instead of five.

This design ports that principle. It is not a new model; it is the model
already validated in the sibling project, adapted to this server's
keyless architecture.

## Goals

- One primary method with a point estimate, not a min/max of five.
- Every multiple traceable to sourced data plus explicit, named adjustments.
- Delete the three arbitrary constants.
- Preserve the keyless guarantee: no LLM on the server.

## Non-goals

- DCF. Requires forecasts this server has no basis to make.
- Recalibrating the adjustment factors. They are calibrated against exactly
  this base table in the sibling project and transfer unchanged.
- Changing `analyze_financials`, ratios, red flags, or IN05.

## Design

### 1. Adjusted multiple

`final = clamp(base × Π factors, 3.0, 18.0)`

`base` is the Damodaran Europe EV/EBITDA for the resolved sector. Factors,
ported verbatim from `multiple_adjustments.py`:

| Factor | Value | Rationale |
|---|---|---|
| `country` | 0.83 | Czech vs. European listed baseline |
| `private_liquidity` | 0.95 | private company, no liquid market |
| `size` | 1.00 | placeholder, as upstream |
| `profitability` | 0.85 / 1.00 / 1.10 | by EBITDA margin, capped by net margin |
| `growth` | 0.82 – 1.12 | by revenue growth; 0.95 when unknown |
| `cash_conversion` | 0.75 – 1.00 | by OCF/EBITDA |
| `quality` | 1.00 | placeholder, as upstream |
| `data_confidence` | 0.85 / 0.95 / 1.00 | by classification confidence |

The clamp is what prevents the 18.94× outlier from propagating.

### 2. Sector classification — the keyless divergence

financialsAI classifies with an LLM. This server cannot: it is keyless by
design, and that is its differentiator.

It does not need to. `analysis/industry.py::industry_key_for_nace` already
maps CZ-NACE to a Damodaran key, and its precedence rule (manufacturing
divisions 10–33 beat retail 45–47) is sound: ARES returns
`['471', '261', '952']` for ROBE and the mapper correctly yields
`electronics_general` (17.27×), not the retail code listed first.

So there are two usable classification sources, and the existing precedence
— explicit `industry_key` over NACE-derived — is already right. What changes
is only that the resulting key now feeds the adjustment chain, and that the
*source* of the key sets `data_confidence`:

| Source | Confidence | `data_confidence` |
|---|---|---|
| Agent-supplied `industry_key` | high | 1.00 |
| NACE-derived via `ico` | medium | 0.95 |
| Fallback `total_market_ex_financials` | low | 0.85 |

The agent still outranks NACE because it read the filing: NACE 26 gives ROBE
the generic `electronics_general`, while an agent that knows the company
makes stage lighting can pass `electrical_equipment`. Both are defensible;
the agent's is better-informed, so it wins and carries full confidence.

Signatures are unchanged. The analysis-level
`estimate_valuation(statements, assumptions, industry_key, industry_reason)`
and the MCP-level `estimate_valuation(statements, assumptions, industry_key,
ico)` both keep their parameters.

The tool description must tell the agent to classify from the filing's
actual business description, not from NACE.

Note this `data_confidence` is a *factor on the multiple* and is distinct
from the result's overall `confidence` label (§6), which is driven by
earnings history:

| Condition | Overall `confidence` |
|---|---|
| ≥2 positive EBITDA years, stable (σ/μ < 0.35), specific sector | high |
| ≥2 positive EBITDA years otherwise | medium |
| 1 positive year, specific sector | medium |
| 1 positive year, fallback sector | low |
| asset fallback | low |

A confidently classified sector with only one filed year therefore yields
`data_confidence = 1.00` but overall `confidence = "medium"` — the sector is
known, the earnings history is not.

### 3. Normalized EBITDA

Recency-weighted over positive years: `(2×latest + prior) / 3`, per
`normalize_ebitda`. One year → that year, basis `latest-year`. No positive
year → fall through to the asset method. This damps a single outlier year.

### 4. Soft sales anchor

Guard against EBITDA-driven absurdity: if the EBITDA valuation exceeds
1.25× a revenue anchor, blend `0.70×anchor + 0.30×ebitda_value`. Applies
only when a sales-anchor multiple is available; otherwise inert.

### 4a. Confidence band

`value_low/value_high` come from the overall confidence label:
`high → ±15%`, `medium → ±25%`, `low → ±40%`, applied to the point estimate.

(Upstream defines this `_CONFIDENCE_BAND` but never reads it — its multiples
range collapses to the point. Using it here is a deliberate improvement, not
a port discrepancy.)

### 5. Asset fallback

EBITDA missing or non-positive → net assets (`total_assets −
total_liabilities`, floored at 0), range ±15%, confidence `low`,
`primary_method = "asset"`. Neither available → `insufficient_data`.

### 6. Result shape

`ValuationEstimate` changes shape — a breaking change to the tool's output,
acceptable pre-1.0 and the point of the exercise:

- **removed:** `capitalized_earnings`, `ev_ebit_multiple`,
  `price_revenue_multiple`, `ValuationAssumptions.capitalization_rate`,
  `.ebit_multiple`, `.revenue_multiple`
- **kept:** `book_value`, `ebitda`, `value_low`, `value_high`, `caveats`
- **added:** `point_estimate`, `primary_method`, `confidence`,
  `base_multiple`, `final_multiple`, `adjustment_factors`, `ebitda_basis`

`caveats` keeps the Damodaran provenance line (source, industry, firm count,
`as_of`, URL) and the "not investment advice" disclaimer.

### ROBE lighting, worked

EBITDA = 903,044 + 62,144 = 965,188 tis. CZK. EBITDA margin 24.8% → 1.10;
OCF/EBITDA 0.38 → 0.90; growth unknown (one filed year) → 0.95. Chain =
0.742, i.e. −26% off the listed multiple.

| Classification | Source | Base | Final | Point estimate |
|---|---|---|---|---|
| `electrical_equipment` | agent (stage lighting) | 18.94× | 14.05× | **13.6 bn CZK** |
| `electronics_general` | NACE 26 via `ico` | 17.27× | 12.17× | 11.7 bn CZK |
| `machinery` | agent | 14.98× | 11.11× | 10.7 bn CZK |

The NACE row carries `data_confidence = 0.95`, so its chain is 0.705 rather
than 0.742 — a lower-confidence input is discounted, by construction.

Sector choice still moves the answer by ~25%, which is why
`industry_reason` is recorded and surfaced rather than hidden.

## Testing

Offline and keyless, per CLAUDE.md. TDD: failing test → minimal impl → green.

- each factor at its boundaries (EBITDA margin 0.17/0.08, OCF/EBITDA
  0.20/0.50/0.80, growth 0.12/0.07/0)
- clamp holds at both ends (18.94× base clamps to ≤18.0)
- `normalize_ebitda`: two years recency-weighted, one year, none, negatives
- confidence tiers map to the right `data_confidence`
- asset fallback on negative EBITDA; `insufficient_data` when both missing
- sales anchor applies above 1.25× and is inert without an anchor multiple
- caveats retain Damodaran provenance
- ROBE end-to-end: `electrical_equipment` → 14.05× → 13.6 bn

## Risks

- **Breaking output change.** Pre-1.0, and `estimate_valuation` is not load-
  bearing for the server's main flow. Version bump across the four synced
  files per the release checklist.
- **Sector choice dominates.** Mitigated by clamp, recorded reason, and
  surfaced confidence — not eliminated.
- **Factors are inherited, not independently derived.** They come from a
  working sibling system on the identical base table. Documented as such;
  no claim of independent calibration.

## Showcase card (the original ask)

Once this lands, the README hero card shows real output:
`Orientační hodnota ~13,6 mld Kč · 14,05× EBITDA (Damodaran Europe
18,94× × korekce 0,74) · spolehlivost střední`, alongside the filed figures
and ratios. Czech, per the README. IN05 is dropped from the card.
