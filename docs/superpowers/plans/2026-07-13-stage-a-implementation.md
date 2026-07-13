# Stage A: Filings Live Again — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or
> superpowers:subagent-driven-development. Follow TDD (failing test → minimal
> impl → green → commit) per step. Tests stay offline and key-free.

**Goal:** Restore the keyless flagship flow (`find → list_filings → get_filing
→ analyze`) which is dead live because `verejnerejstriky.msp.gov.cz` 403s at
the Azure Front Door edge. Add a legacy `or.justice.cz` fallback with real
(not placeholder) selectors, honest errors when both portals fail, and a
canary so this doesn't silently rot again.

**Spec:** `docs/superpowers/specs/2026-07-13-stage-a-filings-fallback-design.md`

## Live investigation results (recorded 2026-07-13, time-boxed ~25 min)

Probed live against IČO `00514152` (Budějovický Budvar):

- `GET https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152`
  → **403** every time, with or without `sec-fetch-*`/Referer/HTTP2 headers.
  Body is an Azure Front Door "Nenalezeno / access denied" HTML block page
  (not JSON) — always 403, no header combination bypassed it. **Decision:
  new API stays primary-but-failing per spec §1; no code path attempts
  evasion.** Block page saved as
  `tests/fixtures/justice/new_api_block_403.html`.
- `GET https://or.justice.cz/ias/ui/rejstrik-$firma?ico=00514152` → **200**.
  Note the literal `$firma` path segment (Wicket page id, not a shell var —
  quote it in code as a plain string). Contains
  `subjektId=59981` for Budvar. Saved as
  `tests/fixtures/justice/legacy_search_00514152.html`.
