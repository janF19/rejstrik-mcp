# Plan 1 — Registry & Filings Spine (CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python core library + CLI that, given a company name or IČO, resolves it via ARES and lists its financial-statement PDFs from the justice.cz Sbírka listin with downloadable URLs.

**Architecture:** A pure core library (`registry/`, `filings/`) with a thin `cli/` shell over it. No AI, no MCP yet — this is the structured spine the document engine (Plan 2) and MCP server (Plan 3) build on. HTTP clients are tested against recorded real-response fixtures so tests are deterministic and offline.

**Tech Stack:** Python 3.11+, `httpx` (HTTP), `pydantic` v2 (models), `typer` (CLI), `selectolax` (fast HTML parsing for justice.cz), `pytest` + `respx` (HTTP mocking), `ruff` (lint/format).

## Global Constraints

- Python 3.11+ (use `X | None` unions, `match`, modern typing).
- License: MIT. A `LICENSES/cz-agents-mcp-LICENSE` file holding the upstream MIT notice (© Martin Havel) MUST exist before any code adapted from cz-agents-mcp lands. (No adapted code in Plan 1, but create the structure.)
- All public functions are fully type-annotated and return Pydantic models, never raw dicts.
- All HTTP access goes through `core/http.py` (one shared client factory) — never instantiate `httpx.Client` elsewhere.
- Respect rate limits: ARES allows generous limits; justice.cz must use a descriptive User-Agent and a small delay. Default User-Agent: `rejstrik-mcp/0.1 (+https://github.com/<user>/rejstrik-mcp)`.
- Tests never hit the network. Network calls are either `respx`-mocked or replayed from `tests/fixtures/`.
- IČO is always handled as an 8-char zero-padded string (e.g. `"00006947"`), never an int.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/rejstrik/__init__.py`
- Create: `src/rejstrik/core/__init__.py`
- Create: `LICENSE`
- Create: `LICENSES/.gitkeep`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: package `rejstrik` importable; `rejstrik.__version__` == `"0.1.0"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
import rejstrik


def test_version_exposed():
    assert rejstrik.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik'`

- [ ] **Step 3: Write scaffold**

```toml
# pyproject.toml
[project]
name = "rejstrik-mcp"
version = "0.1.0"
description = "Czech registry MCP that reads the documents"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
    "typer>=0.12",
    "selectolax>=0.3.21",
]

[project.optional-dependencies]
dev = ["pytest>=8", "respx>=0.21", "ruff>=0.5"]

[project.scripts]
rejstrik = "rejstrik.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rejstrik"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
# src/rejstrik/__init__.py
__version__ = "0.1.0"
```

```python
# src/rejstrik/core/__init__.py
```

```python
# tests/__init__.py
```

`LICENSE`: standard MIT text, copyright `2026 <your name>`.
`LICENSES/.gitkeep`: empty file (placeholder so the directory is tracked).

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/ LICENSE LICENSES/
git commit -m "chore: project scaffold"
```

---

### Task 2: Shared HTTP client factory

**Files:**
- Create: `src/rejstrik/core/http.py`
- Test: `tests/core/test_http.py`
- Create: `tests/core/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `make_client(timeout: float = 30.0) -> httpx.Client` — returns an `httpx.Client` with the project User-Agent header set and `follow_redirects=True`.
- Produces: `USER_AGENT: str` constant.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_http.py
from rejstrik.core.http import make_client, USER_AGENT


def test_client_has_user_agent_and_redirects():
    client = make_client()
    try:
        assert client.headers["User-Agent"] == USER_AGENT
        assert "rejstrik-mcp" in USER_AGENT
        assert client.follow_redirects is True
    finally:
        client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.core.http'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/core/http.py
import httpx

