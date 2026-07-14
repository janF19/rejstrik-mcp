# Post-Audit Hardening & Features (Stages F–G)

**Date:** 2026-07-14
**Status:** Approved direction, pending per-stage implementation plans
**Builds on:** `2026-07-13-roadmap-overview.md` (Stages A–E, shipped through v0.6.0)

## Why this spec exists

A post-Stage-E audit on 2026-07-14 (248 tests green, lint clean, all five
roadmap stages verified against their specs) found the product healthy but
left a short list of real defects, robustness gaps, and two features that
close the remaining holes in the keyless promise. This spec records them
so each stage can get its own implementation plan.

Two stages, independently shippable:

| Stage | Goal | Ships as |
|---|---|---|
| F | Hardening: fix the audit's defects and robustness gaps | v0.6.1 |
| G | Features: scanned filings as images; NACE-aware valuation; small perf/ops items | v0.7.0 |

**F before G** — G's features land on code paths F touches (valuation,
filings client), and F is small enough to ship same-day.

---

## Stage F: Hardening (v0.6.1)

### F1. README references media that does not exist

`README.md` "See it work" (lines 12–20) embeds
`docs/media/budvar-3year.gif` and `docs/media/report-card.png`; neither
file is committed (Stage E Task 4 is still a pending human task). Anyone
visiting the repo sees two broken images directly under the headline
pitch. The Stage E plan warned to land T3 and T4 together; T3 landed
alone.

**Design:** keep the "See it work" section heading but replace the two
image embeds with a single honest line — e.g. *"Demo media is being
recorded (see `scripts/record_demo.sh`); meanwhile the walkthrough below
shows the exact flow."* — until Task 4 commits the binaries, at which
point the embeds are restored verbatim from the Stage E plan. Do **not**
delete the section: its prose (the Budvar question → answer walkthrough)
stands on its own.

The PyPI badge (line 3) renders "package not found" until first publish.
If publish (Stage E T5/T6) is imminent, leave it; otherwise comment it
out with an HTML comment noting when to restore. The implementation plan
decides based on publish status on the day.

### F2. A fourth version location escapes the drift guard

`src/rejstrik/__init__.py:1` hardcodes `__version__ = "0.6.0"`.
`tests/test_version_sync.py` guards only `server.json` and
`mcpb/manifest.json` against `pyproject.toml`, and the README "Releasing"
checklist says "all **three** files". This is exactly the drift class the
guard was built for.

**Design:** extend `tests/test_version_sync.py` with
`test_package_dunder_version_matches_pyproject` importing
`rejstrik.__version__` (no runtime change — keep the hardcoded string;
`importlib.metadata` at import time is slower and fails in odd packaging
states). Update the README Releasing step to say **four** places and name
the file. No version bump needed by this change itself; it ships with F.

### F3. `estimate_valuation([])` crashes with a bare IndexError

`src/rejstrik/analysis/valuation.py:51` does `ordered[0]` on an empty
list. Its sibling `analyze_statements` (`service.py:168`) raises a
helpful `ValueError` telling the agent what to do. An agent calling the
tool with `statements=[]` gets a stack trace instead of guidance.

**Design:** raise `ValueError` with the same wording pattern:
*"statements must contain at least one FinancialStatement (extract it
from the PDF returned by get_filing)"*. TDD: failing test first
(`tests/analysis/` alongside the existing valuation tests).

### F4. Legacy fallback triggers only on an exact HTTP 403

`list_filings` (`src/rejstrik/filings/justice.py:154`) falls back to
`or.justice.cz` only on `HTTPStatusError` with status 403. Azure Front
Door blocks are not always 403-shaped:

- a **200 with a challenge/interstitial HTML page** makes `resp.json()`
  raise `JSONDecodeError`, which propagates raw — no fallback;
- **429** (rate-limited) and **5xx** from the edge also bypass the
  fallback.

Stage A's spec said "block-shaped failures"; 403-only is too narrow for a
WAF we don't control.

**Design:** treat as block-shaped, and therefore fallback-eligible:

- HTTP 403 (unchanged) and 429;
- HTTP 5xx from the new portal;
- a 2xx response whose body fails to parse as JSON (challenge page).

Keep propagating unchanged: 404 (subject genuinely absent — the legacy
portal would also miss it, and a `RegistryBlockedError` would mislead),
connect/read timeouts and transport errors (network trouble hits both
portals; `core/http.py` retries already cover transients). The
`RegistryBlockedError` message should name the actual trigger (status
code or "non-JSON response") so live debugging stays honest.

**Testing:** offline fixtures for each new trigger shape — a 200
challenge-HTML body, a 429, a 503 — asserting fallback engages; existing
404/timeout tests keep asserting no fallback.

### F5. Minor fixes (bundle into the F plan, one commit each)

- **Split-year filing titles:** `_YEAR_RE` in `justice.py` takes the
  *first* year, so "účetní závěrka 2023/2024" yields 2023. Take the
  **max** year found in the title instead (the accounting period ends in
  the later year). Test with a split-year title fixture.
- **`scripts/smoke.py:60`** hardcodes `period_year=2024`, which silently
  goes stale. Derive from the fetched filing's `doc.year`, falling back
  to `date.today().year - 1`.
- **README "A Note On Real-World Drift"** still ends at the portal
  migration; add two sentences covering the 2026-07 AFD block and the
  legacy-portal fallback + canary — it is the repo's best engineering
  story and currently undersold. Also mention the fallback in the
  `filings/` line of "How it works".

### F6. Human checklist (not code; carried from the audit)

- [ ] Verify the MCP Apps `_UI_META` key (`server.py:60`, marked VERIFY)
      against the current MCP Apps spec in a live Claude Desktop session;
      set `REJSTRIK_APPS_CAPABILITY_KEY` if the negotiated key differs.
