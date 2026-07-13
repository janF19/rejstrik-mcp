# Stage A: Filings Live Again — Legacy Portal Fallback + Endpoint Canary

**Date:** 2026-07-13
**Status:** Approved design, pending implementation plan
**Parent:** `2026-07-13-roadmap-overview.md`
**Ships as:** v0.4.1

## Problem

`list_filings()` in `src/rejstrik/filings/justice.py` calls
`https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/{ico}`,
which as of 2026-07-13 returns **403 at the Azure Front Door edge** for
every non-interactive client tested (project UA, browser UA, cookie-primed
session, sandboxed Chromium, remote fetcher). PDF downloads via
`/dokumenty/sbirka-listin/{id}` sit behind the same edge. The keyless
flagship flow — find → list_filings → get_filing → analyze — is dead live.

Meanwhile `or.justice.cz` (the pre-migration portal) still serves both the
subject search and the Sbírka listin listing pages (HTTP 200 verified
2026-07-13), and the repo retains its parsers: `parse_subject_id()` and
`parse_deeds()` in `justice.py`.

## Design

### 1. Live investigation first (time-boxed)

Before coding, spend a bounded slice (≤30 min) confirming the block from a
plain interactive browser and checking whether the new API works with any
reasonable request shape (HTTP/2, `sec-fetch-*` headers, XSRF token from
the Nuxt app). Outcome recorded in the implementation plan:

- If a stable request shape works → implement it as the primary path and
  keep the fallback below anyway.
- If not (expected) → new portal stays primary-but-failing, fallback
  carries the product.

Rationale for keeping the new portal primary: it is the ministry's stated
future; the block may be a temporary WAF policy, and its JSON API is far
more robust than legacy HTML scraping.

### 2. Fallback chain in `list_filings`

```
list_filings(ico) →
  try new JSON API
  on 403/blocked (and only on block-shaped failures):
    or.justice.cz search by IČO → parse_subject_id →
    vypis-sl page → parse_deeds → list[Filing]
```

- `parse_deeds` selectors were written against a placeholder structure
  (`div.document-row` / `span.document-title` — the code itself warns
  "selectors may need updating for real justice.cz HTML"). **The plan must
  start by capturing real `or.justice.cz` HTML as fixtures** (one search
  page, one Sbírka listin page for Budvar, IČO 00514152) and rewriting the
  parsers against them, TDD-style.
- Legacy rows carry filing metadata (type, year, page count) and document
  detail links; map to the existing `Filing` model. `pdf_url` points at the
  legacy download endpoint.
- `load_pdf()` must work for both URL families (it already takes
  `filing.pdf_url`; verify redirects/content-type handling on the legacy
  host).
- Filing IDs differ between portals. `filing_id` selection keeps working
  per-portal: IDs returned by `list_filings` are always valid inputs to
  `get_filing` in the same portal mode. Do not attempt cross-portal ID
  translation.

### 3. Honest errors when both portals fail

If the new API is blocked and the legacy path also fails, raise a typed
error that names both portals, includes the manual URL
(`https://or.justice.cz/ias/ui/rejstrik-$firma?ico=...`), and says the
registry may be blocking automated access. Agents relay honest errors well.

### 4. Canary so this never silently rots again

- `scripts/smoke.py` gains an explicit **endpoint canary section** that
  hits both portals and prints a one-line PASS/BLOCKED per endpoint,
  run-before-release per CLAUDE.md.
- Optional (include if cheap): a scheduled GitHub Actions workflow
  (weekly, `workflow_dispatch`-able) that runs only the canary — not the
  full smoke — and opens/updates an issue on failure. This is the one
  permitted live-network CI touchpoint, clearly separated from the
  offline test suite.

## Not in scope

- Proxy/fingerprint evasion (curl-impersonate, residential proxies). The
  project scrapes public registries politely under an honest UA; if the
  ministry blocks that, the answer is the legacy portal and honest errors,
  not an arms race.

## Testing

- Offline fixtures for: legacy search page, legacy filings page, block
  page (403 HTML) from the new portal.
- Unit: fallback triggers on 403 but not on 404/timeout (those surface as
  their own errors); parser correctness; sort order preserved
  (financial statements first, year desc).
- `test_smoke.py` asserts canary section exists (structure only, offline).

## Acceptance

`rejstrik analyze "Budejovicky Budvar"` completes live on the dev machine
(currently 403s), via whichever portal works, and `scripts/smoke.py`
reports per-portal status.
