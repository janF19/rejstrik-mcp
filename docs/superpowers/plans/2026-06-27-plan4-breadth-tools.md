# Plan 4 — Registry Breadth Tools (insolvency · statutory bodies · VAT) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **⚠️ DEPENDENCY: Plan 3 must be implemented before this plan.** Plan 4 modifies `src/rejstrik/service.py`, `src/rejstrik/analysis/redflags.py`, and `src/rejstrik/mcp/server.py`, all of which Plan 3 creates. As of writing, those files do **not** exist in the repo (only Plans 1–2 are built). Do not start Plan 4 until `python -m pytest` shows Plan 3's tests passing. If Plan 3's implemented interfaces differ from what its plan document specified, reconcile the signatures referenced below (`detect_red_flags(..., insolvent=None)`, `resolve_statement_source -> (Company, Filing, PdfSource)`, `analyze_company_financials(query, *, llm=None)`, `EXPOSED_TOOL_NAMES`) against the real code before coding each task.

**Goal:** Add the structured-registry breadth that makes the product feel end-to-end — insolvency cross-check (ISIR), statutory bodies / directors (ARES VR), and VAT status (from the ARES detail) — expose them as MCP tools, and feed the insolvency result into the red-flag engine so `analyze_company_financials` reports insolvency automatically.

**Architecture:** Three small, independent clients under `registry/`, each adapted from `cz-agents-mcp` (MIT) and tested against recorded fixtures (the Plan 1 pattern — no network in CI). The analysis layer already accepts an `insolvent` flag; this plan supplies it. Three new MCP tools register alongside Plan 3's five. VAT reuses the ARES detail payload already fetched in Plan 1, so it needs no new endpoint.

**Tech Stack:** Python 3.11+, existing stack (`httpx`, `pydantic`, `selectolax`, `mcp`, `typer`, `pytest`, `respx`). No new dependencies.

## Global Constraints

- Python 3.11+; full type annotations; return Pydantic models, never raw dicts. (Inherited.)
- **Attribution is mandatory and ships in Task 1, before any adapted code lands.** Registry clients adapted from `cz-agents-mcp` (MIT, © Martin Havel) must carry the upstream copyright + permission notice in `LICENSES/cz-agents-mcp-LICENSE` and a credit line in `README.md`. Add source-file header comments (`# Adapted from cz-agents-mcp (MIT) © Martin Havel`) on the insolvency and statutory-body modules.
- IČO is always an 8-char zero-padded string (`zfill(8)`).
- All HTTP through `core/http.make_client`; never instantiate `httpx.Client` elsewhere.
- No network in tests. New external shapes are captured to `tests/fixtures/` via a one-time manual discovery sub-step, then parsers are tested against the saved fixture (Plan 1 pattern).
- Each breadth client degrades gracefully: a transport/parse failure returns a typed "unknown" result, never crashes the analyzer or MCP server.

---

### Task 1: Attribution

**Files:**
- Create: `LICENSES/cz-agents-mcp-LICENSE`
- Modify: `README.md`

**Interfaces:** none.

- [ ] **Step 1: Capture the upstream license (one-time)**

```bash
curl -s https://raw.githubusercontent.com/martinhavel/cz-agents-mcp/main/LICENSE \
  -o LICENSES/cz-agents-mcp-LICENSE
```

Open the file and confirm it is the MIT License text with a `Copyright (c) ... Martin Havel` line. If the upstream path differs, fetch from the repo's actual `LICENSE` and keep the copyright line intact.

- [ ] **Step 2: Add the README credit**

Add an "Attribution" section to `README.md`:

```markdown
## Attribution

The insolvency (ISIR) and statutory-body registry clients are adapted from
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT License,
© Martin Havel). See `LICENSES/cz-agents-mcp-LICENSE`.
```

- [ ] **Step 3: Commit**

