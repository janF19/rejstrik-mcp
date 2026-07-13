# Stage A: Filings Live Again — Legacy Portal Fallback + Endpoint Canary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the keyless find → list_filings → get_filing → analyze flow by adding an `or.justice.cz` legacy-portal fallback to `list_filings()` when the new `verejnerejstriky.msp.gov.cz` JSON API returns a 403 block, plus an endpoint canary in the smoke script so the block never silently rots again.

**Architecture:** `list_filings()` keeps the new JSON API as the primary path. On a **403-only** ("block-shaped") failure it falls back to scraping the legacy `or.justice.cz` portal: search by IČO → `parse_subject_id` → Sbírka listin page → `parse_deeds` → `list[Filing]`. Any other failure (404, timeout, 5xx) surfaces as its own error. When both portals fail, a typed `FilingsUnavailable` error names both portals and the manual URL. Legacy HTML parsers are re-tuned against **real captured fixtures**, with the three CSS selectors isolated into named constants so re-tuning is a one-line change. `load_pdf()` already works from `filing.pdf_url` for both URL families. `scripts/smoke.py` gains an endpoint-canary section printing one PASS/BLOCKED line per portal.

**Tech Stack:** Python 3.12, httpx (retrying client via `rejstrik.core.http.make_client`), selectolax (`HTMLParser`), pydantic v2 (`Filing` model), pytest + respx (offline HTTP mocking), ruff.

## Global Constraints

- **Ships as v0.4.1** — bump `src/rejstrik/__init__.py` `__version__` and `pyproject.toml` `version` from `0.4.0` to `0.4.1`; update `tests/test_smoke.py::test_version_exposed`.
- **Tests are offline and key-free.** No live network in the test suite. Mock all HTTP with `respx`. Live network belongs only in `scripts/smoke.py`.
- **No proxy/fingerprint evasion.** Honest UA only (`rejstrik.core.http.USER_AGENT`). Do not add curl-impersonate, residential proxies, or header-spoofing tricks.
- **Fallback triggers on 403 only.** 404, timeout, and 5xx surface as their own errors — they must NOT trigger the legacy fallback.
- **Filing IDs are per-portal.** Do not translate document IDs between portals. IDs returned by `list_filings` in a given portal mode are valid inputs to `get_filing` in that same mode.
- **Verification gate, every task:** `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` must pass before commit.
- **TDD order, every code task:** write failing test → run it, watch it fail → minimal implementation → run it, watch it pass → commit.

---

## File Structure

- `src/rejstrik/filings/justice.py` — MODIFY. Add `FilingsUnavailable` error, extract `_fetch_new_api()` and `_fetch_legacy()` helpers, add legacy search/deeds URL constants, isolate `parse_deeds` selectors into named constants, rewrite the fallback chain in `list_filings()`.
- `tests/filings/test_justice.py` — MODIFY. Add fallback-chain tests (403→legacy, 404 surfaces, both-fail raises), re-point parser tests at real Budvar fixtures.
- `tests/fixtures/justice/search_00514152.html` — CREATE. Real captured `or.justice.cz` IČO search results page for Budvar (00514152).
- `tests/fixtures/justice/deeds_00514152.html` — CREATE. Real captured `or.justice.cz` Sbírka listin page for Budvar.
- `tests/fixtures/justice/block_403.html` — CREATE. The 403 block page HTML the new portal returns (for the block-page fallback test).
- `tests/documents/test_source.py` — CREATE. Regression test that `load_pdf` handles the legacy `or.justice.cz` download URL family.
- `scripts/smoke.py` — MODIFY. Add `endpoint_canary()` and call it; print one PASS/BLOCKED line per portal.
- `tests/test_smoke.py` — MODIFY. Version bump + structural (offline) assertion that the canary section exists.
- `src/rejstrik/__init__.py`, `pyproject.toml` — MODIFY. Version bump to 0.4.1.
- `.github/workflows/endpoint-canary.yml` — CREATE (Task 8, optional). Weekly + `workflow_dispatch` canary that runs ONLY the canary, opens/updates an issue on failure.

---

## Task 1: Live investigation + capture real fixtures

