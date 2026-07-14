# Unit Normalization & Verification-Audit Fixes — Design

**Date:** 2026-07-15
**Status:** Approved for planning; implementation plan at
`docs/superpowers/plans/2026-07-15-unit-normalization-and-verification-fixes.md`

## Where this came from

A launch-readiness verification session (2026-07-15) drove the full pipeline
live against Budějovický Budvar (IČO 00514152) and found one real
correctness bug plus several smaller gaps. All offline gates were green
(ruff, 283 tests) and every live tool worked; the bug is in the *numbers*,
not the plumbing.

### Finding 1 (the bug): cross-year unit mismatch makes trends garbage

`python scripts/smoke.py` with an LLM key produced, for
`analyze_company_financials(years=2)`:

| metric | current | prior | reported pct_change |
|---|---|---|---|
| revenue | 3,647,852 | 3,666,523,000 | −99.9% |
| net_profit | 356,318 | 371,051,000 | −99.9% |
| total_assets | 5,408,329 | 5,754,734,000 | −99.9% |
| equity | 4,398,302 | 4,549,753,000 | −99.9% |

Budvar's real revenue is ~3.6B CZK. The 2025 statement was extracted in
thousands of CZK, the 2024 one in absolute CZK, and the analysis layer
compared them raw. Root causes, confirmed by code inspection:

- `FinancialStatement` (`src/rejstrik/documents/schema.py`) has no field
  recording the scale the figures were read at — only `currency`.
- `EXTRACT_INSTRUCTIONS` (`src/rejstrik/documents/extract.py`) says "Use CZK
  unless the document states otherwise", which invites the LLM to sometimes
  convert and sometimes not. Czech statutory statements are filed
  "v celých tisících Kč" (whole thousands of CZK) almost universally.
- `normalize()` (`src/rejstrik/analysis/normalize.py`) copies values
  verbatim; `compute_trends`/`compute_trend_series`
  (`src/rejstrik/analysis/trends.py`) divide raw values with no
  plausibility guard.
- `scripts/smoke.py` printed `SMOKE OK` anyway — it checks that trends
  exist, not that they are sane.

This poisons the headline demo path (`analyze_company_financials`,
`analyze_company_card`, multi-year `analyze_financials`) whenever two years
are read at different scales. Single-year ratios are scale-invariant and
unaffected (except IN05 absolute thresholds — none currently used — and
valuation, which is per-statement so internally consistent).

### Finding 2 (fixed in-tree, needs commit): `serverInfo.version` lied

`FastMCP` has no `version` kwarg, so initialize responses reported the MCP
SDK version (`1.26.0`) instead of the package version (`0.7.0`). Fixed by
pinning `mcp._mcp_server.version = __version__` in
`src/rejstrik/mcp/server.py`; verified live over HTTP.

### Finding 3 (fixed in-tree, needs commit): `scripts` namespace-package collision

`tests/test_smoke.py` does `from scripts import smoke`, but `scripts/` had
no `__init__.py`, making it a PEP 420 namespace package. A *regular*
`scripts` package anywhere on `sys.path` (another project installed in the
same environment) always wins over a namespace package, which made 17 test
modules fail collection locally while CI stayed green. Fixed by adding
`scripts/__init__.py`.

### Finding 4: README still hides the PyPI badge

`README.md` line 3 keeps the PyPI badge commented out "until first publish
(Stage E T5/T6)". 0.7.0 is on PyPI; the condition is met — restore it.

### Not doing (recorded so it isn't re-litigated)

- **pytest-asyncio loop-scope warning** seen locally comes from a globally
  installed plugin that is not one of this repo's dev dependencies; adding
  its ini option would emit "unknown config option" warnings in clean CI.
  Leave it alone.
- **Auto-rescaling on suspected mismatch.** When years disagree ~1000×, we
  flag and suppress rather than silently "fix", because guessing which year
  is wrong is unverifiable. Honest suppression + a red flag beats a
  confident wrong number.
- The four human-only launch items (demo media, MCP registry publish,
  directory listings, live Desktop `_UI_META` check) are unchanged.

## Design

### Canonical unit: thousands of CZK

Everything downstream already documents this ("Figures as filed; typically
thousands of CZK" in the card, valuation disclaimer, tool docstrings), and
it is the Czech statutory filing scale. `NormalizedFinancials` becomes
*defined* as thousands of CZK.

### Layer 1 — record the scale at extraction

`FinancialStatement` gains:

```python
unit: Literal["czk", "thousands_czk", "millions_czk"] | None = None
```

with a `Field` description that teaches both the keyed extractor LLM and
keyless host agents (the description flows into the MCP tool JSON schema
and the `analyze-company` prompt embeds the schema): record figures
**verbatim as printed**, set `unit` from the declared scale
("v celých tisících Kč" → `thousands_czk`), never convert. `None` means
unknown and is treated as already-in-thousands (no conversion), which
preserves today's behavior for every existing caller and fixture.

`EXTRACT_INSTRUCTIONS` is rewritten to match (verbatim figures + set
`unit`), replacing the ambiguous "Use CZK unless the document states
otherwise".

### Layer 2 — convert once, in `normalize()`

`normalize()` multiplies every extracted value by a per-statement factor:
`czk` → 0.001, `thousands_czk` → 1.0, `millions_czk` → 1000.0, `None` →
1.0. All ratios, red flags, IN05, trends, valuation and the card then see
consistent thousands-of-CZK numbers.

### Layer 3 — defense in depth: mismatch guard in trends

Layer 1 depends on an LLM (or host agent) labeling correctly, so the
deterministic layer still guards: `suspected_unit_mismatch(current, prior)`
in `trends.py` returns True when **≥2** of the four headline metrics are
present and positive in both years and **all** of them shifted ≥100× in the
same direction — the signature of a scale mix-up, not a business event.
On mismatch: `compute_trends` keeps the raw `current`/`prior` values but
nulls `pct_change`; `compute_trend_series` nulls `cagr`;
`analyze_statements` appends a `warning` red flag
`unit_mismatch_suspected` telling the caller to check `unit` per statement.
A single-metric 1000× move (possible in reality) never triggers it.

### Layer 4 — the smoke canary must catch this class of bug

`scripts/smoke.py` gains `trend_plausibility_issues(report)`: fails the
smoke run (exit ≠ 0) if the multi-year report carries
`unit_mismatch_suspected` or any headline |pct_change| > 90%. Offline-unit
tested like `canary()` already is.

### Release

Ship as **0.7.1** (bug fix + additive schema field). Version must change in
all five places (`pyproject.toml`, `server.json` ×2, `mcpb/manifest.json`,
`src/rejstrik/__init__.py`) plus the hardcoded assert in
`tests/test_smoke.py`; `tests/test_version_sync.py` enforces the first
five. Tagging `v0.7.1` (triggers PyPI publish) and the MCP registry
publish remain explicit human decisions.