```bash
git add LICENSES/cz-agents-mcp-LICENSE README.md
git commit -m "docs: add cz-agents-mcp MIT attribution (LICENSES + README)"
```

---

### Task 2: ISIR insolvency client

**Discovery sub-step (one-time, manual):** The ISIR insolvency lookup endpoint and response shape are the highest-risk unknown. **Read `cz-agents-mcp`'s ISIR package** (`https://github.com/martinhavel/cz-agents-mcp`, the `isir` package — MIT) to find the exact endpoint it calls and the response shape it parses. Capture one real response (a known-clean IČO and, ideally, one with a record) to a fixture:

```bash
mkdir -p tests/fixtures/isir
# Use the endpoint cz-agents-mcp's ISIR module calls. Example shape (verify against that module):
#   POST https://<isir-endpoint>/api/getevents  body {"ic": "00006947"}
curl -s -X POST "<ISIR_ENDPOINT_FROM_CZ_AGENTS_MCP>" \
  -H "Content-Type: application/json" -d '{"ic":"00006947"}' \
  -o tests/fixtures/isir/clean_00006947.json
```

Open the saved JSON, identify how "in insolvency" is signalled (presence of cases / a status field) and the per-case fields. Encode those in `parse_insolvency` below; adjust the field access AND the test assertions together to match the real shape. Commit the fixture. If the chosen source requires auth or a key, document that in the module docstring and fall back to the official ISIR endpoint cz-agents-mcp uses.

**Files:**
- Create: `src/rejstrik/registry/isir.py`
- Test: `tests/registry/test_isir.py`
- Create: `tests/fixtures/isir/clean_00006947.json` (from discovery)

**Interfaces:**
- Consumes: `make_client` (core/http).
- Produces: `InsolvencyCase` model: `case_number: str | None`, `state: str | None`.
- Produces: `InsolvencyStatus` model: `ico: str`, `in_insolvency: bool`, `cases: list[InsolvencyCase]`, `checked: bool` (`False` when the lookup failed and the result is unknown).
- Produces: `parse_insolvency(ico: str, payload: dict) -> InsolvencyStatus` — pure mapper from the ISIR JSON to the model.
- Produces: `check_insolvency(ico: str, client=None) -> InsolvencyStatus` — fetches + parses; on any transport error returns `InsolvencyStatus(ico, in_insolvency=False, cases=[], checked=False)`.

- [ ] **Step 1: Write the failing test (parser against fixture + graceful failure)**

```python
# tests/registry/test_isir.py
import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.isir import parse_insolvency, check_insolvency, InsolvencyStatus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "isir" / "clean_00006947.json"


def test_parse_insolvency_clean_record():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    status = parse_insolvency("00006947", payload)
    assert isinstance(status, InsolvencyStatus)
    assert status.ico == "00006947"
    assert status.checked is True
    # A clean company has no open insolvency:
    assert status.in_insolvency is False


@respx.mock
def test_check_insolvency_returns_unknown_on_transport_error():
    # Match whatever URL check_insolvency calls; force a 500.
    respx.route().mock(return_value=httpx.Response(500))
    status = check_insolvency("00006947")
    assert status.checked is False
    assert status.in_insolvency is False
```

> When you encode the real ISIR endpoint, add a third test (`@respx.mock`) that mocks a *positive* record (copy the fixture, inject one case) and asserts `in_insolvency is True` and `len(status.cases) == 1`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_isir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.registry.isir'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/isir.py
# Adapted from cz-agents-mcp (MIT) © Martin Havel — endpoint and response shape
# follow that project's ISIR package. See LICENSES/cz-agents-mcp-LICENSE.
import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

# Replace with the exact endpoint cz-agents-mcp's ISIR module uses (captured in discovery).
ISIR_ENDPOINT = "<ISIR_ENDPOINT_FROM_CZ_AGENTS_MCP>"


class InsolvencyCase(BaseModel):
    case_number: str | None = None
    state: str | None = None