USER_AGENT = "rejstrik-mcp/0.1 (+https://github.com/rejstrik-mcp/rejstrik-mcp)"


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_http.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/core/http.py tests/core/
git commit -m "feat: shared http client factory"
```

---

### Task 3: ARES models

**Files:**
- Create: `src/rejstrik/registry/__init__.py`
- Create: `src/rejstrik/registry/models.py`
- Test: `tests/registry/test_models.py`
- Create: `tests/registry/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Company` Pydantic model with fields: `ico: str`, `name: str`, `address: str | None`, `legal_form: str | None`, `founded: str | None` (ISO date string or None).
- Produces: `Company.ico` validator that zero-pads to 8 chars.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_models.py
from rejstrik.registry.models import Company


def test_company_pads_ico():
    c = Company(ico="6947", name="Test s.r.o.")
    assert c.ico == "00006947"
    assert c.address is None


def test_company_keeps_full_ico():
    c = Company(ico="00006947", name="Test", address="Praha", legal_form="s.r.o.")
    assert c.ico == "00006947"
    assert c.address == "Praha"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/__init__.py
```

```python
# src/rejstrik/registry/models.py
from pydantic import BaseModel, field_validator


class Company(BaseModel):
    ico: str
    name: str
    address: str | None = None
    legal_form: str | None = None
    founded: str | None = None

    @field_validator("ico")
    @classmethod
    def pad_ico(cls, v: str) -> str:
        return v.strip().zfill(8)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/ tests/registry/
git commit -m "feat: ARES Company model"
```

---

### Task 4: ARES detail parser (test against recorded fixture)

**Discovery sub-step (do this first, once, manually — it is NOT a unit test):**
Run this to capture a real ARES detail response into a fixture. ARES API v3 detail endpoint:
`GET https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}`

```bash
mkdir -p tests/fixtures/ares
curl -s "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947" \
  -o tests/fixtures/ares/detail_00006947.json
```

Then open the JSON and confirm the field names used below (`ico`, `obchodniJmeno`, `sidlo.textovaAdresa`, `pravniForma`, `datumVzniku`). If ARES has renamed a field, adjust the parser AND the assertions in the same step. Commit the fixture.

**Files:**
- Create: `src/rejstrik/registry/ares.py`
- Test: `tests/registry/test_ares.py`
- Create: `tests/fixtures/ares/detail_00006947.json` (from discovery)

**Interfaces:**
- Consumes: `Company` (Task 3), `make_client` (Task 2).
- Produces: `parse_detail(payload: dict) -> Company` — pure function mapping an ARES JSON dict to a `Company`.
- Produces: `get_company(ico: str, client: httpx.Client | None = None) -> Company` — fetches and parses; raises `CompanyNotFound(ico)` on HTTP 404.
- Produces: `class CompanyNotFound(Exception)`.

- [ ] **Step 1: Write the failing test (parser, against fixture)**

```python
# tests/registry/test_ares.py
import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.ares import parse_detail, get_company, CompanyNotFound
import pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"


def test_parse_detail_maps_core_fields():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    company = parse_detail(payload)
    assert company.ico == "00006947"
    assert company.name  # non-empty
    assert isinstance(company.name, str)


@respx.mock
def test_get_company_uses_detail_endpoint():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    route = respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(200, json=payload))
    company = get_company("6947")  # unpadded on purpose
    assert route.called
    assert company.ico == "00006947"


@respx.mock
def test_get_company_raises_on_404():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00000000"
    ).mock(return_value=httpx.Response(404))
    with pytest.raises(CompanyNotFound):
        get_company("00000000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_ares.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.registry.ares'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/ares.py
import httpx

from rejstrik.core.http import make_client
from rejstrik.registry.models import Company

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class CompanyNotFound(Exception):
    def __init__(self, ico: str) -> None:
        super().__init__(f"No company found for IČO {ico}")
        self.ico = ico


def parse_detail(payload: dict) -> Company:
    sidlo = payload.get("sidlo") or {}
    return Company(
        ico=str(payload["ico"]),
        name=payload.get("obchodniJmeno") or "",
        address=sidlo.get("textovaAdresa"),
        legal_form=payload.get("pravniForma"),
        founded=payload.get("datumVzniku"),
    )


def get_company(ico: str, client: httpx.Client | None = None) -> Company:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(f"{BASE}/{ico}")
        if resp.status_code == 404:
            raise CompanyNotFound(ico)
        resp.raise_for_status()
        return parse_detail(resp.json())
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_ares.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/ares.py tests/registry/test_ares.py tests/fixtures/ares/
git commit -m "feat: ARES company detail fetch + parse"
```

---