This task is a data-capture / investigation task (per the spec's time-boxed live investigation). It produces the real HTML fixtures the parser tasks depend on, and records the investigation outcome in this plan. **No production code changes here.** It requires live network on the dev machine.

**Files:**
- Create: `tests/fixtures/justice/search_00514152.html`
- Create: `tests/fixtures/justice/deeds_00514152.html`
- Create: `tests/fixtures/justice/block_403.html`

**Interfaces:**
- Consumes: nothing.
- Produces: three fixture files used by Tasks 3, 4, and 6.

- [ ] **Step 1: Confirm the new-portal block and capture the 403 body**

Run (network required):

```bash
curl -sS -D - -o tests/fixtures/justice/block_403.html \
  -A "rejstrik-mcp/0.4 (+https://github.com/janF19/rejstrik-mcp)" \
  "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152" | head -20
```

Expected: an `HTTP/2 403` (or `HTTP/1.1 403`) status line at the edge, and `tests/fixtures/justice/block_403.html` written with the block page body. If the status is NOT 403 (e.g. the API now returns 200 JSON), record that in Step 4 and STOP — the block has lifted and the fallback design's primary path already works; the remaining fallback tasks still ship (fallback is kept regardless), but note the changed reality.

- [ ] **Step 2: Capture the legacy IČO search page**

Run (network required):

```bash
curl -sS -o tests/fixtures/justice/search_00514152.html \
  -A "rejstrik-mcp/0.4 (+https://github.com/janF19/rejstrik-mcp)" \
  "https://or.justice.cz/ias/ui/rejstrik-firma.vysledky?ico=00514152&jenPlatne=PLATNE"
```

Expected: HTTP 200, an HTML file that contains a link with `subjektId=` in its href (this is what `parse_subject_id` extracts). Verify with:

```bash
grep -o 'subjektId=[0-9]*' tests/fixtures/justice/search_00514152.html | head -1
```

Expected: at least one `subjektId=<digits>` match printed. If empty, the search URL shape changed — open `https://or.justice.cz/ias/ui/rejstrik-$firma?ico=00514152` in a plain browser, complete the search, and save the resulting results page (View Source) to the fixture path; re-run the grep.

- [ ] **Step 3: Capture the legacy Sbírka listin (deeds) page**

Using the `subjektId` value printed in Step 2 (call it `<SID>`), run:

```bash
curl -sS -o tests/fixtures/justice/deeds_00514152.html \
  -A "rejstrik-mcp/0.4 (+https://github.com/janF19/rejstrik-mcp)" \
  "https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId=<SID>"
```

Expected: HTTP 200, an HTML file listing filed documents. Verify it contains download links and at least one accounting-statement row:

```bash
grep -ic 'download' tests/fixtures/justice/deeds_00514152.html
grep -io 'ú[cč]etní záv\|ucetni zav\|Ú[CČ]ETNÍ' tests/fixtures/justice/deeds_00514152.html | head -1
```

Expected: the first command prints a non-zero count; the second prints at least one match (Budvar files annual accounts). Trim the fixture to the results container if it is enormous (>200 KB), but keep the full list-section markup intact.

- [ ] **Step 4: Record the investigation outcome in this plan**

Append a short "## Investigation outcome (2026-07-13)" section to the BOTTOM of this plan file documenting, in 3–6 lines: (a) new-portal status observed in Step 1 (403 at edge / other); (b) whether a working request shape for the new API was found (per spec §1 — if yes, note it becomes the primary path but the fallback still ships); (c) the exact legacy search URL and deeds URL that worked; (d) the CSS structure of a deed row in the captured deeds fixture (the tag/class wrapping each document, the node holding the title text, and the anchor holding the download href) — these three selectors feed Task 3's constants.

- [ ] **Step 5: Verify the fixtures exist and are non-empty**

Run:

```bash
wc -c tests/fixtures/justice/search_00514152.html tests/fixtures/justice/deeds_00514152.html tests/fixtures/justice/block_403.html
```

Expected: three files, each > 0 bytes (the two `or.justice.cz` pages should each be several KB).

- [ ] **Step 6: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add tests/fixtures/justice/search_00514152.html \
        tests/fixtures/justice/deeds_00514152.html \
        tests/fixtures/justice/block_403.html \
        docs/superpowers/plans/2026-07-13-stage-a-implementation.md
git commit -m "test: capture real or.justice.cz + block-page fixtures for stage a"
```

Expected: gate passes (no code changed yet), commit created.

---

## Task 2: Typed `FilingsUnavailable` error + extract new-API fetch helper

Refactor the current single-path `list_filings` so the new-API call lives in its own helper and a typed error exists for the "both portals failed" case. Behavior is unchanged in this task (the existing `test_list_filings_uses_new_sbirka_listin_api` must stay green).

**Files:**
- Modify: `src/rejstrik/filings/justice.py`
- Test: `tests/filings/test_justice.py`

**Interfaces:**
- Consumes: `make_client` (`rejstrik.core.http`), `Filing` (`rejstrik.filings.models`).
- Produces:
  - `class FilingsUnavailable(Exception)` — raised when both portals fail.
  - `_fetch_new_api(ico: str, client: httpx.Client) -> list[Filing]` — GETs the new JSON API, calls `raise_for_status()`, returns `parse_filings_api(resp.json())`. `ico` is already normalized (leading zeros stripped) by the caller.

- [ ] **Step 1: Write the failing test**

Add to `tests/filings/test_justice.py`:

```python
def test_filings_unavailable_is_an_exception():
    from rejstrik.filings.justice import FilingsUnavailable

    err = FilingsUnavailable("both portals down")
    assert isinstance(err, Exception)
    assert "both portals down" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/filings/test_justice.py::test_filings_unavailable_is_an_exception -v`
Expected: FAIL with `ImportError: cannot import name 'FilingsUnavailable'`.

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/filings/justice.py`, add the error class after the imports (below `_YEAR_RE`) and extract the new-API fetch into a helper. Add:

```python
class FilingsUnavailable(Exception):
    """Raised when both the new portal and the legacy portal fail to serve filings."""


def _fetch_new_api(ico: str, client: httpx.Client) -> list[Filing]:
    resp = client.get(_NEW_FILINGS_URL.format(ico=ico))
    resp.raise_for_status()
    return parse_filings_api(resp.json())
```

Then rewrite `list_filings` to call the helper (keep behavior identical for now):

```python
def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Primary path is the verejnerejstriky.msp.gov.cz JSON API. The endpoint
    expects the numeric IČO without leading zeroes.
    """
    ico = ico.strip().zfill(8).lstrip("0") or "0"
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        return _fetch_new_api(ico, client)
    finally:
        if own_client:
            client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: PASS — `test_filings_unavailable_is_an_exception` and the pre-existing `test_list_filings_uses_new_sbirka_listin_api` both green.

- [ ] **Step 5: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py
git commit -m "refactor: extract _fetch_new_api helper + add FilingsUnavailable error"
```

Expected: gate passes, commit created.

---

## Task 3: Re-tune legacy parsers against the real Budvar fixtures

Point the parser tests at the real captured fixtures and isolate `parse_deeds`'s three CSS selectors into named constants so re-tuning to real HTML is a one-line change per selector. `parse_subject_id` already extracts `subjektId=` from any href and needs no change beyond a real-fixture test.

**Files:**
- Modify: `src/rejstrik/filings/justice.py`
- Modify: `tests/filings/test_justice.py`

**Interfaces:**
- Consumes: fixtures from Task 1 (`search_00514152.html`, `deeds_00514152.html`); `Filing`, `classify_financial`.
- Produces:
  - Module constants `_DEED_ROW_SEL`, `_DEED_TITLE_SEL`, `_DEED_LINK_SEL` (strings) used by `parse_deeds`.
  - `parse_deeds(html: str, base_url: str = _BASE_URL) -> list[Filing]` — unchanged signature; sort order = financial-first then year desc.

- [ ] **Step 1: Write the failing tests against the real fixtures**

In `tests/filings/test_justice.py`, add the real-fixture paths near the existing `FIXTURES` block:

```python
REAL_SEARCH_HTML = (FIXTURES / "search_00514152.html").read_text(encoding="utf-8")
REAL_DEEDS_HTML = (FIXTURES / "deeds_00514152.html").read_text(encoding="utf-8")
```

Add:

```python
def test_parse_subject_id_from_real_search_page():
    subject_id = parse_subject_id(REAL_SEARCH_HTML)
    assert subject_id is not None
    assert subject_id.isdigit()


def test_parse_deeds_from_real_page_invariants():
    filings = parse_deeds(REAL_DEEDS_HTML)

    # Real Budvar page lists multiple filed documents.
    assert len(filings) >= 3, f"expected several filings, got {len(filings)}"

    # Every download URL resolves to an absolute or.justice.cz link.
    for f in filings:
        assert f.pdf_url.startswith("https://or.justice.cz/"), (
            f"expected absolute or.justice.cz URL, got: {f.pdf_url}"
        )

    # Budvar files annual accounts -> at least one financial statement,
    # and financial statements sort first.
    assert any(f.is_financial_statement for f in filings)
    assert filings[0].is_financial_statement is True

    # Financial statements are sorted by year descending (None last).
    fin_years = [f.year for f in filings if f.is_financial_statement and f.year]
    assert fin_years == sorted(fin_years, reverse=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/filings/test_justice.py::test_parse_deeds_from_real_page_invariants tests/filings/test_justice.py::test_parse_subject_id_from_real_search_page -v`
Expected: `test_parse_deeds_from_real_page_invariants` FAILS (the synthetic `div.document-row` / `span.document-title` selectors do not match the real HTML, so `parse_deeds` returns `[]` and the `len >= 3` assertion fails). `test_parse_subject_id_from_real_search_page` may already PASS (the regex is structure-agnostic) — that is fine.

- [ ] **Step 3: Isolate the selectors and re-tune them to the real HTML**

In `src/rejstrik/filings/justice.py`, add three module constants above `parse_deeds` (below `_YEAR_RE`). Set their values to the selectors you identified from the real deeds fixture in Task 1 Step 4. The values below are the starting point (they match the synthetic fixture); replace each with the real selector observed in `deeds_00514152.html`:

```python
# Sbírka listin deed-row selectors (verified against or.justice.cz 2026-07-13).
# Re-tune these three if the portal HTML changes; parse_deeds needs no other edit.
_DEED_ROW_SEL = "div.document-row"       # each filed document row
_DEED_TITLE_SEL = "span.document-title"  # node holding the human-readable title
_DEED_LINK_SEL = "a[href]"               # anchor holding the download href
```

Rewrite `parse_deeds` to use the constants (logic otherwise identical to today):

```python
def parse_deeds(html: str, base_url: str = _BASE_URL) -> list[Filing]:
    """
    Parse the Sbírka listin page and return a sorted list of Filing objects.

    Sorting: financial statements first, then by year descending (None last).
    """
    tree = HTMLParser(html)
    filings: list[Filing] = []

    for row in tree.css(_DEED_ROW_SEL):
        title_node = row.css_first(_DEED_TITLE_SEL)
        link_node = row.css_first(_DEED_LINK_SEL)
        if title_node is None or link_node is None:
            continue

        title = (title_node.text(strip=True) or "").strip()
        href = (link_node.attributes.get("href") or "").strip()
        if not title or not href:
            continue

        if href.startswith("/"):
            pdf_url = base_url.rstrip("/") + href
        elif href.startswith("http"):
            pdf_url = href
        else:
            pdf_url = base_url.rstrip("/") + "/" + href

        year_m = _YEAR_RE.search(title)
        year = int(year_m.group(0)) if year_m else None

        filings.append(
            Filing(
                title=title,
                year=year,
                pdf_url=pdf_url,
                is_financial_statement=classify_financial(title),
            )
        )

    if not filings and len(html) > 1024:
        logging.warning(
            "parse_deeds: no documents found — re-tune _DEED_ROW_SEL/_DEED_TITLE_SEL/"
            "_DEED_LINK_SEL against current or.justice.cz HTML"
        )

    filings.sort(key=lambda f: (not f.is_financial_statement, -(f.year or 0)))
    return filings
```

Now open `tests/fixtures/justice/deeds_00514152.html`, read the actual row markup, and set `_DEED_ROW_SEL`, `_DEED_TITLE_SEL`, `_DEED_LINK_SEL` to selectors that select, respectively: each document row, the title-text node inside it, and the download anchor inside it. (If the real page nests the title directly in the row with no dedicated span, `_DEED_TITLE_SEL` may equal `_DEED_ROW_SEL`; if the row is a `<tr>`, use `tr` / the matching `td` / `a[href]`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: all tests PASS, including `test_parse_deeds_from_real_page_invariants`, the real search-page test, and the pre-existing synthetic tests. If the synthetic `test_parse_deeds_extracts_filings_with_absolute_urls` now fails because the real selectors no longer match the synthetic fixture, DELETE that synthetic test and its `DEEDS_HTML`/`SUBJECT_HTML` constants if unused — the real fixtures supersede them (note the deletion in the commit message).

- [ ] **Step 5: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py
git commit -m "fix: re-tune parse_deeds selectors against real or.justice.cz HTML"
```

Expected: gate passes, commit created.

---

## Task 4: Legacy fallback chain in `list_filings`

Add `_fetch_legacy()` and wire the 403-only fallback into `list_filings`. On a 403 from the new API, scrape `or.justice.cz`. If the legacy path also fails (or yields nothing), raise `FilingsUnavailable` naming both portals and the manual URL. 404 / timeout / 5xx from the new API propagate unchanged (no fallback).

**Files:**
- Modify: `src/rejstrik/filings/justice.py`
- Test: `tests/filings/test_justice.py`

**Interfaces:**
- Consumes: `_fetch_new_api`, `parse_subject_id`, `parse_deeds`, `FilingsUnavailable`, `make_client`.
- Produces:
  - Legacy URL constants `_LEGACY_SEARCH_URL`, `_LEGACY_DEEDS_URL`.
  - `_fetch_legacy(ico_padded: str, client: httpx.Client) -> list[Filing]` — GETs the legacy search page (8-digit IČO), parses the `subjektId`, GETs the deeds page, returns `parse_deeds(...)`. Raises `FilingsUnavailable` if the subject id cannot be found.
  - `list_filings(ico, client=None)` — new-API-first, 403→legacy fallback.

- [ ] **Step 1: Write the failing tests**

Add to `tests/filings/test_justice.py` (imports at top: `import pytest`, and extend the justice import line to include `FilingsUnavailable`). The legacy URLs used in mocks must match the constants defined in Step 3:

```python
import pytest

_LEGACY_SEARCH = "https://or.justice.cz/ias/ui/rejstrik-firma.vysledky"
_LEGACY_DEEDS = "https://or.justice.cz/ias/ui/vypis-sl-firma"


@respx.mock
def test_list_filings_falls_back_to_legacy_on_403():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(403, html="blocked"))
    respx.get(_LEGACY_SEARCH).mock(return_value=httpx.Response(200, html=REAL_SEARCH_HTML))
    respx.get(_LEGACY_DEEDS).mock(return_value=httpx.Response(200, html=REAL_DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 3
    assert filings[0].is_financial_statement is True
    assert all(f.pdf_url.startswith("https://or.justice.cz/") for f in filings)


@respx.mock
def test_list_filings_does_not_fall_back_on_404():
    route = respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(404))
    legacy = respx.get(_LEGACY_SEARCH).mock(return_value=httpx.Response(200, html=REAL_SEARCH_HTML))

    client = httpx.Client()
    with pytest.raises(httpx.HTTPStatusError):
        list_filings("00514152", client=client)
    client.close()

    assert route.called
    assert not legacy.called, "404 must NOT trigger the legacy fallback"


@respx.mock
def test_list_filings_raises_filings_unavailable_when_both_fail():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(403, html="blocked"))
    # Legacy search returns a page with no subjektId link -> legacy path fails.
    respx.get(_LEGACY_SEARCH).mock(return_value=httpx.Response(200, html="<html>no results</html>"))

    client = httpx.Client()
    with pytest.raises(FilingsUnavailable) as excinfo:
        list_filings("00514152", client=client)
    client.close()

    msg = str(excinfo.value)
    assert "or.justice.cz" in msg
    assert "verejnerejstriky.msp.gov.cz" in msg
    assert "ico=00514152" in msg
```

Also extend the existing import line to:

```python
from rejstrik.filings.justice import (
    FilingsUnavailable,
    list_filings,
    parse_deeds,
    parse_subject_id,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/filings/test_justice.py -k "fall_back or 404 or filings_unavailable" -v`
Expected: FAIL — `test_list_filings_falls_back_to_legacy_on_403` fails because the current `list_filings` lets the 403 raise instead of falling back; the "both fail" test fails for the same reason. (`test_list_filings_does_not_fall_back_on_404` may already pass, since no fallback exists yet — it locks in the behavior.)

- [ ] **Step 3: Write the implementation**

In `src/rejstrik/filings/justice.py`, add the legacy URL constants near the top (below `_NEW_DOCUMENT_URL`). Use the exact URLs verified in Task 1; the defaults below match the Task 1 capture commands:

```python
_LEGACY_SEARCH_URL = _BASE_URL + "/ias/ui/rejstrik-firma.vysledky"
_LEGACY_DEEDS_URL = _BASE_URL + "/ias/ui/vypis-sl-firma"
_MANUAL_URL = "https://or.justice.cz/ias/ui/rejstrik-$firma?ico={ico}"
```

Add `_fetch_legacy`:

```python
def _fetch_legacy(ico_padded: str, client: httpx.Client) -> list[Filing]:
    """Scrape the pre-migration or.justice.cz portal. `ico_padded` is 8 digits."""
    search = client.get(
        _LEGACY_SEARCH_URL, params={"ico": ico_padded, "jenPlatne": "PLATNE"}
    )
    search.raise_for_status()
    subject_id = parse_subject_id(search.text)
    if not subject_id:
        raise FilingsUnavailable(
            "Both portals failed: verejnerejstriky.msp.gov.cz returned 403 and "
            "or.justice.cz returned no subject for this IČO. The registry may be "
            f"blocking automated access. Try manually: {_MANUAL_URL.format(ico=ico_padded)}"
        )
    deeds = client.get(_LEGACY_DEEDS_URL, params={"subjektId": subject_id})
    deeds.raise_for_status()
    return parse_deeds(deeds.text)
```

Rewrite `list_filings` to add the 403-only fallback:

```python
def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Primary path is the verejnerejstriky.msp.gov.cz JSON API. On a 403 block
    at that portal, fall back to scraping the legacy or.justice.cz portal.
    Non-block failures (404, timeout, 5xx) propagate unchanged.
    """
    ico_stripped = ico.strip().zfill(8).lstrip("0") or "0"
    ico_padded = ico.strip().zfill(8)
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        try:
            return _fetch_new_api(ico_stripped, client)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            try:
                return _fetch_legacy(ico_padded, client)
            except FilingsUnavailable:
                raise
            except Exception as legacy_exc:
                raise FilingsUnavailable(
                    "Both portals failed: verejnerejstriky.msp.gov.cz returned 403 "
                    f"and or.justice.cz failed ({legacy_exc!r}). The registry may be "
                    "blocking automated access. Try manually: "
                    f"{_MANUAL_URL.format(ico=ico_padded)}"
                ) from legacy_exc
    finally:
        if own_client:
            client.close()
```

Note: the "both fail" message must contain both hostnames and `ico=<padded>` (the manual URL embeds `?ico=`), satisfying the test's substring assertions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: all tests PASS, including the three new fallback tests.

- [ ] **Step 5: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py
git commit -m "feat: or.justice.cz legacy fallback in list_filings on 403 block"
```

Expected: gate passes, commit created.

---

## Task 5: Verify `load_pdf` handles the legacy download URL family

`load_pdf` already fetches from `filing.pdf_url` for any host. Add a regression test locking in that a legacy `or.justice.cz` download URL is fetched and wrapped in a `PdfSource` (redirects handled by the retrying client's `follow_redirects=True`). This guards the Filing → PDF handoff for the fallback path.

**Files:**
- Create: `tests/documents/test_source.py`
- (No production change expected — this is a regression guard. If it fails, fix `load_pdf`.)

**Interfaces:**
- Consumes: `load_pdf`, `PdfSource` (`rejstrik.documents.source`), `Filing` (`rejstrik.filings.models`).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Create `tests/documents/test_source.py`:

```python
import httpx
import respx

from rejstrik.documents.source import load_pdf
from rejstrik.filings.models import Filing

_LEGACY_PDF = "https://or.justice.cz/ias/content/download?id=99999999"


@respx.mock
def test_load_pdf_fetches_legacy_or_justice_url():
    respx.get(_LEGACY_PDF).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 legacy bytes",
            headers={"content-type": "application/pdf"},
        )
    )
    filing = Filing(title="Účetní závěrka 2022", year=2022, pdf_url=_LEGACY_PDF)

    client = httpx.Client()
    source = load_pdf(filing, client=client)
    client.close()

    assert source.data == b"%PDF-1.4 legacy bytes"
    assert source.filename == "filing.pdf"
    assert len(source.sha256) == 64
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `python -m pytest tests/documents/test_source.py -v`
Expected: the test should PASS on the first run because `load_pdf` is already host-agnostic. If it PASSES, that is the intended outcome — this is a regression guard, and its value is being committed. If it FAILS, `load_pdf` has a host assumption to fix in `src/rejstrik/documents/source.py`; make the minimal change to fetch any `https://` URL, then re-run until green.

- [ ] **Step 3: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add tests/documents/test_source.py
git commit -m "test: guard load_pdf for legacy or.justice.cz download URLs"
```

Expected: gate passes, commit created.

---

## Task 6: Endpoint canary in `scripts/smoke.py` + version bump to 0.4.1

Add an endpoint-canary section to the smoke script that hits both portals and prints one `CANARY <portal>: PASS|BLOCKED` line each, run before releases (per CLAUDE.md). Add an offline structural test in `tests/test_smoke.py` asserting the canary section exists, and bump the version to 0.4.1.

**Files:**
- Modify: `scripts/smoke.py`
- Modify: `tests/test_smoke.py`
- Modify: `src/rejstrik/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `make_client` (`rejstrik.core.http`).
- Produces: `endpoint_canary() -> None` in `scripts/smoke.py`, called from `main()` before the numbered steps.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_smoke.py` to bump the version assertion and add an offline structural canary assertion (reads the script text — no network, no import of the live script):

```python
from pathlib import Path

import rejstrik


def test_version_exposed():
    assert rejstrik.__version__ == "0.4.1"


def test_smoke_has_endpoint_canary_section():
    text = Path(__file__).parent.parent.joinpath("scripts", "smoke.py").read_text(
        encoding="utf-8"
    )
    assert "def endpoint_canary" in text
    assert "CANARY" in text
    # Both portals must be probed by the canary.
    assert "verejnerejstriky.msp.gov.cz" in text
    assert "or.justice.cz" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `test_version_exposed` fails (still `0.4.0`) and `test_smoke_has_endpoint_canary_section` fails (no `endpoint_canary` in the script yet).

- [ ] **Step 3: Bump the version**

In `src/rejstrik/__init__.py` change `__version__ = "0.4.0"` to `__version__ = "0.4.1"`.
In `pyproject.toml` change `version = "0.4.0"` to `version = "0.4.1"`.

- [ ] **Step 4: Add the canary to `scripts/smoke.py`**

Add this import near the top of `scripts/smoke.py` (with the other imports):

```python
from rejstrik.core.http import make_client
```

Add the `endpoint_canary` function above `main()`:

```python
def endpoint_canary() -> None:
    """Probe both filings portals and print one PASS/BLOCKED line each.

    Run before releases. A BLOCKED new portal is expected as of 2026-07-13;
    a BLOCKED or.justice.cz means the fallback is dead and the flagship flow
    is down — investigate immediately.
    """
    probes = [
        (
            "verejnerejstriky.msp.gov.cz",
            "https://verejnerejstriky.msp.gov.cz/api/sbirka-listin/subjekty/514152",
        ),
        (
            "or.justice.cz",
            "https://or.justice.cz/ias/ui/rejstrik-firma.vysledky?ico=00514152&jenPlatne=PLATNE",
        ),
    ]
    client = make_client()
    try:
        for name, url in probes:
            try:
                resp = client.get(url)
                status = "PASS" if resp.status_code == 200 else "BLOCKED"
                print(f"CANARY {name}: {status} (HTTP {resp.status_code})")
            except Exception as exc:  # noqa: BLE001 - canary reports any failure
                print(f"CANARY {name}: BLOCKED ({exc!r})")
    finally:
        client.close()
```

Call it at the start of `main()`, before `[1/5]`:

```python
def main() -> None:
    endpoint_canary()
    query = sys.argv[1] if len(sys.argv) > 1 else "Budejovicky Budvar"
    company = find_company(query)
    ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add scripts/smoke.py tests/test_smoke.py src/rejstrik/__init__.py pyproject.toml
git commit -m "feat: endpoint canary in smoke script; bump to v0.4.1"
```

Expected: gate passes, commit created.

---

## Task 7: Full-suite verification of the restored flow

A final integration checkpoint: confirm the whole offline suite is green and (network permitting on the dev machine) that the live acceptance criterion passes.

**Files:** none (verification only).

- [ ] **Step 1: Run the full offline gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green, no lint/format errors.

- [ ] **Step 2: Run the live smoke + canary (network required; not CI)**

Run: `python scripts/smoke.py "Budejovicky Budvar"`
Expected: two `CANARY ...:` lines print first (new portal likely `BLOCKED`, `or.justice.cz` `PASS`), then `[1/5]`…`[5/5]` complete and `SMOKE OK` prints — i.e. `rejstrik analyze "Budejovicky Budvar"` now completes live via the legacy portal. If the new portal canary shows `PASS`, the block lifted and the primary path served the flow; either way the flow must complete. If it does not complete, STOP and debug before proceeding (do not commit a broken acceptance).

- [ ] **Step 3: Commit nothing / note outcome**

No code change in this task. If Step 2 surfaced a real bug, fix it under the relevant earlier task's TDD cycle (failing test first) rather than patching here.

---

## Task 8 (Optional): Weekly endpoint-canary GitHub Actions workflow

Include only if cheap and the repo uses GitHub Actions. A scheduled workflow that runs ONLY the canary (not the full smoke), clearly separated from the offline test suite, and opens/updates an issue on failure. This is the single permitted live-network CI touchpoint.

**Files:**
- Create: `.github/workflows/endpoint-canary.yml`
- Modify: `scripts/smoke.py` (add a `--canary-only` entry path)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `endpoint_canary` from Task 6.
- Produces: `endpoint_canary()` exits non-zero when `or.justice.cz` is BLOCKED (so CI can fail and open an issue).

- [ ] **Step 1: Write the failing test for canary-only exit behavior**

Add to `tests/test_smoke.py`:

```python
def test_smoke_supports_canary_only_flag():
    text = Path(__file__).parent.parent.joinpath("scripts", "smoke.py").read_text(
        encoding="utf-8"
    )
    assert "--canary-only" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py::test_smoke_supports_canary_only_flag -v`
Expected: FAIL — no `--canary-only` handling yet.

- [ ] **Step 3: Add `--canary-only` handling to `scripts/smoke.py`**

Make `endpoint_canary()` return a bool (True = all PASS) and honor a `--canary-only` argument in `main()`:

```python
def endpoint_canary() -> bool:
    ...
    all_pass = True
    try:
        for name, url in probes:
            try:
                resp = client.get(url)
                ok = resp.status_code == 200
                print(f"CANARY {name}: {'PASS' if ok else 'BLOCKED'} (HTTP {resp.status_code})")
            except Exception as exc:  # noqa: BLE001
                ok = False
                print(f"CANARY {name}: BLOCKED ({exc!r})")
            all_pass = all_pass and ok
    finally:
        client.close()
    return all_pass
```

In `main()`, at the very top:

```python
def main() -> None:
    if "--canary-only" in sys.argv[1:]:
        ok = endpoint_canary()
        sys.exit(0 if ok else 1)
    endpoint_canary()
    query = ...
```

Note: the new-portal canary is expected to be BLOCKED today, which would fail CI. To keep the workflow signal meaningful (fail only when the fallback dies), have the workflow invoke a legacy-only check, OR relax `--canary-only` to exit non-zero only when `or.justice.cz` is BLOCKED. Implement the latter: track `legacy_ok` separately and `sys.exit(0 if legacy_ok else 1)` in the `--canary-only` branch.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Create the workflow**

Create `.github/workflows/endpoint-canary.yml`:

```yaml
name: endpoint-canary
on:
  schedule:
    - cron: "0 6 * * 1"  # Mondays 06:00 UTC
  workflow_dispatch: {}

permissions:
  contents: read
  issues: write

jobs:
  canary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - id: canary
        run: python scripts/smoke.py --canary-only
      - if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const title = "Endpoint canary: or.justice.cz fallback BLOCKED";
            const body = "The weekly endpoint canary reports the or.justice.cz legacy fallback is blocked. The keyless filings flow is likely down. See run: " + context.serverUrl + "/" + context.repo.owner + "/" + context.repo.repo + "/actions/runs/" + context.runId;
            const existing = await github.rest.issues.listForRepo({owner: context.repo.owner, repo: context.repo.repo, state: "open", labels: "canary"});
            if (existing.data.length === 0) {
              await github.rest.issues.create({owner: context.repo.owner, repo: context.repo.repo, title, body, labels: ["canary"]});
            } else {
              await github.rest.issues.createComment({owner: context.repo.owner, repo: context.repo.repo, issue_number: existing.data[0].number, body});
            }
```

- [ ] **Step 6: Run the gate and commit**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
git add scripts/smoke.py tests/test_smoke.py .github/workflows/endpoint-canary.yml
git commit -m "ci: weekly endpoint-canary workflow (legacy portal watchdog)"
```

Expected: gate passes, commit created.

---

## Self-Review

**Spec coverage:**
- §1 Live investigation first → Task 1 (capture + record outcome).
- §2 Fallback chain in `list_filings` (403→legacy) → Task 4; parser re-tuning against real fixtures → Tasks 1 + 3; `load_pdf` both URL families → Task 5; per-portal filing IDs (no cross-translation) → honored, no ID translation added (Global Constraints).
- §3 Honest typed error naming both portals + manual URL → Task 2 (`FilingsUnavailable`) + Task 4 (message content, asserted).
- §4 Canary in `scripts/smoke.py` → Task 6; optional scheduled workflow → Task 8.
- Not-in-scope (no evasion) → Global Constraints.
- Testing: offline fixtures (search / deeds / block 403) → Task 1; fallback on 403 not 404/timeout → Task 4; parser correctness + sort order → Task 3; `test_smoke.py` structural canary assertion → Task 6.
- Acceptance (`rejstrik analyze "Budejovicky Budvar"` completes live; per-portal status) → Task 7 Step 2.
- Ships as v0.4.1 → Task 6.

**Placeholder scan:** The only intentionally deferred values are the three `_DEED_*` selector constants (Task 3) and the exact captured HTML — these are inherently unknowable until Task 1's live capture, per the spec ("capture real HTML … and rewrite the parsers against them"). Task 3 gives a concrete starting value for each constant, an explicit procedure to set them from the fixture, and invariant-based tests that verify correctness without hard-coding portal-specific strings. No "TODO/handle edge cases/add validation" placeholders remain.

**Type consistency:** `FilingsUnavailable` (Task 2) is raised in Task 4 and imported in tests consistently. `_fetch_new_api(ico, client)` (Task 2) and `_fetch_legacy(ico_padded, client)` (Task 4) signatures match their call sites in `list_filings`. `parse_deeds`/`parse_subject_id` signatures unchanged. `endpoint_canary` returns `None` in Task 6 and is widened to `-> bool` in Task 8 (Task 8 is explicitly optional and self-contained; if skipped, Task 6's `-> None` stands).