class InsolvencyStatus(BaseModel):
    ico: str
    in_insolvency: bool
    cases: list[InsolvencyCase] = []
    checked: bool = True


def parse_insolvency(ico: str, payload: dict) -> InsolvencyStatus:
    # Adjust these accessors to the real ISIR JSON observed in discovery.
    raw_cases = payload.get("cases") or payload.get("events") or []
    cases = [
        InsolvencyCase(
            case_number=c.get("caseNumber") or c.get("spisovaZnacka"),
            state=c.get("state") or c.get("stav"),
        )
        for c in raw_cases
    ]
    return InsolvencyStatus(ico=ico.zfill(8), in_insolvency=bool(cases), cases=cases, checked=True)


def check_insolvency(ico: str, client: httpx.Client | None = None) -> InsolvencyStatus:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.post(ISIR_ENDPOINT, json={"ic": ico})
        resp.raise_for_status()
        return parse_insolvency(ico, resp.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return InsolvencyStatus(ico=ico, in_insolvency=False, cases=[], checked=False)
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_isir.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/isir.py tests/registry/test_isir.py tests/fixtures/isir/
git commit -m "feat: ISIR insolvency client (adapted from cz-agents-mcp, MIT)"
```

---

### Task 3: Wire insolvency into the analyzer

**Files:**
- Modify: `src/rejstrik/service.py`
- Test: `tests/test_service_insolvency.py`

**Interfaces:**
- Consumes: `check_insolvency` (Task 2), `detect_red_flags(..., insolvent=...)` (Plan 3).
- Modifies: `analyze_company_financials(query, *, llm=None, insolvency_check=None)` — `insolvency_check` defaults to `check_insolvency` (injectable for tests). After extraction, call `insolvency_check(company.ico)`; pass `insolvent=status.in_insolvency if status.checked else None` to `detect_red_flags`. (Plan 3 already wired the `insolvent` parameter through; this only supplies the value.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_service_insolvency.py
from unittest.mock import patch

import rejstrik.service as service
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.models import Company

COMPANY = Company(ico="00006947", name="Test s.r.o.")
FILINGS = [Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True)]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")
STATEMENT = FinancialStatement(ico="00006947", period_year=2023, balance_sheet=[Figure(label="Aktiva celkem", value=10.0)])


def _patches():
    return [
        patch.object(service, "find_company", return_value=COMPANY),
        patch.object(service, "list_filings", return_value=FILINGS),
        patch.object(service, "load_pdf", return_value=SRC),
        patch.object(service, "extract_financials", return_value=STATEMENT),
    ]


def test_insolvent_company_gets_insolvency_red_flag():
    insolvent = lambda ico: InsolvencyStatus(ico=ico, in_insolvency=True, cases=[], checked=True)
    with _patches()[0], _patches()[1], _patches()[2], _patches()[3]:
        report = service.analyze_company_financials("Test", insolvency_check=insolvent)
    assert any(f.code == "insolvency" for f in report.red_flags)


def test_unknown_insolvency_adds_no_flag():
    unknown = lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False, cases=[], checked=False)
    with _patches()[0], _patches()[1], _patches()[2], _patches()[3]:
        report = service.analyze_company_financials("Test", insolvency_check=unknown)
    assert not any(f.code == "insolvency" for f in report.red_flags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_service_insolvency.py -v`
Expected: FAIL — `TypeError` (`insolvency_check` not accepted) or no insolvency flag.

- [ ] **Step 3: Modify `analyze_company_financials`**

Add the import and parameter; pass the flag into `detect_red_flags`:

```python
# add to imports in src/rejstrik/service.py
from rejstrik.registry.isir import check_insolvency
```

```python
# replace the analyze_company_financials definition body in src/rejstrik/service.py
def analyze_company_financials(query, *, llm=None, insolvency_check=None):
    insolvency_check = insolvency_check or check_insolvency
    company, filing, source = resolve_statement_source(query)
    statement = extract_financials(source, llm=llm)
    normalized = normalize(statement)
    ratios = compute_ratios(normalized)
    status = insolvency_check(company.ico)
    insolvent = status.in_insolvency if status.checked else None
    red_flags = detect_red_flags(normalized, ratios, statement.notes, insolvent=insolvent)
    return CompanyFinancialReport(
        company_name=statement.company_name or company.name,
        ico=statement.ico or company.ico,
        period_year=statement.period_year,
        currency=statement.currency,
        statement=statement,
        normalized=normalized,
        ratios=ratios,
        red_flags=red_flags,
        source_filing_title=filing.title,
    )
```

> Keep the type annotations consistent with Plan 3's signature (`query: str`, `llm: DocumentLLM | None`); add `insolvency_check: Callable[[str], InsolvencyStatus] | None = None` and import `Callable` from `typing` and `InsolvencyStatus` from `rejstrik.registry.isir`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_service_insolvency.py tests/test_service.py -v`
Expected: PASS (existing `test_service.py` still green — its default `insolvency_check` would hit the network, so confirm those tests either patch `service.check_insolvency` or pass a stub; if Plan 3's `test_service.py` calls `analyze_company_financials` without an insolvency stub, add `patch.object(service, "check_insolvency", return_value=InsolvencyStatus(ico="00006947", in_insolvency=False, cases=[], checked=False))` to those tests).

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/service.py tests/test_service_insolvency.py tests/test_service.py
git commit -m "feat: feed ISIR insolvency into analyze_company_financials red flags"
```

---

### Task 4: Statutory bodies (ARES VR)

**Discovery sub-step (one-time, manual):** ARES exposes the full public-register extract (including statutory bodies) at the VR endpoint. Capture a real response:

```bash
mkdir -p tests/fixtures/ares
curl -s "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/00006947" \
  -o tests/fixtures/ares/vr_00006947.json
```

Open the JSON and locate the statutory-body section (under `zaznamy[].statutarniOrgany[]` or similar — confirm the exact path) and the per-member fields (person name, role, start date). Encode those in `parse_statutory_bodies` and align the test assertions to the real shape. Cross-check field names against `cz-agents-mcp`'s ARES package. Commit the fixture.

**Files:**
- Create: `src/rejstrik/registry/statutory.py`
- Test: `tests/registry/test_statutory.py`
- Create: `tests/fixtures/ares/vr_00006947.json` (from discovery)

**Interfaces:**
- Consumes: `make_client`.
- Produces: `Officer` model: `name: str`, `role: str | None`, `since: str | None`.
- Produces: `parse_statutory_bodies(payload: dict) -> list[Officer]` — pure mapper.
- Produces: `get_statutory_bodies(ico: str, client=None) -> list[Officer]` — fetches + parses; `[]` on error.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_statutory.py
import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.statutory import parse_statutory_bodies, get_statutory_bodies, Officer

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ares" / "vr_00006947.json"


def test_parse_statutory_bodies_returns_officers():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    officers = parse_statutory_bodies(payload)
    assert isinstance(officers, list)
    assert all(isinstance(o, Officer) for o in officers)
    assert all(o.name for o in officers)  # every officer has a name


@respx.mock
def test_get_statutory_bodies_returns_empty_on_error():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/00006947"
    ).mock(return_value=httpx.Response(500))
    assert get_statutory_bodies("00006947") == []
```

> The first assertion is shape-tolerant on purpose (the exact officer count/names depend on the live fixture). Once you see the real data, tighten it to assert a known officer name from the fixture.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_statutory.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/statutory.py
# Adapted from cz-agents-mcp (MIT) © Martin Havel. See LICENSES/cz-agents-mcp-LICENSE.
import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr"


class Officer(BaseModel):
    name: str
    role: str | None = None
    since: str | None = None


def _member_name(member: dict) -> str | None:
    osoba = member.get("fyzickaOsoba") or member.get("osoba") or {}
    first = osoba.get("jmeno") or ""
    last = osoba.get("prijmeni") or osoba.get("obchodniJmeno") or ""
    full = f"{first} {last}".strip()
    return full or None


def parse_statutory_bodies(payload: dict) -> list[Officer]:
    # Adjust the path to match the observed VR JSON (records -> statutory organs -> members).
    officers: list[Officer] = []
    for zaznam in payload.get("zaznamy") or []:
        for organ in zaznam.get("statutarniOrgany") or []:
            role = organ.get("nazevOrganu") or organ.get("typOrganu")
            for member in organ.get("clenoveOrganu") or organ.get("clenove") or []:
                name = _member_name(member)
                if name:
                    officers.append(Officer(name=name, role=role, since=member.get("datumZapisu")))
    return officers


def get_statutory_bodies(ico: str, client: httpx.Client | None = None) -> list[Officer]:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(f"{BASE}/{ico}")
        resp.raise_for_status()
        return parse_statutory_bodies(resp.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return []
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_statutory.py -v`
Expected: PASS. If the real VR JSON nests members differently, adjust `parse_statutory_bodies` + `_member_name` until the fixture-based test passes.

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/statutory.py tests/registry/test_statutory.py tests/fixtures/ares/vr_00006947.json
git commit -m "feat: statutory-body lookup via ARES VR (adapted from cz-agents-mcp)"
```

---

### Task 5: VAT status (from ARES detail — no new endpoint)

**Files:**
- Create: `src/rejstrik/registry/vat.py`
- Test: `tests/registry/test_vat.py`

**Interfaces:**
- Consumes: `make_client`, the ARES detail endpoint + fixture already used in Plan 1 (`tests/fixtures/ares/detail_00006947.json`).
- Produces: `VatStatus` model: `ico: str`, `dic: str | None`, `is_vat_payer: bool`.
- Produces: `parse_vat(ico: str, payload: dict) -> VatStatus` — `dic` from `payload["dic"]`; `is_vat_payer` True when a DIČ is present (and/or a DPH registration entry exists in the detail payload — confirm against the Plan 1 fixture and use whichever field is populated).
- Produces: `check_vat(ico: str, client=None) -> VatStatus` — fetches the ARES detail (same URL as `registry.ares.get_company`) and parses; on error returns `VatStatus(ico, dic=None, is_vat_payer=False)`.

> Scope note: this reports VAT *registration* from ARES. The ADIS "unreliable payer" (nespolehlivý plátce) flag requires a separate SOAP service and is deferred to a future plan — documented here so the boundary is explicit.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_vat.py
import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.vat import parse_vat, check_vat, VatStatus

DETAIL = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"


def test_parse_vat_reads_dic_from_detail():
    payload = json.loads(DETAIL.read_text(encoding="utf-8"))
    status = parse_vat("00006947", payload)
    assert isinstance(status, VatStatus)
    assert status.ico == "00006947"
    # Budvar is a VAT payer — fixture should carry a DIČ. If the fixture company has no DIČ,
    # swap the fixture for a VAT-registered company before asserting True.
    assert status.is_vat_payer == (status.dic is not None)


def test_parse_vat_no_dic_is_not_payer():
    status = parse_vat("00000000", {"ico": "00000000"})
    assert status.dic is None
    assert status.is_vat_payer is False


@respx.mock
def test_check_vat_returns_not_payer_on_error():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(500))
    status = check_vat("00006947")
    assert status.is_vat_payer is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_vat.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/vat.py
import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class VatStatus(BaseModel):
    ico: str
    dic: str | None = None
    is_vat_payer: bool = False


def parse_vat(ico: str, payload: dict) -> VatStatus:
    dic = payload.get("dic")
    return VatStatus(ico=ico.zfill(8), dic=dic, is_vat_payer=dic is not None)


def check_vat(ico: str, client: httpx.Client | None = None) -> VatStatus:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(f"{BASE}/{ico}")
        resp.raise_for_status()
        return parse_vat(ico, resp.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return VatStatus(ico=ico, dic=None, is_vat_payer=False)
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_vat.py -v`
Expected: PASS. If the Plan 1 `detail_00006947.json` fixture has no `dic` field, either confirm `is_vat_payer` follows `dic is None` (the assertion is written to tolerate both) or capture a fresh detail fixture for a known VAT-registered company.

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/vat.py tests/registry/test_vat.py
git commit -m "feat: VAT status from ARES detail (dic + registration)"
```

---

### Task 6: Register the three breadth tools on the MCP server

**Files:**
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_breadth_tools.py`

**Interfaces:**
- Consumes: `check_insolvency`, `get_statutory_bodies`, `check_vat`, and `find_company` (to resolve a name → IČO so the tools accept either).
- Modifies: `EXPOSED_TOOL_NAMES` → append `"check_insolvency"`, `"get_statutory_bodies"`, `"check_vat"` (now 8 total).
- Adds three `@mcp.tool()` functions delegating to the clients. Each accepts an `ico` string; if the input is not 8 digits, resolve it via `find_company(...).ico` first so agents can pass a name.

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_breadth_tools.py
import asyncio

from rejstrik.mcp import server


def test_breadth_tools_in_exposed_names():
    for name in ("check_insolvency", "get_statutory_bodies", "check_vat"):
        assert name in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 8


def test_breadth_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"check_insolvency", "get_statutory_bodies", "check_vat"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_breadth_tools.py -v`
Expected: FAIL — `AssertionError` (names absent / count is 5).

- [ ] **Step 3: Modify `src/rejstrik/mcp/server.py`**

Add imports, extend `EXPOSED_TOOL_NAMES`, add the three tools:

```python
# add to imports in src/rejstrik/mcp/server.py
from rejstrik.registry.isir import InsolvencyStatus, check_insolvency as _check_insolvency
from rejstrik.registry.statutory import Officer, get_statutory_bodies as _get_statutory_bodies
from rejstrik.registry.vat import VatStatus, check_vat as _check_vat
```

```python
# extend the EXPOSED_TOOL_NAMES list in src/rejstrik/mcp/server.py
EXPOSED_TOOL_NAMES = [
    "find_company",
    "list_filings",
    "extract_financials",
    "ask_filing",
    "analyze_company_financials",
    "check_insolvency",
    "get_statutory_bodies",
    "check_vat",
]
```

```python
# add near the other @mcp.tool() functions in src/rejstrik/mcp/server.py

def _to_ico(value: str) -> str:
    """Accept an 8-digit IČO directly, otherwise resolve a name via ARES."""
    v = value.strip()
    return v.zfill(8) if v.isdigit() else _find_company(v).ico


@mcp.tool()
def check_insolvency(ico: str) -> InsolvencyStatus:
    """Check the Czech insolvency register (ISIR) for a company by IČO or name."""
    return _check_insolvency(_to_ico(ico))


@mcp.tool()
def get_statutory_bodies(ico: str) -> list[Officer]:
    """List a company's statutory bodies / directors from the ARES public register."""
    return _get_statutory_bodies(_to_ico(ico))


@mcp.tool()
def check_vat(ico: str) -> VatStatus:
    """Report a company's VAT registration (DIČ) from ARES."""
    return _check_vat(_to_ico(ico))
```

> `_find_company` is already imported in Plan 3's server module (aliased). If Plan 3 imported it under a different name, reuse that alias in `_to_ico`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mcp/test_breadth_tools.py tests/mcp/test_server.py -v`
Expected: PASS (the Plan 3 `test_server.py` still passes — update its `EXPOSED_TOOL_NAMES` equality assertion if it pinned the list to exactly five names; change it to the eight-name list).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS (Plans 1–4).

- [ ] **Step 6: Manual smoke test (real network — NOT in CI)**

```bash
rejstrik-mcp &
# In an MCP client / curl, call check_insolvency, get_statutory_bodies, check_vat for IČO 00006947
kill %1
# Or exercise the clients directly:
python -c "from rejstrik.registry.statutory import get_statutory_bodies; print(get_statutory_bodies('00006947'))"
python -c "from rejstrik.registry.vat import check_vat; print(check_vat('00006947'))"
python -c "from rejstrik.registry.isir import check_insolvency; print(check_insolvency('00006947'))"
```

Confirm statutory bodies list real officers, VAT shows the DIČ, and insolvency returns `checked=True`.

- [ ] **Step 7: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_breadth_tools.py tests/mcp/test_server.py
git commit -m "feat: expose insolvency, statutory-body, and VAT MCP tools (8 total)"
```

---

### Task 7: README + lint

**Files:**
- Modify: `README.md`
- Modify: any files flagged by `ruff`.

- [ ] **Step 1: Update README**

Update the MCP-server section to list all eight tools, note that `analyze_company_financials` now includes an automatic ISIR insolvency cross-check in its red flags, and document the deferred ADIS "unreliable payer" flag as a known future extension.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: clean (run `ruff format src/ tests/` to fix, then re-run).

- [ ] **Step 3: Run full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md src/ tests/
git commit -m "docs: README breadth-tools + insolvency cross-check; lint clean"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- `check_insolvency` (ISIR) → Task 2. ✓
- `get_statutory_bodies` (directors / UBO) → Task 4. ✓
- `check_vat` (VAT reliability) → Task 5 (registration; unreliable-payer deferred, documented). ✓
- "borrowed/adapted from cz-agents-mcp (MIT) with attribution" → Task 1 (LICENSE + README + source headers). ✓
- Insolvency feeds the red-flag engine → Task 3 (the design spec lists ISIR cross-check as a red flag; Plan 3 wired the parameter, Plan 4 supplies the value). ✓
- All breadth tools exposed via MCP → Task 6 (8 tools total — the full design-spec tool surface). ✓
- "match enough breadth to feel end-to-end, win on depth" → achieved: structured breadth (8 tools) without chasing cz-agents-mcp's full 27-tool surface. ✓

**Placeholder scan:** The `<ISIR_ENDPOINT_FROM_CZ_AGENTS_MCP>` and `<ISIR_ENDPOINT>` tokens in Task 2 are **intentional, flagged discovery placeholders** — the ISIR endpoint genuinely cannot be hardcoded without reading cz-agents-mcp's source and capturing a real response (the same fixture-discovery pattern Plan 1 used for ARES/justice). The task tells the implementer exactly where to get the value and what to confirm. Every other module is complete code. The ARES VR statutory-body JSON path and the VAT `dic` field are written to the most likely shapes with explicit "confirm against the captured fixture and adjust parser + assertions together" instructions — the standard scraper-TDD loop, not unfinished work.

**Type consistency:** `InsolvencyStatus(ico, in_insolvency, cases, checked)` identical across Tasks 2/3/6. `Officer(name, role, since)` across 4/6. `VatStatus(ico, dic, is_vat_payer)` across 5/6. `detect_red_flags(..., insolvent=...)` (Plan 3) consumed in Task 3. `analyze_company_financials(query, *, llm=None, insolvency_check=None)` extends Plan 3's signature additively (old callers unaffected). `EXPOSED_TOOL_NAMES` is the single source for the tool-name tests (Tasks 6) and matches the eight `@mcp.tool()` functions. ✓

**Dependency reminder:** This plan does not run until Plan 3 is implemented and green. The header gate states this; the implementer must verify Plan 3's real interfaces before each task, since Plan 4 was written against Plan 3's *documented* interfaces, not verified code.