### Task 5: ARES name search → find_company

**Discovery sub-step (once, manual):** ARES search is a POST:
`POST https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat`
Body: `{"obchodniJmeno": "<name>", "start": 0, "pocet": 10}`. Capture a real response:

```bash
curl -s -X POST "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat" \
  -H "Content-Type: application/json" \
  -d '{"obchodniJmeno":"Budvar","start":0,"pocet":5}' \
  -o tests/fixtures/ares/search_budvar.json
```

Confirm the response has an `ekonomickeSubjekty` array of detail-shaped objects. Adjust the key below if different. Commit the fixture.

**Files:**
- Modify: `src/rejstrik/registry/ares.py`
- Test: `tests/registry/test_search.py`
- Create: `tests/fixtures/ares/search_budvar.json` (from discovery)

**Interfaces:**
- Consumes: `parse_detail`, `Company`, `make_client`.
- Produces: `search_by_name(name: str, limit: int = 10, client=None) -> list[Company]`.
- Produces: `find_company(query: str, client=None) -> Company` — if `query` is 1–8 digits, treat as IČO and call `get_company`; otherwise `search_by_name` and return the first match; raise `CompanyNotFound(query)` if the search is empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_search.py
import json
from pathlib import Path

import httpx
import pytest
import respx

from rejstrik.registry.ares import search_by_name, find_company, CompanyNotFound

FX = Path(__file__).parent.parent / "fixtures" / "ares"


@respx.mock
def test_search_by_name_returns_companies():
    payload = json.loads((FX / "search_budvar.json").read_text(encoding="utf-8"))
    respx.post(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat"
    ).mock(return_value=httpx.Response(200, json=payload))
    results = search_by_name("Budvar")
    assert len(results) >= 1
    assert all(len(c.ico) == 8 for c in results)


@respx.mock
def test_find_company_numeric_query_uses_detail():
    detail = json.loads((FX / "detail_00006947.json").read_text(encoding="utf-8"))
    route = respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"
    ).mock(return_value=httpx.Response(200, json=detail))
    company = find_company("6947")
    assert route.called
    assert company.ico == "00006947"


