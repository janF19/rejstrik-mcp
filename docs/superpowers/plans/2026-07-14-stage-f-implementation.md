# Stage F: Hardening (v0.6.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the post-Stage-E audit's defects and robustness gaps so rejstrik-mcp ships cleanly as v0.6.1 — no broken README media, a fourth version location guarded, a graceful `estimate_valuation([])`, and a WAF-aware filings fallback.

**Architecture:** Six independent fixes plus a release bump, each landing as its own commit. Three are pure-Python behavior changes covered by offline TDD (valuation guard, version-sync guard, filings fallback, split-year parsing); three are non-tested edits to a manual script and the README; one is a version bump. No new runtime dependencies. Every code change follows failing-test-first where a behavior is testable.

**Tech Stack:** Python 3.11/3.12, pytest, respx (offline HTTP mocking), httpx, pydantic, ruff. Source under `src/rejstrik/`, tests under `tests/`.

## Global Constraints

- Tests are **offline and key-free**: mock HTTP with `respx`, never hit the network. Copied verbatim from CLAUDE.md.
- **No new runtime dependency** is introduced anywhere in Stage F (the first new runtime dep is deferred to Stage G).
- Follow **TDD**: failing test → minimal implementation → green → commit. One commit per fix.
- **Every task ends** with: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` (all green).
- `scripts/smoke.py` is **manual, network-using tooling — never in CI**; it has no unit tests.
- Czech identifiers in code/messages keep their diacritics (`Sbírka listin`, `IČO`) exactly as in the existing source.
- Stage F ships as **v0.6.1**; the version bump is the final task, after every fix is green.

---

### Task 1: `estimate_valuation([])` raises a helpful `ValueError` (F3)

**Files:**
- Modify: `src/rejstrik/analysis/valuation.py:42-51`
- Test: `tests/analysis/test_valuation.py`

**Interfaces:**
- Consumes: `estimate_valuation(statements: list[FinancialStatement], assumptions: ValuationAssumptions | None = None) -> ValuationEstimate` (existing signature — unchanged).
- Produces: same signature; now raises `ValueError` when `statements` is empty, matching the wording pattern used by `analyze_statements` in `service.py`.

- [ ] **Step 1: Write the failing test**

Append to `tests/analysis/test_valuation.py`:

```python
def test_valuation_empty_statements_raises_valueerror():
    with pytest.raises(
        ValueError, match="at least one FinancialStatement"
    ):
        estimate_valuation([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/analysis/test_valuation.py::test_valuation_empty_statements_raises_valueerror -v`
Expected: FAIL with `IndexError: list index out of range` (from `ordered[0]`), not `ValueError`.

- [ ] **Step 3: Write minimal implementation**

In `src/rejstrik/analysis/valuation.py`, add the guard as the first statement inside `estimate_valuation`, immediately after the `assumptions = assumptions or ValuationAssumptions()` line:

```python
def estimate_valuation(
    statements: list[FinancialStatement],
    assumptions: ValuationAssumptions | None = None,
) -> ValuationEstimate:
    assumptions = assumptions or ValuationAssumptions()
    if not statements:
        raise ValueError(
            "statements must contain at least one FinancialStatement "
            "(extract it from the PDF returned by get_filing)"
        )
    normalized = [normalize(s) for s in statements]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/test_valuation.py -v`
Expected: PASS (new test plus the four existing valuation tests).

- [ ] **Step 5: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/analysis/valuation.py tests/analysis/test_valuation.py
git commit -m "fix(valuation): raise ValueError on empty statements"
```

---

### Task 2: Guard the `__version__` dunder against drift (F2)

**Files:**
- Modify: `tests/test_version_sync.py`
- Modify: `README.md:171-173` (Releasing checklist — "three" → "four")
- No change to `src/rejstrik/__init__.py` (keep the hardcoded string `__version__ = "0.6.0"`).

**Interfaces:**
- Consumes: existing `_pyproject_version() -> str` helper in `tests/test_version_sync.py`; `rejstrik.__version__` (str).
- Produces: a new test `test_package_dunder_version_matches_pyproject` asserting `rejstrik.__version__ == _pyproject_version()`.

- [ ] **Step 1: Write the guard test**

Append to `tests/test_version_sync.py`:

```python
def test_package_dunder_version_matches_pyproject() -> None:
    import rejstrik

    assert rejstrik.__version__ == _pyproject_version()
```

- [ ] **Step 2: Run the test — it passes immediately (both are `0.6.0`)**

Run: `python -m pytest tests/test_version_sync.py::test_package_dunder_version_matches_pyproject -v`
Expected: PASS. This is a drift *guard*, so it holds today; there is no behavior to change.

- [ ] **Step 3: Prove the guard bites (red/green demonstration)**

Temporarily edit `src/rejstrik/__init__.py` to `__version__ = "9.9.9"`, then run:
`python -m pytest tests/test_version_sync.py::test_package_dunder_version_matches_pyproject -v`
Expected: FAIL (`assert '9.9.9' == '0.6.0'`).
Then **revert** `src/rejstrik/__init__.py` back to `__version__ = "0.6.0"` and re-run: PASS.

- [ ] **Step 4: Update the README Releasing checklist to four files**

In `README.md`, replace the numbered step 2 (currently lines 171-173):

Old:
```markdown
2. Bump `version` in **all three** metadata files so they agree:
   `pyproject.toml`, `server.json` (top-level **and** `packages[0].version`),
   and `mcpb/manifest.json`. `tests/test_version_sync.py` fails if they drift.
```

New:
```markdown
2. Bump `version` in **all four** places so they agree: `pyproject.toml`,
   `server.json` (top-level **and** `packages[0].version`), `mcpb/manifest.json`,
   and `src/rejstrik/__init__.py` (`__version__`). `tests/test_version_sync.py`
   fails if any of them drift.
```

- [ ] **Step 5: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (version_sync now has three tests).

- [ ] **Step 6: Commit**

```bash
git add tests/test_version_sync.py README.md
git commit -m "test(version): guard __init__.__version__ against drift; README says four files"
```

---

### Task 3: Broaden the legacy fallback to all block-shaped failures (F4)

**Files:**
- Modify: `src/rejstrik/filings/justice.py` (imports; add `_BlockShaped`; add `_fetch_new_filings`; rewrite `list_filings` body + docstring)
- Test: `tests/filings/test_justice.py`

**Interfaces:**
- Consumes: existing `_fetch_legacy_filings(ico_padded: str, client: httpx.Client) -> list[Filing] | None`; `parse_filings_api(data: dict) -> list[Filing]`; `RegistryBlockedError`.
- Produces:
  - `class _BlockShaped(Exception)` with a `.reason: str` attribute (private, internal-only).
  - `_fetch_new_filings(ico_stripped: str, client: httpx.Client) -> list[Filing]` — raises `_BlockShaped(reason)` on a WAF/edge block shape; re-raises `httpx.HTTPStatusError` for non-block statuses (e.g. 404).
  - `list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]` — unchanged signature; now falls back on 403, 429, 5xx, and non-JSON 2xx bodies.

**Block-shaped triggers (fallback-eligible):** HTTP 403, HTTP 429, HTTP 5xx (500–599), and a 2xx response whose body fails to parse as JSON.
**Propagate unchanged (no fallback):** HTTP 404 and any other non-block 4xx; connect/read timeouts and transport errors (`httpx.TimeoutException` / other `httpx.TransportError`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/filings/test_justice.py` (the file already imports `httpx`, `pytest`, `respx`, `RegistryBlockedError`, `list_filings`, and defines `SEARCH_HTML`, `DEEDS_HTML`, `_NEW_FILINGS_URL`, `_LEGACY_SEARCH_URL`, `_LEGACY_DEEDS_URL`):

```python
@respx.mock
def test_list_filings_falls_back_on_429():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(429, text="slow down"))
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90
    assert filings[0].pdf_url.startswith(
        "https://or.justice.cz/ias/ui/vypis-sl-detail?dokument="
    )


@respx.mock
def test_list_filings_falls_back_on_503():
    respx.get(_NEW_FILINGS_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90


@respx.mock
def test_list_filings_falls_back_on_challenge_html_200():
    # Azure Front Door interstitial: HTTP 200 but an HTML challenge body, not JSON.
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(
            200,
            html="<html><body>Checking your browser…</body></html>",
        )
    )
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    respx.get(_LEGACY_DEEDS_URL).mock(return_value=httpx.Response(200, text=DEEDS_HTML))

    client = httpx.Client()
    filings = list_filings("00514152", client=client)
    client.close()

    assert len(filings) >= 90


@respx.mock
def test_list_filings_does_not_fall_back_on_timeout():
    respx.get(_NEW_FILINGS_URL).mock(side_effect=httpx.ConnectTimeout("boom"))

    client = httpx.Client()
    try:
        with pytest.raises(httpx.ConnectTimeout):
            list_filings("00514152", client=client)
    finally:
        client.close()


@respx.mock
def test_registry_blocked_message_names_non_json_trigger():
    respx.get(_NEW_FILINGS_URL).mock(
        return_value=httpx.Response(
            200, html="<html><body>Checking your browser…</body></html>"
        )
    )
    respx.get(_LEGACY_SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<html><body>no results</body></html>")
    )

    client = httpx.Client()
    try:
        with pytest.raises(RegistryBlockedError) as exc_info:
            list_filings("00514152", client=client)
    finally:
        client.close()

    assert "non-JSON response" in str(exc_info.value)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/filings/test_justice.py -k "429 or 503 or challenge or timeout or non_json" -v`
Expected: the 429/503/challenge tests FAIL (currently only 403 triggers fallback, so a `JSONDecodeError`/`HTTPStatusError` propagates instead of returning filings); `non_json` FAILs (no `RegistryBlockedError`); `timeout` may already pass (timeouts already propagate) — that is fine, it locks the behavior in.

- [ ] **Step 3: Add the `json` import**

In `src/rejstrik/filings/justice.py`, add `import json` so the stdlib import block reads (ruff/isort keeps them alphabetical):

```python
import json
import logging
import re
```

- [ ] **Step 4: Add the internal block exception**

In `src/rejstrik/filings/justice.py`, immediately after the existing `RegistryBlockedError` class, add:

```python
class _BlockShaped(Exception):
    """Internal: a new-portal response that looks like an edge/WAF block.

    Block-shaped means fallback-eligible: HTTP 403/429/5xx, or a 2xx body that
    is not parseable JSON (a challenge/interstitial page). ``reason`` names the
    actual trigger so RegistryBlockedError messages stay honest.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
```

- [ ] **Step 5: Add the new-portal fetch helper**

In `src/rejstrik/filings/justice.py`, add this function directly above `list_filings` (after `_fetch_legacy_filings`):

```python
def _fetch_new_filings(ico_stripped: str, client: httpx.Client) -> list[Filing]:
    """Fetch from the new portal; raise _BlockShaped on a WAF/edge block shape.

    Non-block failures (404, other 4xx) re-raise as httpx.HTTPStatusError so
    they propagate unchanged. Timeouts/transport errors are not caught here and
    propagate to the caller.
    """
    resp = client.get(_NEW_FILINGS_URL.format(ico=ico_stripped))
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (403, 429) or 500 <= status <= 599:
            raise _BlockShaped(f"HTTP {status}") from exc
        raise
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise _BlockShaped("non-JSON response") from exc
    return parse_filings_api(data)
```

- [ ] **Step 6: Rewrite `list_filings` to use the helper and broadened fallback**

Replace the entire body of `list_filings` (from the `try:` on line ~170 through the `finally:` block) — and update the docstring — so the function reads:

```python
def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    """
    Fetch and return all Sbírka listin filings for a given IČO.

    Tries the new verejnerejstriky.msp.gov.cz JSON API first (numeric IČO
    without leading zeroes). On a block-shaped failure — HTTP 403, 429, any
    5xx, or a 2xx body that is not JSON (an Azure Front Door challenge page) —
    falls back to the legacy or.justice.cz HTML portal (IČO with leading
    zeroes). Non-block failures (404, timeouts, transport errors) from the new
    API propagate unchanged — they aren't evidence of a block.
    """
    ico_padded = ico.strip().zfill(8)
    ico_stripped = ico_padded.lstrip("0") or "0"
    own_client = client is None
    if own_client:
        client = make_client()

    try:
        try:
            return _fetch_new_filings(ico_stripped, client)
        except _BlockShaped as block:
            try:
                legacy_filings = _fetch_legacy_filings(ico_padded, client)
            except httpx.HTTPError:
                legacy_filings = None
            if legacy_filings is None:
                raise RegistryBlockedError(
                    f"Sbírka listin unreachable for IČO {ico_padded}: "
                    f"new portal (verejnerejstriky.msp.gov.cz) returned "
                    f"{block.reason} and the legacy portal (or.justice.cz) has "
                    f"no matching subject. The registry may be blocking "
                    f"automated access. Check manually: "
                    f"https://or.justice.cz/ias/ui/rejstrik-$firma?ico={ico_padded}"
                ) from block
            return legacy_filings
    finally:
        if own_client:
            client.close()
```

- [ ] **Step 7: Run the whole justice test module**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: PASS — the five new tests plus the existing ones. In particular `test_list_filings_falls_back_to_legacy_portal_on_403` and `test_list_filings_does_not_fall_back_on_404` and `test_list_filings_raises_registry_blocked_when_both_portals_fail` still pass (403 stays a trigger; the block message still contains `verejnerejstriky.msp.gov.cz`, `or.justice.cz`, and the manual-check URL — it now reads "returned HTTP 403").

- [ ] **Step 8: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py
git commit -m "fix(filings): fall back to legacy portal on 429/5xx/non-JSON blocks"
```

---

### Task 4: Split-year filing titles take the max year (F5)

**Files:**
- Modify: `src/rejstrik/filings/justice.py` (add `_max_year`; use it in `parse_deeds` and `parse_filings_api`)
- Test: `tests/filings/test_justice.py`

**Interfaces:**
- Consumes: existing `_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")`.
- Produces: `_max_year(title: str) -> int | None` — returns the **latest** 4-digit year found in `title`, or `None`. Used by both `parse_deeds` and `parse_filings_api`.

- [ ] **Step 1: Write the failing test**

Append to `tests/filings/test_justice.py`:

```python
def test_parse_filings_api_split_year_title_takes_max_year():
    from rejstrik.filings.justice import parse_filings_api

    data = {
        "vysledekdetail": {
            "prehledlistin": [
                {
                    "typlistiny": "účetní závěrka 2023/2024",
                    "detail": [
                        {
                            "obsah": {
                                "digitalnipodoba": {"documentid": "111222333"}
                            }
                        }
                    ],
                }
            ]
        }
    }

    filings = parse_filings_api(data)
    assert len(filings) == 1
    # The accounting period ends in the later year — take 2024, not 2023.
    assert filings[0].year == 2024
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/filings/test_justice.py::test_parse_filings_api_split_year_title_takes_max_year -v`
Expected: FAIL with `assert 2023 == 2024` (`_YEAR_RE.search` returns the first match).

- [ ] **Step 3: Add the `_max_year` helper**

In `src/rejstrik/filings/justice.py`, add directly below the `_YEAR_RE` definition (after line ~22):

```python
def _max_year(title: str) -> int | None:
    """Return the latest 4-digit year in *title* (the accounting period ends
    in the later year), or None if no year is present."""
    years = [int(m.group(0)) for m in _YEAR_RE.finditer(title)]
    return max(years) if years else None
```

- [ ] **Step 4: Use `_max_year` in `parse_deeds`**

In `parse_deeds`, replace:

```python
        year_m = _YEAR_RE.search(title)
        year = int(year_m.group(0)) if year_m else None
```

with:

```python
        year = _max_year(title)
```

- [ ] **Step 5: Use `_max_year` in `parse_filings_api`**

In `parse_filings_api`, replace the identical two lines:

```python
        year_m = _YEAR_RE.search(title)
        year = int(year_m.group(0)) if year_m else None
```

with:

```python
        year = _max_year(title)
```

- [ ] **Step 6: Run the justice tests**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: PASS — the new split-year test plus all existing ones (the existing titles use bracketed `[2024]` only, so `_max_year` still returns 2024; no regression).

- [ ] **Step 7: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py
git commit -m "fix(filings): take max year from split-year filing titles"
```

---

### Task 5: `scripts/smoke.py` derives the period year (F5)

**Files:**
- Modify: `scripts/smoke.py` (add `from datetime import date`; derive `base_year`; replace hardcoded `period_year=2024` / `period_year=2023`)

**Interfaces:**
- No public interface. `scripts/smoke.py` is manual tooling with no unit tests; `ruff check`/`pytest` do not cover `scripts/`, so verify with `py_compile`.

- [ ] **Step 1: Add the `date` import**

In `scripts/smoke.py`, add to the imports (top of file, after the module docstring, alphabetically before `import sys` in the stdlib block):

```python
from datetime import date
```

The resulting stdlib import block reads:
```python
from datetime import date
import sys
```

- [ ] **Step 2: Derive `base_year` from the fetched filing**

In `main()`, immediately after the `doc, _source = fetch_filing(company.ico)` call and its `print(...)` (around line 50), add:

```python
    base_year = doc.year or (date.today().year - 1)
```

- [ ] **Step 3: Replace the two hardcoded years**

In the `statements = [...]` list, replace `period_year=2024,` (the first `FinancialStatement`) with:

```python
            period_year=base_year,
```

and replace `period_year=2023,` (the second `FinancialStatement`) with:

```python
            period_year=base_year - 1,
```

- [ ] **Step 4: Verify the script still compiles**

Run: `python -m py_compile scripts/smoke.py`
Expected: no output, exit 0.

- [ ] **Step 5: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (unchanged — `scripts/` is not linted or tested; this confirms nothing else broke).

- [ ] **Step 6: Commit**

```bash
git add scripts/smoke.py
git commit -m "fix(smoke): derive period_year from filing instead of hardcoding"
```

---

### Task 6: README "See it work" — remove broken media, hide PyPI badge (F1)

**Files:**
- Modify: `README.md:3` (PyPI badge)
- Modify: `README.md:12-20` ("See it work" media embeds)

**Interfaces:** None (documentation only).

**Publish-status decision:** As of 2026-07-14 the package is not yet on PyPI (Stage E T5/T6 publish remains an open human task — see Task 8), so the PyPI badge renders "package not found". Comment it out with a restore note; keep the CI badge.

- [ ] **Step 1: Comment out the PyPI badge**

In `README.md`, replace line 3:

Old:
```markdown
[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/)
```

New:
```markdown
[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) <!-- PyPI badge hidden until first publish (Stage E T5/T6); restore this line: [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/) -->
```

- [ ] **Step 2: Replace the broken image embeds, keep the prose**

In `README.md`, replace the block from the `## See it work` heading through the "Reproduce the GIF" line (lines 12-20):

Old:
```markdown
## See it work

![Analyzing Budějovický Budvar's last 3 years of filings](docs/media/budvar-3year.gif)

The `analyze_company_card` report rendered in Claude Desktop:

![Report card in Claude Desktop](docs/media/report-card.png)

Reproduce the GIF with `scripts/record_demo.sh` (needs asciinema + agg).
```

New:
```markdown
## See it work

Demo media is being recorded (see `scripts/record_demo.sh`, which needs
asciinema + agg); meanwhile the walkthrough below shows the exact flow.
```

(The "Then ask: *…*" walkthrough paragraph immediately below is untouched — it stands on its own.)

- [ ] **Step 3: Confirm no `docs/media` references remain**

Run: `grep -n "docs/media" README.md`
Expected: no output (exit 1) — both broken embeds are gone.

- [ ] **Step 4: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (docs-only change).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(readme): drop broken demo embeds, hide PyPI badge until publish"
```

---

### Task 7: README drift note + "How it works" fallback mention (F5)

**Files:**
- Modify: `README.md` "How it works" code block (the `filings/` line, ~line 100)
- Modify: `README.md` "A Note On Real-World Drift" section (~lines 112-119)

**Interfaces:** None (documentation only).

- [ ] **Step 1: Mention the fallback in the "How it works" filings line**

In `README.md`, inside the `## How it works` fenced `text` block, replace:

```text
filings/   verejnerejstriky.msp.gov.cz Sbirka listin client
```

with:

```text
filings/   verejnerejstriky.msp.gov.cz Sbirka listin client
           (falls back to legacy or.justice.cz when the new portal is blocked)
```

- [ ] **Step 2: Extend the drift note with the AFD block + fallback + canary story**

In `README.md`, at the end of the `### A Note On Real-World Drift` paragraph, replace the final sentence:

Old:
```markdown
Registry, filings, insolvency, statutory-body, VAT, and ADIS
lookups are covered by fixtures/unit tests; live smoke testing verified the
registry/document analysis path against Budejovicky Budvar with OpenAI.
```

New:
```markdown
Registry, filings, insolvency, statutory-body, VAT, and ADIS
lookups are covered by fixtures/unit tests; live smoke testing verified the
registry/document analysis path against Budejovicky Budvar with OpenAI.

In July 2026 the new portal began returning Azure Front Door block responses
— 403/429/5xx and 200-with-challenge-HTML interstitials — to automated
clients. The filings client now treats all of these as block-shaped and falls
back to the legacy `or.justice.cz` portal, so a single blocked edge does not
break lookups. A `scripts/smoke.py` canary hits both portals directly and
prints PASS/BLOCKED per endpoint, so this drift is caught before a release
tag rather than in the field.
```

- [ ] **Step 3: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green (docs-only change).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): document AFD block, legacy fallback, and canary"
```

---

### Task 8: Bump version to v0.6.1 (release prep)

**Files:**
- Modify: `pyproject.toml` (`version`)
- Modify: `server.json` (top-level `version` **and** `packages[0].version`)
- Modify: `mcpb/manifest.json` (`version`)
- Modify: `src/rejstrik/__init__.py` (`__version__`)

**Interfaces:** None — coordinated constant bump across the four version locations guarded by `tests/test_version_sync.py`.

Do this task **only after Tasks 1–7 are all green.** All four locations currently read `0.6.0`.

- [ ] **Step 1: Bump `pyproject.toml`**

Change `version = "0.6.0"` → `version = "0.6.1"`.

- [ ] **Step 2: Bump `server.json` (both places)**

Change the top-level `"version": "0.6.0"` → `"0.6.1"` **and** `packages[0].version` `"0.6.0"` → `"0.6.1"`.

- [ ] **Step 3: Bump `mcpb/manifest.json`**

Change `"version": "0.6.0"` → `"0.6.1"`.

- [ ] **Step 4: Bump `src/rejstrik/__init__.py`**

Change `__version__ = "0.6.0"` → `__version__ = "0.6.1"`.

- [ ] **Step 5: Run the version-sync guard**

Run: `python -m pytest tests/test_version_sync.py -v`
Expected: PASS — all three tests (server.json, manifest.json, and the new `__version__` guard from Task 2) agree at `0.6.1`.

- [ ] **Step 6: Run the full verification**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py
git commit -m "chore(release): bump version to 0.6.1"
```

---

### Task 9: Stage F acceptance verification (no code)

**Files:** None.

- [ ] **Step 1: Confirm the acceptance criteria hold**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected — the full suite is green and demonstrates every Stage F acceptance item:
- a fixture-driven test exists for every new fallback trigger (429, 503, 200-non-JSON) — Task 3;
- `estimate_valuation([])` raises `ValueError` — Task 1;
- `test_version_sync.py` covers four locations (server.json, manifest.json, pyproject, `__version__`) — Task 2;
- README shows no broken images — Task 6 (`grep -n "docs/media" README.md` returns nothing).

- [ ] **Step 2: Optional pre-release live check (manual, not CI)**

If cutting the v0.6.1 tag, run the live smoke/canary once (network required): `python scripts/smoke.py`
Expected: `SMOKE OK` and both canary endpoints reported. This is not part of CI and not required to land the code.

---

## F6 — HUMAN checklist (carried verbatim from the audit; NOT code)

These items are for a human operator. They are **not** implemented by this plan and have no code tasks. Reproduced verbatim from the spec (F6):

- [ ] Verify the MCP Apps `_UI_META` key (`server.py:60`, marked VERIFY) against the current MCP Apps spec in a live Claude Desktop session; set `REJSTRIK_APPS_CAPABILITY_KEY` if the negotiated key differs.
- [ ] Turn on GitHub Actions failure notifications for `canary.yml` (or rely on G4's auto-issue once shipped).
- [ ] Stage E T4–T6 remain open: record demo media, verify/publish the registry entry, directory + community listings.

---

## Self-Review

**Spec coverage (Stage F, F1–F6):**
- F1 (broken README media + PyPI badge) → Task 6.
- F2 (fourth version location guard + README "four" files) → Task 2.
- F3 (`estimate_valuation([])` ValueError) → Task 1.
- F4 (broaden fallback to 403/429/5xx/non-JSON; keep 404/timeout propagating; message names trigger; fixture per shape) → Task 3.
- F5 minor fixes → split-year max year (Task 4), smoke.py period_year (Task 5), README drift note + How-it-works fallback mention (Task 7).
- F6 human checklist → carried verbatim above as HUMAN tasks, no code.
- Stage F "ships as v0.6.1" → Task 8; acceptance → Task 9.

**No Stage G content included** (confirmed: no `read_filing_page_images`, no Damodaran multiples, no filings TTL cache, no canary auto-issue).

**Type/name consistency:** `_BlockShaped(.reason)`, `_fetch_new_filings`, `_fetch_legacy_filings`, `_max_year`, `parse_filings_api`, `RegistryBlockedError`, `estimate_valuation` used consistently across Tasks 1/3/4. `base_year`, `date` in Task 5 match their imports.

**Placeholder scan:** none — every code step shows the exact code; every verification step shows the exact command and expected result.