- `GET https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId=59981` → **200**.
  Real structure is a `<table class="list"><tbody><tr>` — **not**
  `div.document-row`/`span.document-title` as the current (placeholder)
  selectors assume. Each `<tr>` has: `<td><a href="./vypis-sl-detail?
  dokument=<id>&subjektId=<sid>&spis=<spis>"><span>číslo listiny</span></a>
  </td>`, then a `<td>` with one or more `<span class="symbol">typ [rok]</span>`
  (comma-joined when a filing covers multiple types, e.g. "účetní závěrka
  [2024], výroční zpráva [2024], zpráva auditora [2024]"), then date/page
  columns. Saved as `tests/fixtures/justice/legacy_deeds_00514152.html`.
- `GET https://or.justice.cz/ias/ui/vypis-sl-detail?dokument=87101138&
  subjektId=59981&spis=411891` → **200**. Contains the actual PDF download
  link: `<a href="/ias/content/download?id=<token>">filename.pdf (size, pages)
  </a>`. Saved as `tests/fixtures/justice/legacy_detail_87101138.html`.
- **Critical finding: the download `id` token is single-use/session-scoped
  and NOT stable.** Re-fetching the same detail page minutes apart yields a
  *different* `id` token each time (confirmed 3x). A stale token 404s with
  "Neplatný odkaz: ... vypršela jeho časová platnost" (invalid/expired
  link). It does **not** require cookies (verified: fresh curl invocation
  with zero cookies, using only a token extracted seconds earlier, succeeds
  — `Content-Type: application/pdf`, 2.7MB). **Design consequence:
  `Filing.pdf_url` for legacy filings must store the stable *detail page*
  URL, not a resolved download link. `load_pdf()` must fetch the detail
  page and extract a fresh download token immediately before downloading —
  never cache a resolved legacy download URL across time.**

## Architecture

- `filings/justice.py`: rewrite `parse_deeds()` against real markup; add
  `parse_download_link(html, base_url) -> str | None` (extracts the
  `/ias/content/download?id=...` href from a detail page); add
  `LEGACY_SEARCH_URL`/`LEGACY_DEEDS_URL` templates; add
  `_is_block_response(resp) -> bool` (403 check); rewrite `list_filings()`
  with the try-new/fallback-to-legacy chain; add typed error
  `RegistryBlockedError`.
- `documents/source.py`: `load_pdf()` gains a branch — if the URL host is
  `or.justice.cz` and path is `/ias/ui/vypis-sl-detail`, fetch it, resolve
  the fresh download link via `parse_download_link`, then fetch that.
- `scripts/smoke.py`: new `canary()` function, offline-detectable by
  `test_smoke.py` (structure-only assertions, no network in tests).
- `.github/workflows/canary.yml`: new scheduled workflow (weekly +
  `workflow_dispatch`), runs only the canary, fails the job on block (kept
  minimal — no auto-issue-filing, that's flagged as a follow-up TODO to
  keep this stage bounded).

## Global constraints

- Offline, key-free tests only; mock HTTP via `respx`.
- `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m
  pytest -q` must pass before every commit.
- Do not attempt fingerprint evasion for the new API (out of scope per spec).
- Filing IDs stay per-portal; no cross-portal ID translation (per spec §2).

---

### Task 1: Real fixtures + rewritten `parse_deeds`/`parse_subject_id`

**Files:** `tests/fixtures/justice/legacy_*.html` (already captured, see
above), `tests/filings/test_justice.py`, `src/rejstrik/filings/justice.py`

- [x] Step 1: Capture real fixtures (done above — search, deeds, detail,
  block pages for IČO 00514152 / subjektId 59981).
- [ ] Step 2: Write failing tests in `tests/filings/test_justice.py` against
  the new fixtures: `parse_subject_id` finds `59981` from
  `legacy_search_00514152.html`; `parse_deeds` on
  `legacy_deeds_00514152.html` returns filings with correct titles (joined
  `symbol` spans), years parsed from `[YYYY]`, `pdf_url` pointing at the
  absolute detail-page URL (`https://or.justice.cz/ias/ui/vypis-sl-detail?
  dokument=...&subjektId=...&spis=...`), `is_financial_statement=True` for
  the účetní závěrka/výroční zpráva rows, and financial-first/year-desc sort
  order preserved. Keep or delete the old synthetic fixtures/tests
  (`subject_00006947.html`, `deeds_00006947.html`) — decide based on whether
  they still add value once real fixtures exist; prefer deleting duplicated
  synthetic coverage to avoid maintaining two selector contracts.
- [ ] Step 3: Rewrite `parse_deeds()` in `justice.py` against the real
  `table.list` structure. Extract `dokument`, `subjektId`, `spis` from the
  row's detail link; build absolute `pdf_url` from `_BASE_URL +
  "/ias/ui/" + href.lstrip("./")`. Join all `span.symbol` texts with `", "`
  for the title.
- [ ] Step 4: Verify — `python -m pytest tests/filings/test_justice.py -q`
  green.
- [ ] Step 5: Commit: `fix(filings): rewrite parse_deeds against real
  or.justice.cz markup`.

### Task 2: `parse_download_link` + legacy-aware `load_pdf`

**Files:** `src/rejstrik/filings/justice.py`, `src/rejstrik/documents/source.py`,
`tests/filings/test_justice.py`, `tests/documents/test_source.py`

- [ ] Step 1: Write failing test for `parse_download_link(html, base_url)`
  using `legacy_detail_87101138.html` — asserts it returns the absolute
  `https://or.justice.cz/ias/content/download?id=...` URL.
- [ ] Step 2: Implement `parse_download_link` in `justice.py`.
- [ ] Step 3: Write failing test in `tests/documents/test_source.py`:
  `load_pdf()` given a `Filing` whose `pdf_url` is a
  `.../vypis-sl-detail?...` URL does a two-step fetch (mock both requests
  with `respx`: GET detail page → GET resolved download link) and returns
  the PDF bytes from the second response. Also add a case confirming plain
  URLs (new-API document URLs, or any non-legacy-detail URL) still do a
  single direct GET (no regression).
- [ ] Step 4: Implement the branch in `load_pdf()`: detect legacy detail
  URLs (`or.justice.cz` host + `/ias/ui/vypis-sl-detail` path), fetch,
  parse download link via `parse_download_link`, fetch that, return.
- [ ] Step 5: Verify — `python -m pytest tests/documents/test_source.py
  tests/filings/test_justice.py -q` green.
- [ ] Step 6: Commit: `feat(documents): resolve legacy filing PDFs via
  fresh detail-page token`.

### Task 3: Fallback chain + typed error in `list_filings`

**Files:** `src/rejstrik/filings/justice.py`, `tests/filings/test_justice.py`

- [ ] Step 1: Write failing tests with `respx`:
  - New API returns 403 → `list_filings` falls back: mocks legacy search
    (200, `legacy_search_00514152.html`) and legacy deeds (200,
    `legacy_deeds_00514152.html`) → returns parsed legacy filings.
  - New API returns 404 → `list_filings` does **not** fall back; the
    `httpx.HTTPStatusError` (or equivalent) propagates unchanged (per spec:
    fallback triggers "only on block-shaped failures").
  - New API returns 403 AND legacy search/deeds also fails (e.g. legacy
    returns 200 but `parse_subject_id` finds nothing, or legacy itself
    errors) → raises `RegistryBlockedError` whose message names both
    portals, includes the manual URL
    `https://or.justice.cz/ias/ui/rejstrik-$firma?ico=<ico>` (with the raw,
    non-URL-encoded ICO as used in the manual link), and mentions the
    registry may be blocking automated access.
  - Sort order (financial-first, year-desc) preserved in the fallback path.
- [ ] Step 2: Add `RegistryBlockedError(Exception)` to `justice.py`.
- [ ] Step 3: Implement the fallback chain in `list_filings()`: try new
  API; on `httpx.HTTPStatusError` with `status_code == 403`, try legacy
  (search by ICO w/ leading zeros preserved → `parse_subject_id` →
  `vypis-sl-firma` → `parse_deeds`); if legacy also fails or finds no
  subject, raise `RegistryBlockedError`. Non-403 errors from the new API
  propagate unchanged.
- [ ] Step 4: Verify — `python -m pytest tests/filings/test_justice.py -q`
  green.
- [ ] Step 5: Commit: `feat(filings): fall back to legacy or.justice.cz
  portal when new API is blocked`.

### Task 4: Live acceptance check (manual, not part of automated suite)

- [x] Step 1: Run live (not in CI): confirm `rejstrik analyze "Budejovicky
  Budvar"` (or the equivalent service call) completes end-to-end via the
  legacy fallback. Record actual result in this plan file (pass/fail +
  notes) — this satisfies the spec's Acceptance criterion.

  **Result: PASS (2026-07-13).** Ran `rejstrik.service.fetch_filing
  ("Budejovicky Budvar")` live against the real network (post Task 3). New
  API 403'd as expected; fell back to the legacy portal automatically.
  Output: `výroční zpráva [2025]`, year 2025, pdf_url =
  `https://or.justice.cz/ias/ui/vypis-sl-detail?dokument=92007187&
  subjektId=59981&spis=411891`, downloaded 5,192,176 bytes, verified
  `%PDF-1.7` magic bytes at the start of the saved file. Full
  find → list_filings → get_filing chain works live via the fallback.

### Task 5: `scripts/smoke.py` canary section

**Files:** `scripts/smoke.py`, `tests/test_smoke.py` (new or existing —
check first)

- [ ] Step 1: Check whether `tests/test_smoke.py` already exists; if not,
  create it. Write a failing offline test asserting `scripts/smoke.py`
  defines a `canary()` (or `canary_endpoints()`) callable that the module
  exposes, and that it's referenced from `main()` — test this via
  source-text or `ast` inspection / import + `hasattr`, no network calls.
- [ ] Step 2: Implement `canary()` in `smoke.py`: does two lightweight
  direct `httpx.get()` calls (short timeout, e.g. 10s) — one to the new API
  base, one to `or.justice.cz` search — and prints one PASS/BLOCKED line
  per endpoint (status code, no exception raised out of `canary()` even on
  network failure — catch and report as BLOCKED). Call `canary()` at the
  start of `main()`.
- [ ] Step 3: Verify — `python -m pytest tests/test_smoke.py -q` green
  (offline). Do not run `scripts/smoke.py` itself in the automated suite.
- [ ] Step 4: Commit: `feat(smoke): add endpoint canary section for both
  filings portals`.

### Task 6: Scheduled canary GitHub Actions workflow (optional, include since cheap)

**Files:** `.github/workflows/canary.yml`

- [ ] Step 1: Add a workflow triggered on `schedule` (weekly, e.g. `cron:
  "0 6 * * 1"`) and `workflow_dispatch`, that checks out, installs deps,
  and runs a small inline script (or `python -c` block) calling
  `scripts.smoke.canary()` directly, exiting non-zero if both endpoints are
  BLOCKED. Keep it separate from `ci.yml` (this is the one permitted
  live-network CI touchpoint per CLAUDE.md/spec, clearly isolated).
  Auto-filing an issue on failure is a nice-to-have — leave a `TODO` comment
  in the workflow noting it's not implemented in this stage rather than
  building it now (scope control).
- [ ] Step 2: No automated test for this (workflow YAML isn't exercised by
  pytest); sanity-check with `python -c "import yaml;
  yaml.safe_load(open('.github/workflows/canary.yml'))"` if `pyyaml` is
  available, else visually verify syntax.
- [ ] Step 3: Commit: `ci: add weekly filings-portal canary workflow`.

### Task 7: Full verification + wrap-up

- [ ] Step 1: `ruff check src/ tests/ && ruff format --check src/ tests/ &&
  python -m pytest -q` — all green.
- [ ] Step 2: Update this plan file's Task 4 with the live acceptance
  result if not already done.
- [ ] Step 3: Final commit if anything is outstanding (e.g. plan file
  updates).

## TODO for human judgment

- Task 6's auto-issue-filing on canary failure is deliberately deferred
  (scope control) — a human should decide whether to add
  `peter-evans/create-issue-from-file` or similar, and to whom it should
  notify.
- If the new API's 403 turns out to be a temporary WAF tuning rather than a
  durable policy, a human should re-run the live investigation
  periodically; the canary (Task 5/6) is the mechanism for noticing this
  automatically.