@respx.mock
def test_find_company_empty_search_raises():
    respx.post(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat"
    ).mock(return_value=httpx.Response(200, json={"ekonomickeSubjekty": []}))
    with pytest.raises(CompanyNotFound):
        find_company("NoSuchCompanyXYZ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_search.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_by_name'`

- [ ] **Step 3: Write minimal implementation (append to ares.py)**

```python
# append to src/rejstrik/registry/ares.py


def search_by_name(name: str, limit: int = 10, client: httpx.Client | None = None) -> list[Company]:
    owns = client is None
    client = client or make_client()
    try:
        resp = client.post(
            f"{BASE}/vyhledat",
            json={"obchodniJmeno": name, "start": 0, "pocet": limit},
        )
        resp.raise_for_status()
        items = resp.json().get("ekonomickeSubjekty") or []
        return [parse_detail(item) for item in items]
    finally:
        if owns:
            client.close()


def find_company(query: str, client: httpx.Client | None = None) -> Company:
    q = query.strip()
    if q.isdigit() and len(q) <= 8:
        return get_company(q, client=client)
    results = search_by_name(q, limit=1, client=client)
    if not results:
        raise CompanyNotFound(query)
    return results[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_search.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/ares.py tests/registry/test_search.py tests/fixtures/ares/search_budvar.json
git commit -m "feat: ARES name search + find_company resolver"
```

---

### Task 6: Filing models

**Files:**
- Create: `src/rejstrik/filings/__init__.py`
- Create: `src/rejstrik/filings/models.py`
- Test: `tests/filings/test_models.py`
- Create: `tests/filings/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Filing` model: `title: str`, `year: int | None`, `pdf_url: str`, `is_financial_statement: bool = False`.
- Produces: `classify_financial(title: str) -> bool` — True if the title matches Czech financial-statement keywords (case/diacritic-insensitive): `účetní závěrka`, `výroční zpráva`, `rozvaha`, `výkaz zisku`, `zpráva auditora`.

- [ ] **Step 1: Write the failing test**

```python
# tests/filings/test_models.py
from rejstrik.filings.models import Filing, classify_financial


def test_classify_financial_matches_keywords():
    assert classify_financial("Účetní závěrka 2023") is True
    assert classify_financial("VYROCNI ZPRAVA 2022") is True   # no diacritics, upper
    assert classify_financial("výkaz zisku a ztráty") is True
    assert classify_financial("Podpisový vzor jednatele") is False


def test_filing_defaults():
    f = Filing(title="Rozvaha 2023", pdf_url="https://x/y.pdf", year=2023)
    assert f.is_financial_statement is False  # set by caller, not auto
    assert f.year == 2023
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/filings/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/filings/__init__.py
```

```python
# src/rejstrik/filings/models.py
import unicodedata

from pydantic import BaseModel

_KEYWORDS = (
    "ucetni zaverka",
    "vyrocni zprava",
    "rozvaha",
    "vykaz zisku",
    "zprava auditora",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.lower()


def classify_financial(title: str) -> bool:
    norm = _normalize(title)
    return any(kw in norm for kw in _KEYWORDS)


class Filing(BaseModel):
    title: str
    year: int | None = None
    pdf_url: str
    is_financial_statement: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/filings/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/filings/ tests/filings/
git commit -m "feat: Filing model + financial-statement classifier"
```

---

### Task 7: justice.cz Sbírka listin parser → list_filings

**Discovery sub-step (once, manual — justice.cz HTML shape is uncertain, so capture real HTML):**
The Sbírka listin (collection of deeds) for a company is reached via or.justice.cz. Capture two real pages — the subject lookup by IČO and the deeds listing — and save the HTML:

```bash
mkdir -p tests/fixtures/justice
# 1) Find the subject page by IČO (returns a page linking to vypis-sl with a subjektId):
curl -s "https://or.justice.cz/ias/ui/rejstrik-firma.vysledky?ico=00006947" \
  -o tests/fixtures/justice/subject_00006947.html
# 2) Open that HTML, find the 'vypis-sl-firma?subjektId=...' link, fetch the deeds page:
#    (replace SUBJID with the real id you found)
curl -s "https://or.justice.cz/ias/ui/vypis-sl-firma?subjektId=SUBJID" \
  -o tests/fixtures/justice/deeds_00006947.html
```

Open `deeds_00006947.html` and identify: the row container for each document, the title text, and the `download` link (`/ias/content/download?id=...`). Encode those selectors in the parser below. If the structure differs from the assumed selectors, fix the parser and the test's expected count together. Commit both fixtures.

**Files:**
- Create: `src/rejstrik/filings/justice.py`
- Test: `tests/filings/test_justice.py`
- Create: `tests/fixtures/justice/subject_00006947.html`, `tests/fixtures/justice/deeds_00006947.html`

**Interfaces:**
- Consumes: `Filing`, `classify_financial` (Task 6), `make_client` (Task 2).
- Produces: `parse_subject_id(html: str) -> str | None` — extract the first `subjektId` from a subject-results page.
- Produces: `parse_deeds(html: str, base_url: str = "https://or.justice.cz") -> list[Filing]` — pure parser; sets `is_financial_statement` via `classify_financial`; resolves relative `download` links to absolute `pdf_url`; extracts a 4-digit year from the title when present.
- Produces: `list_filings(ico: str, client=None) -> list[Filing]` — orchestrates lookup → deeds → parse; returns financial statements first, then others; returns `[]` if the company has no deeds.

- [ ] **Step 1: Write the failing test**

```python
# tests/filings/test_justice.py
from pathlib import Path

import httpx
import respx

from rejstrik.filings.justice import parse_subject_id, parse_deeds, list_filings

FX = Path(__file__).parent.parent / "fixtures" / "justice"


def test_parse_subject_id_found():
    html = (FX / "subject_00006947.html").read_text(encoding="utf-8")
    sid = parse_subject_id(html)
    assert sid is not None and sid.isdigit()


def test_parse_deeds_extracts_filings_with_absolute_urls():
    html = (FX / "deeds_00006947.html").read_text(encoding="utf-8")
    filings = parse_deeds(html)
    assert len(filings) >= 1
    assert all(f.pdf_url.startswith("https://") for f in filings)
    # at least one financial statement should be detected and sorted first
    assert any(f.is_financial_statement for f in filings)
    assert filings[0].is_financial_statement is True


@respx.mock
def test_list_filings_orchestrates_lookup_and_deeds():
    subject_html = (FX / "subject_00006947.html").read_text(encoding="utf-8")
    deeds_html = (FX / "deeds_00006947.html").read_text(encoding="utf-8")
    respx.get("https://or.justice.cz/ias/ui/rejstrik-firma.vysledky").mock(
        return_value=httpx.Response(200, text=subject_html)
    )
    respx.get("https://or.justice.cz/ias/ui/vypis-sl-firma").mock(
        return_value=httpx.Response(200, text=deeds_html)
    )
    filings = list_filings("00006947")
    assert len(filings) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.filings.justice'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/filings/justice.py
import re

import httpx
from selectolax.parser import HTMLParser

from rejstrik.core.http import make_client
from rejstrik.filings.models import Filing, classify_financial

BASE = "https://or.justice.cz"
_SUBJ_RE = re.compile(r"subjektId=(\d+)")
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def parse_subject_id(html: str) -> str | None:
    tree = HTMLParser(html)
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        m = _SUBJ_RE.search(href)
        if m:
            return m.group(1)
    return None


def _year_from(title: str) -> int | None:
    m = _YEAR_RE.search(title)
    return int(m.group(0)) if m else None


def parse_deeds(html: str, base_url: str = BASE) -> list[Filing]:
    tree = HTMLParser(html)
    filings: list[Filing] = []
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if "download" not in href:
            continue
        title = (a.text() or "").strip()
        if not title:
            continue
        url = href if href.startswith("http") else f"{base_url}{href}"
        filings.append(
            Filing(
                title=title,
                year=_year_from(title),
                pdf_url=url,
                is_financial_statement=classify_financial(title),
            )
        )
    filings.sort(key=lambda f: (not f.is_financial_statement, -(f.year or 0)))
    return filings


def list_filings(ico: str, client: httpx.Client | None = None) -> list[Filing]:
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        sub = client.get(
            f"{BASE}/ias/ui/rejstrik-firma.vysledky", params={"ico": ico}
        )
        sub.raise_for_status()
        subject_id = parse_subject_id(sub.text)
        if subject_id is None:
            return []
        deeds = client.get(
            f"{BASE}/ias/ui/vypis-sl-firma", params={"subjektId": subject_id}
        )
        deeds.raise_for_status()
        return parse_deeds(deeds.text)
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/filings/test_justice.py -v`
Expected: PASS (3 tests). If the real HTML uses different containers, adjust the `css(...)` selectors and the title/href extraction until the fixture-based tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/filings/justice.py tests/filings/test_justice.py tests/fixtures/justice/
git commit -m "feat: justice.cz Sbirka listin listing + financial-statement detection"
```

---

### Task 8: CLI

**Files:**
- Create: `src/rejstrik/cli/__init__.py`
- Create: `src/rejstrik/cli/main.py`
- Test: `tests/cli/test_main.py`
- Create: `tests/cli/__init__.py`

**Interfaces:**
- Consumes: `find_company` (Task 5), `list_filings` (Task 7), `CompanyNotFound`.
- Produces: a `typer` app `app` with two commands:
  - `find <query>` → prints `IČO  Name  Address`.
  - `filings <ico> [--financial-only]` → prints one line per filing: `[FS] year  title  url` (the `[FS]` marker only for financial statements); with `--financial-only`, lists only financial statements.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_main.py
from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.registry.models import Company
from rejstrik.filings.models import Filing

runner = CliRunner()


def test_find_prints_company():
    company = Company(ico="00006947", name="Test s.r.o.", address="Praha")
    with patch("rejstrik.cli.main.find_company", return_value=company):
        result = runner.invoke(app, ["find", "Test"])
    assert result.exit_code == 0
    assert "00006947" in result.stdout
    assert "Test s.r.o." in result.stdout


def test_filings_financial_only_filters():
    filings = [
        Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True),
        Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False),
    ]
    with patch("rejstrik.cli.main.list_filings", return_value=filings):
        result = runner.invoke(app, ["filings", "00006947", "--financial-only"])
    assert result.exit_code == 0
    assert "Účetní závěrka 2023" in result.stdout
    assert "Podpisový vzor" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/cli/__init__.py
```

```python
# src/rejstrik/cli/main.py
import typer

from rejstrik.registry.ares import find_company, CompanyNotFound
from rejstrik.filings.justice import list_filings

app = typer.Typer(help="Czech registry MCP that reads the documents — CLI")


@app.command()
def find(query: str) -> None:
    """Resolve a company by name or IČO via ARES."""
    try:
        company = find_company(query)
    except CompanyNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    typer.echo(f"{company.ico}  {company.name}  {company.address or ''}".rstrip())


@app.command()
def filings(ico: str, financial_only: bool = typer.Option(False, "--financial-only")) -> None:
    """List Sbírka listin documents for a company."""
    items = list_filings(ico)
    if financial_only:
        items = [f for f in items if f.is_financial_statement]
    if not items:
        typer.echo("No filings found.")
        return
    for f in items:
        marker = "[FS] " if f.is_financial_statement else "     "
        year = str(f.year) if f.year else "----"
        typer.echo(f"{marker}{year}  {f.title}  {f.pdf_url}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_main.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite + manual smoke**

Run: `python -m pytest -v`
Expected: ALL PASS.
Manual smoke (real network — not part of CI): `rejstrik find "Budějovický Budvar"` then `rejstrik filings 00514152 --financial-only`. Confirm real output. (Manual only; do not add network tests.)

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/cli/ tests/cli/
git commit -m "feat: CLI find + filings commands"
```

---

### Task 9: README + lint

**Files:**
- Create: `README.md`
- Modify: any files flagged by `ruff`.

**Interfaces:** none.

- [ ] **Step 1: Write README**

Include: the one-liner, the competitive positioning (names cz-agents-mcp/chytryrejstrik, states the document differentiator is coming in Plan 2), install (`pip install -e ".[dev]"`), the two CLI commands with example output, and an "Attribution" section reserving credit for cz-agents-mcp (MIT) to be added when its registry code is adapted in Plan 3.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: no errors (run `ruff format src/ tests/` to fix, then re-run).

- [ ] **Step 3: Run full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md src/ tests/
git commit -m "docs: README + lint clean"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- `find_company` tool → Tasks 3–5 (ARES). ✓
- `list_filings` tool + "tells the agent where to grab it" → Tasks 6–7 (justice.cz, financial-statement tagging, PDF URLs). ✓
- "one core, three faces" — core library + CLI face → Tasks 2–8; MCP face deferred to Plan 3 (as designed). ✓
- IČO-as-8-char-string global constraint → enforced in `Company` validator (Task 3) and every client (`zfill(8)`). ✓
- Borrowed-code attribution structure → `LICENSES/` created Task 1; actual adapted code lands Plan 3. ✓
- Document engine (`extract_financials`, `ask_filing`), analysis, orchestrator, MCP, breadth tools → **out of scope for Plan 1 by design** (Plans 2 & 3). ✓

**Placeholder scan:** No TBD/TODO. The two "discovery sub-steps" (Tasks 4, 5, 7) are real, executable curl commands that capture fixtures, not placeholders — they exist because the exact upstream field names / HTML structure must be observed from the live service rather than guessed, and the plan tells the engineer exactly what to confirm and how to adjust.

**Type consistency:** `Company(ico, name, address, legal_form, founded)` used identically in Tasks 3/4/5/8. `Filing(title, year, pdf_url, is_financial_statement)` used identically in Tasks 6/7/8. `find_company`/`list_filings`/`CompanyNotFound` signatures match between definition (Tasks 5/7/4) and CLI consumption (Task 8). ✓

**Note for the implementer:** justice.cz endpoint paths and HTML structure are the highest-risk area. The fixture-capture sub-steps exist precisely so failures surface as a parser/selector adjustment against a saved file, not a flaky network test. If or.justice.cz blocks scripted access or changes routes, capture the real navigation path in a browser, save the HTML, and adapt selectors — the parser functions (`parse_subject_id`, `parse_deeds`) are pure and will not need structural change, only selector tuning.