- [ ] Turn on GitHub Actions failure notifications for `canary.yml` (or
      rely on G4's auto-issue once shipped).
- [ ] Stage E T4–T6 remain open: record demo media, verify/publish the
      registry entry, directory + community listings.

### Stage F acceptance

Full suite green on both CI OSes; a fixture-driven test exists for every
new fallback trigger; `estimate_valuation([])` raises `ValueError`;
`test_version_sync.py` covers four locations; README shows no broken
images.

---

## Stage G: Features (v0.7.0)

### G1. Scanned filings as images (`read_filing_page_images`)

**The gap:** many Czech filings are scans with no text layer.
`read_filing_text` honestly reports `has_text=false`, but a host
*without* filesystem access then dead-ends: it cannot read `file_path`,
gets no text, and a 20–25 MB PDF won't embed. The keyless promise
currently holds only for filesystem-capable hosts or born-digital PDFs.

**Design:** a new keyless tool mirroring `read_filing_text`'s shape:

```
read_filing_page_images(ico, year=None, filing_id=None, pages="1-5")
  → list of MCP ImageContent blocks (+ one TextContent with metadata)
```

- Rasterize with **pypdfium2** (permissive license, prebuilt wheels, no
  system deps) — this is a **new runtime dependency**, the first since
  the keyless pivot; the plan should confirm wheel availability for the
  CI matrix (Linux + Windows, py3.11/3.12).
- Render at a DPI that keeps statement tables legible (~150 DPI target,
  longest side capped ≈1600 px), encode PNG.
- Reuse `parse_page_range` grammar, but cap at **5 pages per call**
  (images are token-expensive on the host side); the metadata text block
  reports `page_count`, the pages returned, and the same honest
  clamp/message behavior as `read_filing_text`.
- Steer agents: `read_filing_text`'s no-text-layer note and the
  `analyze-company` prompt step 3 both point to
  `read_filing_page_images` as the scan remedy for hosts without
  filesystem access.
- Tests offline: a tiny generated 2-page PDF fixture (one text page, one
  image-only page); assert PNG magic bytes, page caps, range clamping.
  No network, no LLM.

### G2. NACE-aware valuation multiples

**The gap:** `ValuationAssumptions` defaults (12% cap rate, 5× EBIT,
0.5× revenue) are deliberately generic; the caveat says "not
industry-calibrated". ARES returns CZ-NACE activity codes but the
`Company` model doesn't capture them, so the calibration hook doesn't
exist.

**Design:**

- Extend `Company` (registry/models.py) with `nace_codes: list[str]`
  parsed from the ARES economic-activity field (`czNace` in the detail
  record; fixture-verify the exact key).
- Add a **NACE-section → multiples table** in `analysis/valuation.py`
  (pure data, no I/O): map the ~21 NACE sections (A–U) to
  `(ebit_multiple, revenue_multiple, capitalization_rate)` ranges with
  conservative, sourced defaults; unknown/missing section keeps today's
  generic defaults.
- `estimate_valuation` gains an optional `nace_code: str | None`
  parameter that seeds `ValuationAssumptions` (explicit
  `assumptions=` always wins over NACE seeding).
- Service/MCP wiring: the `estimate_valuation` **tool** gains optional
  `ico` — when given, the server resolves NACE via ARES itself;
  statements-only calls stay fully offline. The caveats list must state
  which multiples were applied and why ("NACE section C defaults" vs
  "generic defaults").
- The multiples table encodes judgment: values go in the spec review, not
  silently in code. The implementation plan must list the table for
  product-owner sign-off before coding.

### G3. Short-TTL cache for `list_filings`

Only PDFs are cached today; every multi-year analysis re-hits the
registry per tool call. Add an in-process TTL cache (default 15 min,
`REJSTRIK_FILINGS_TTL_SECONDS` override, 0 disables) keyed by padded IČO,
with an injectable clock for tests. In-memory only — the server is
single-process for stdio and per-worker state is acceptable for HTTP;
no cross-process cache, no new dependency.

### G4. Canary auto-files a tracking issue

`canary.yml` failures currently only fail a scheduled job nobody watches.
Extend the workflow: on failure, open **or update** a single tracking
issue (search by a `portal-canary` label; comment if open, create if
not) via `actions/github-script` with the default `GITHUB_TOKEN`. Closes
the TODO deferred in Stage A Task 6. Workflow-only change; no Python
code, no tests beyond YAML lint.

### Stage G acceptance

- A scanned (image-only) filing page reaches a filesystem-less host as a
  legible PNG via `read_filing_page_images`, offline-tested.
- `find_company` surfaces NACE codes; valuation with a known NACE section
  applies table multiples and says so in caveats; without one, output is
  byte-identical to v0.6.x behavior.
- Repeated `list_filings` within the TTL hits the network once
  (unit-tested with the injected clock).
- A manually dispatched canary run against a forced failure files/updates
  the tracking issue.

---

## Not in scope

- OCR (tesseract etc.) — G1's image delivery makes the *host* model the
  OCR engine, which is the project's whole design stance.
- Fingerprint evasion for the new portal (unchanged from Stage A).
- Industry multiples beyond NACE-section granularity (division-level
  calibration needs data the project doesn't have).
- Hosted/multi-tenant HTTP deployment concerns (per-worker cache is
  accepted in G3).

## Working agreement per stage

Unchanged from the roadmap overview: open this spec → `writing-plans`
skill → TDD per CLAUDE.md (offline, key-free tests) → ruff + pytest green
on both CI OSes → `scripts/smoke.py` before any release tag.
