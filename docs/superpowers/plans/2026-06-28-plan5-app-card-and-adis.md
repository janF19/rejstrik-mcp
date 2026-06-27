# Plan 5 — MCP App Card + ADIS Unreliable-Payer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two remaining design-spec extras — (A) the ADIS "unreliable VAT payer" (nespolehlivý plátce DPH) flag, wired into `check_vat` and the red-flag engine; and (B) an interactive MCP **App card** so `analyze_company_financials` can render as a rich, cited HTML report in MCP UI-capable clients.

**Architecture:** Builds on Plans 1–4 (all implemented, 75 tests green, registry+filings verified live). ADIS is a SOAP service modelled exactly like the existing ISIR client (`registry/isir.py`): build envelope → POST → parse XML → fixture-tested, graceful failure. The App card is a pure HTML renderer (`mcp/card.py`, unit-tested) surfaced through a new `analyze_company_card` tool using `mcp-ui-server`'s `create_ui_resource`; the existing text tool stays as the fallback for non-UI hosts.

**Tech Stack:** Python 3.11+, `mcp-ui-server` (new), existing stack (`httpx`, `pydantic`, `mcp`, `pytest`, `respx`). SOAP via stdlib `xml.etree` (as ISIR already does).

## Global Constraints

- Python 3.11+; full type annotations; return Pydantic models (analysis/registry) — the App-card tool returns `list[UIResource]`, which is the mcp-ui contract.
- IČO 8-char zero-padded; DIČ is the ADIS key (numeric part, no `CZ` prefix).
- All HTTP through `core/http.make_client`.
- ADIS client degrades gracefully: transport/parse failure → status `"unknown"`, never raises into the analyzer or server (mirrors `registry/isir.py`).
- App-card HTML must be **self-contained and sandbox-safe**: inline CSS only, no external scripts/fonts/images, all dynamic values escaped via `html.escape`. It renders in a sandboxed iframe.
- Keep the text tool `analyze_company_financials` unchanged as the text-only fallback (MCP Apps requires UI-enabled tools to remain usable on text-only hosts).
- No network in tests: ADIS parser tested against a recorded fixture; the card renderer is pure; live SOAP + in-client rendering are manual smoke steps.

---

## Part A — ADIS unreliable-payer flag

### Task 1: ADIS SOAP client

**Discovery sub-step (one-time, manual):** Capture a real ADIS response. The service is `getStatusNespolehlivyPlatce` at `https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP`, namespace `http://adis.mfcr.cz/rozhraniCRPDPH/`, input one or more `dic` (numeric, no `CZ`), output per-DIČ `nespolehlivyPlatce` ∈ `ANO` | `NE` | `NENALEZEN`. Capture a real response for a known reliable payer (Budvar DIČ `00514152`):

```bash
mkdir -p tests/fixtures/adis
curl -s -X POST "https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP" \
  -H "Content-Type: text/xml; charset=utf-8" -H 'SOAPAction: ""' \
  --data '<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:r="http://adis.mfcr.cz/rozhraniCRPDPH/">
  <soapenv:Body><r:StatusNespolehlivyPlatceRequest><r:dic>00514152</r:dic></r:StatusNespolehlivyPlatceRequest></soapenv:Body>
</soapenv:Envelope>' \
  -o tests/fixtures/adis/reliable_00514152.xml
```

Open the XML; confirm the response element names (`statusPlatceDPH` / attribute `nespolehlivyPlatce`, or child elements) and adjust `parse_unreliable` + the request element name below to match. Cross-check against `cz-agents-mcp`'s ADIS package. Commit the fixture.

**Files:**
- Create: `src/rejstrik/registry/adis.py`
- Test: `tests/registry/test_adis.py`
- Create: `tests/fixtures/adis/reliable_00514152.xml` (from discovery)

**Interfaces:**
- Consumes: `make_client`.
- Produces: `UnreliablePayer` model: `dic: str`, `status: str` (`"reliable" | "unreliable" | "not_found" | "unknown"`).
- Produces: `parse_unreliable(dic: str, xml: str) -> UnreliablePayer` — maps `NE→reliable`, `ANO→unreliable`, `NENALEZEN→not_found`.
- Produces: `check_unreliable_payer(dic: str, client=None) -> UnreliablePayer` — strips a leading `CZ`, POSTs the SOAP envelope, parses; any error → `status="unknown"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_adis.py
from pathlib import Path

import httpx
import respx

from rejstrik.registry.adis import parse_unreliable, check_unreliable_payer, UnreliablePayer

FIXTURE = Path(__file__).parent.parent / "fixtures" / "adis" / "reliable_00514152.xml"
ENDPOINT = "https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"


def test_parse_unreliable_reliable_payer():
    status = parse_unreliable("00514152", FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(status, UnreliablePayer)
    assert status.dic == "00514152"
    assert status.status == "reliable"  # Budvar is reliable -> nespolehlivyPlatce = NE


def test_parse_unreliable_handles_ano_and_nenalezen():
    ano = '<x nespolehlivyPlatce="ANO" dic="123"/>'
    nen = '<x nespolehlivyPlatce="NENALEZEN" dic="123"/>'
    assert parse_unreliable("123", ano).status == "unreliable"
    assert parse_unreliable("123", nen).status == "not_found"


@respx.mock
def test_check_unreliable_strips_cz_prefix_and_handles_error():
    respx.post(ENDPOINT).mock(return_value=httpx.Response(500))
    status = check_unreliable_payer("CZ00514152")
    assert status.dic == "00514152"
    assert status.status == "unknown"
```

> Adjust `test_parse_unreliable_handles_ano_and_nenalezen` to the real element/attribute path once the fixture reveals it (the assertions on the three status mappings stay).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_adis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.registry.adis'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/registry/adis.py
# Adapted from cz-agents-mcp (MIT) (c) Martin Havel. See LICENSES/cz-agents-mcp-LICENSE.
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client

ADIS_ENDPOINT = "https://adisrws.mfcr.cz/adistc/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"
_NS = "http://adis.mfcr.cz/rozhraniCRPDPH/"

_STATUS_MAP = {"NE": "reliable", "ANO": "unreliable", "NENALEZEN": "not_found"}


class UnreliablePayer(BaseModel):
    dic: str
    status: str  # reliable | unreliable | not_found | unknown


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_unreliable(dic: str, xml: str) -> UnreliablePayer:
    root = ElementTree.fromstring(xml)
    # The flag appears as an attribute `nespolehlivyPlatce` on the status element.
    for el in root.iter():
        raw = el.attrib.get("nespolehlivyPlatce")
        if raw is not None:
            return UnreliablePayer(dic=dic, status=_STATUS_MAP.get(raw, "unknown"))
    return UnreliablePayer(dic=dic, status="unknown")


def _build_envelope(dic: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:r="{_NS}">
  <soapenv:Body>
    <r:StatusNespolehlivyPlatceRequest>
      <r:dic>{dic}</r:dic>
    </r:StatusNespolehlivyPlatceRequest>
  </soapenv:Body>
</soapenv:Envelope>"""


def check_unreliable_payer(dic: str, client: httpx.Client | None = None) -> UnreliablePayer:
    dic = dic.strip().removeprefix("CZ").removeprefix("cz")
    owns = client is None
    client = client or make_client()
    try:
        resp = client.post(
            ADIS_ENDPOINT,
            content=_build_envelope(dic),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
        )
        resp.raise_for_status()
        return parse_unreliable(dic, resp.text)
    except (httpx.HTTPError, ElementTree.ParseError, ValueError):
        return UnreliablePayer(dic=dic, status="unknown")
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_adis.py -v`
Expected: PASS. If the real XML carries the flag as a child element rather than an attribute, adjust `parse_unreliable` (and the two crafted XML strings in the test) until the fixture test passes.

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/adis.py tests/registry/test_adis.py tests/fixtures/adis/
git commit -m "feat: ADIS unreliable-payer SOAP client (adapted from cz-agents-mcp)"
```

---

### Task 2: Enrich `check_vat` with unreliable-payer status

**Files:**
- Modify: `src/rejstrik/registry/vat.py`
- Test: `tests/registry/test_vat_unreliable.py`

**Interfaces:**
- Consumes: `check_unreliable_payer` (Task 1).
- Modifies: `VatStatus` — add `is_unreliable: bool | None = None` (None when not a payer or the check is unavailable).
- Modifies: `check_vat(ico, client=None, unreliable_check=None)` — `unreliable_check` defaults to `check_unreliable_payer` (injectable). When a DIČ is found, call it; set `is_unreliable = True` if status is `"unreliable"`, `False` if `"reliable"`, else `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/registry/test_vat_unreliable.py
import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.vat import check_vat
from rejstrik.registry.adis import UnreliablePayer

DETAIL = Path(__file__).parent.parent / "fixtures" / "ares" / "detail_00006947.json"
ARES = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00006947"


@respx.mock
def test_check_vat_sets_is_unreliable_from_adis():
    payload = json.loads(DETAIL.read_text(encoding="utf-8"))
    respx.get(ARES).mock(return_value=httpx.Response(200, json=payload))
    calls = []

    def fake_adis(dic, client=None):
        calls.append(dic)
        return UnreliablePayer(dic=dic, status="unreliable")

    status = check_vat("00006947", unreliable_check=fake_adis)
    if status.dic:  # only meaningful when the fixture company has a DIČ
        assert status.is_unreliable is True
        assert calls  # ADIS was consulted


@respx.mock
def test_check_vat_no_dic_skips_adis():
    respx.get("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/00000000").mock(
        return_value=httpx.Response(200, json={"ico": "00000000"})
    )
    called = []
    status = check_vat("00000000", unreliable_check=lambda d, client=None: called.append(d))
    assert status.is_unreliable is None
    assert called == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/registry/test_vat_unreliable.py -v`
Expected: FAIL — `TypeError` (`unreliable_check` not accepted) / `AttributeError` (`is_unreliable`).

- [ ] **Step 3: Modify `src/rejstrik/registry/vat.py`**

```python
# src/rejstrik/registry/vat.py  (full replacement)
import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client
from rejstrik.registry.adis import check_unreliable_payer

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"


class VatStatus(BaseModel):
    ico: str
    dic: str | None = None
    is_vat_payer: bool = False
    is_unreliable: bool | None = None


def parse_vat(ico: str, payload: dict) -> VatStatus:
    dic = payload.get("dic")
    registrations = payload.get("seznamRegistraci") or {}
    active_vat = registrations.get("stavZdrojeDph") == "AKTIVNI"
    return VatStatus(ico=ico.strip().zfill(8), dic=dic, is_vat_payer=bool(dic) or active_vat)


def check_vat(ico, client=None, unreliable_check=None):
    unreliable_check = unreliable_check or check_unreliable_payer
    ico = ico.strip().zfill(8)
    owns = client is None
    client = client or make_client()
    try:
        response = client.get(f"{BASE}/{ico}")
        response.raise_for_status()
        status = parse_vat(ico, response.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return VatStatus(ico=ico, dic=None, is_vat_payer=False)
    finally:
        if owns:
            client.close()

    if status.dic:
        result = unreliable_check(status.dic)
        if result is not None and getattr(result, "status", None) in ("reliable", "unreliable"):
            status.is_unreliable = result.status == "unreliable"
    return status
```

> Keep type annotations consistent with the existing module style; add `from rejstrik.registry.adis import UnreliablePayer` if you annotate `unreliable_check`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/registry/test_vat_unreliable.py tests/registry/test_vat.py -v`
Expected: PASS (existing `test_vat.py` still green — its calls don't pass `unreliable_check`, so add a stub there if any assert on a live ADIS call; the no-DIČ fixture path skips ADIS automatically).

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/registry/vat.py tests/registry/test_vat_unreliable.py
git commit -m "feat: enrich check_vat with ADIS unreliable-payer flag"
```

---

### Task 3: Unreliable-payer red flag in the analyzer

**Files:**
- Modify: `src/rejstrik/analysis/redflags.py`
- Modify: `src/rejstrik/service.py`
- Test: `tests/analysis/test_redflags_unreliable.py`
- Test: `tests/test_service_unreliable.py`

**Interfaces:**
- Modifies: `detect_red_flags(..., unreliable_vat: bool | None = None)` — when `True`, append `RedFlag(code="unreliable_vat", severity="warning", message="Registered as an unreliable VAT payer (nespolehlivý plátce DPH).")`.
- Modifies: `analyze_company_financials(query, *, llm=None, insolvency_check=None, vat_check=None)` — `vat_check` defaults to `check_vat`; call it for the company IČO, pass `unreliable_vat=vat.is_unreliable` to `detect_red_flags`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis/test_redflags_unreliable.py
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import detect_red_flags


def test_unreliable_vat_adds_warning():
    flags = detect_red_flags(NormalizedFinancials(), Ratios(), [], unreliable_vat=True)
    assert any(f.code == "unreliable_vat" and f.severity == "warning" for f in flags)


def test_reliable_or_unknown_vat_adds_no_flag():
    assert not any(f.code == "unreliable_vat" for f in detect_red_flags(NormalizedFinancials(), Ratios(), [], unreliable_vat=False))
    assert not any(f.code == "unreliable_vat" for f in detect_red_flags(NormalizedFinancials(), Ratios(), [], unreliable_vat=None))
```

```python
# tests/test_service_unreliable.py
from unittest.mock import patch

import rejstrik.service as service
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.isir import InsolvencyStatus
from rejstrik.registry.models import Company
from rejstrik.registry.vat import VatStatus

COMPANY = Company(ico="00006947", name="Test s.r.o.")
FILINGS = [Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True)]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")
STATEMENT = FinancialStatement(ico="00006947", period_year=2023, balance_sheet=[Figure(label="Aktiva celkem", value=10.0)])


def test_unreliable_payer_becomes_red_flag():
    clean_isir = lambda ico: InsolvencyStatus(ico=ico, in_insolvency=False, cases=[], checked=True)
    unreliable_vat = lambda ico: VatStatus(ico=ico, dic="CZ00006947", is_vat_payer=True, is_unreliable=True)
    with patch.object(service, "find_company", return_value=COMPANY), \
         patch.object(service, "list_filings", return_value=FILINGS), \
         patch.object(service, "load_pdf", return_value=SRC), \
         patch.object(service, "extract_financials", return_value=STATEMENT):
        report = service.analyze_company_financials("Test", insolvency_check=clean_isir, vat_check=unreliable_vat)
    assert any(f.code == "unreliable_vat" for f in report.red_flags)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/analysis/test_redflags_unreliable.py tests/test_service_unreliable.py -v`
Expected: FAIL — `TypeError` (`unreliable_vat` / `vat_check` not accepted).

- [ ] **Step 3: Modify the two files**

In `src/rejstrik/analysis/redflags.py`, add the parameter and rule:

```python
# extend the detect_red_flags signature and add this block before the final `return flags`
# signature: def detect_red_flags(n, ratios, notes, insolvent=None, unreliable_vat=None):
    if unreliable_vat is True:
        flags.append(RedFlag(code="unreliable_vat", severity="warning",
                             message="Registered as an unreliable VAT payer (nespolehlivý plátce DPH)."))
```

In `src/rejstrik/service.py`, add the import and the `vat_check` wiring:

```python
# add import
from rejstrik.registry.vat import check_vat

# in analyze_company_financials: add `vat_check=None` to the signature, then
    vat_check = vat_check or check_vat
    vat = vat_check(company.ico)
    red_flags = detect_red_flags(
        normalized, ratios, statement.notes,
        insolvent=insolvent,
        unreliable_vat=vat.is_unreliable,
    )
```

> `vat_check(company.ico)` returns a `VatStatus`; `.is_unreliable` is `None` when unknown, so the analyzer only flags confirmed unreliable payers. Keep the existing `insolvency_check` wiring intact.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/analysis/ tests/test_service_unreliable.py tests/test_service.py tests/test_service_insolvency.py -v`
Expected: PASS. If Plan-3/4 service tests call `analyze_company_financials` without a `vat_check`, add `patch.object(service, "check_vat", return_value=VatStatus(ico="00006947", is_vat_payer=False))` to them so they don't hit the live ADIS/ARES path.

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/analysis/redflags.py src/rejstrik/service.py tests/analysis/test_redflags_unreliable.py tests/test_service_unreliable.py tests/test_service.py tests/test_service_insolvency.py
git commit -m "feat: unreliable-VAT-payer red flag in analyze_company_financials"
```

---

## Part B — MCP App card

### Task 4: HTML report-card renderer (pure)

**Files:**
- Create: `src/rejstrik/mcp/card.py`
- Test: `tests/mcp/test_card.py`

**Interfaces:**
- Consumes: `CompanyFinancialReport` (analysis/report).
- Produces: `render_report_card(report: CompanyFinancialReport) -> str` — a self-contained HTML document (inline `<style>` only; no external resources; every dynamic value passed through `html.escape`). Sections: header (company name, IČO, period year), a ratios table, a red-flags list colour-coded by severity (`critical`=red, `warning`=amber, `info`=grey), and a footer naming `source_filing_title`.

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_card.py
from rejstrik.mcp.card import render_report_card
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.documents.schema import FinancialStatement

REPORT = CompanyFinancialReport(
    company_name="Test & Co s.r.o.", ico="00006947", period_year=2023, currency="CZK",
    statement=FinancialStatement(), normalized=NormalizedFinancials(),
    ratios=Ratios(current_ratio=0.5, equity_ratio=0.4),
    red_flags=[RedFlag(code="low_liquidity", severity="warning", message="Current ratio below 1.")],
    source_filing_title="Účetní závěrka 2023",
)


def test_card_is_self_contained_html():
    html = render_report_card(REPORT)
    assert html.lstrip().lower().startswith("<!doctype html") or "<html" in html.lower()
    assert "<style" in html  # inline CSS
    assert "http://" not in html and "https://" not in html  # no external resources


def test_card_includes_report_content():
    html = render_report_card(REPORT)
    assert "00006947" in html
    assert "current_ratio" in html
    assert "Current ratio below 1." in html
    assert "Účetní závěrka 2023" in html


def test_card_escapes_company_name():
    html = render_report_card(REPORT)
    assert "Test &amp; Co s.r.o." in html  # & escaped
    assert "Test & Co" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.mcp.card'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/mcp/card.py
import html

from rejstrik.analysis.report import CompanyFinancialReport

_SEVERITY_COLOR = {"critical": "#c0392b", "warning": "#e67e22", "info": "#7f8c8d"}

_STYLE = """
body{font-family:system-ui,sans-serif;margin:0;padding:16px;color:#1a1a1a}
h1{font-size:18px;margin:0 0 2px}
.sub{color:#666;font-size:13px;margin-bottom:14px}
table{border-collapse:collapse;width:100%;margin-bottom:14px}
td{padding:4px 8px;border-bottom:1px solid #eee;font-size:13px}
td.k{color:#555}
.flag{padding:6px 10px;border-radius:6px;margin:4px 0;color:#fff;font-size:13px}
.foot{color:#999;font-size:11px;margin-top:10px}
"""


def _esc(value) -> str:
    return html.escape(str(value))


def render_report_card(report: CompanyFinancialReport) -> str:
    rows = "".join(
        f"<tr><td class='k'>{_esc(name)}</td><td>{_esc('-' if v is None else round(v, 3))}</td></tr>"
        for name, v in report.ratios.model_dump().items()
    )
    if report.red_flags:
        flags = "".join(
            f"<div class='flag' style='background:{_SEVERITY_COLOR.get(f.severity, '#7f8c8d')}'>"
            f"[{_esc(f.severity.upper())}] {_esc(f.message)}</div>"
            for f in report.red_flags
        )
    else:
        flags = "<div class='flag' style='background:#27ae60'>No red flags detected.</div>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <h1>{_esc(report.company_name or "")}</h1>
  <div class="sub">IČO {_esc(report.ico or "—")} · period {_esc(report.period_year or "—")} · {_esc(report.currency or "")}</div>
  <table>{rows}</table>
  {flags}
  <div class="foot">Source: {_esc(report.source_filing_title or "Sbírka listin")}</div>
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/mcp/test_card.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/mcp/card.py tests/mcp/test_card.py
git commit -m "feat: self-contained HTML report-card renderer"
```

---

### Task 5: `analyze_company_card` MCP tool (UI resource)

**Files:**
- Modify: `pyproject.toml` (add `mcp-ui-server`)
- Modify: `src/rejstrik/mcp/server.py`
- Test: `tests/mcp/test_card_tool.py`

**Interfaces:**
- Consumes: `render_report_card` (Task 4), `analyze_company_financials` (service), `create_ui_resource` (`mcp_ui_server`).
- Modifies: `EXPOSED_TOOL_NAMES` → append `"analyze_company_card"` (now 9).
- Adds: `@mcp.tool() def analyze_company_card(query: str) -> list[UIResource]` — runs the analysis, renders the card, returns one `create_ui_resource({"uri": "ui://rejstrik/report", "content": {"type": "rawHtml", "htmlString": <html>}, "encoding": "text"})`. The existing text tool `analyze_company_financials` remains the non-UI fallback.

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_card_tool.py
import asyncio
from unittest.mock import patch

from rejstrik.mcp import server
from rejstrik.analysis.report import CompanyFinancialReport
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.documents.schema import FinancialStatement

REPORT = CompanyFinancialReport(
    company_name="Test s.r.o.", ico="00006947", period_year=2023, currency="CZK",
    statement=FinancialStatement(), normalized=NormalizedFinancials(), ratios=Ratios(),
    red_flags=[], source_filing_title="Účetní závěrka 2023",
)


def test_card_tool_in_exposed_names():
    assert "analyze_company_card" in server.EXPOSED_TOOL_NAMES
    assert len(server.EXPOSED_TOOL_NAMES) == 9


def test_card_tool_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "analyze_company_card" in names


def test_card_tool_returns_ui_resource():
    with patch.object(server, "_analyze_company_financials", return_value=REPORT):
        result = server.analyze_company_card("Test")
    assert isinstance(result, list) and len(result) == 1
    # the UI resource carries a ui:// uri
    res = result[0]
    dumped = res.model_dump() if hasattr(res, "model_dump") else res
    assert "ui://rejstrik/report" in str(dumped)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/mcp/test_card_tool.py -v`
Expected: FAIL — `AttributeError` / count is 8.

- [ ] **Step 3: Modify `pyproject.toml` and `server.py`**

Add `"mcp-ui-server>=0.1"` to `dependencies` in `pyproject.toml`.

```python
# add to imports in src/rejstrik/mcp/server.py
from mcp_ui_server import create_ui_resource
from mcp_ui_server.core import UIResource

from rejstrik.mcp.card import render_report_card
```

```python
# append "analyze_company_card" to EXPOSED_TOOL_NAMES in src/rejstrik/mcp/server.py
# (list now ends with: ..., "check_vat", "analyze_company_card")
```

```python
# add near analyze_company_financials in src/rejstrik/mcp/server.py
@mcp.tool()
def analyze_company_card(query: str) -> list[UIResource]:
    """Full financial report rendered as an interactive HTML card (cited ratios + red flags)."""
    report = _analyze_company_financials(query)
    html = render_report_card(report)
    return [
        create_ui_resource({
            "uri": "ui://rejstrik/report",
            "content": {"type": "rawHtml", "htmlString": html},
            "encoding": "text",
        })
    ]
```

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]" && python -m pytest tests/mcp/test_card_tool.py tests/mcp/test_server.py tests/mcp/test_breadth_tools.py -v`
Expected: PASS. Update the `EXPOSED_TOOL_NAMES` length assertion in `tests/mcp/test_breadth_tools.py` (was 8) and any equality assertion in `tests/mcp/test_server.py` to expect 9 names.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 6: Manual smoke (real API + UI host — NOT in CI)**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
rejstrik-mcp &
# In an MCP UI-capable client (mcp-ui playground or a UI-enabled host), call
# analyze_company_card("Budějovický Budvar") and confirm the card renders with
# ratios + red flags. In a text-only host, fall back to analyze_company_financials.
kill %1
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/rejstrik/mcp/server.py tests/mcp/test_card_tool.py tests/mcp/test_server.py tests/mcp/test_breadth_tools.py
git commit -m "feat: analyze_company_card MCP tool returning interactive UI resource"
```

---

### Task 6: README + lint

**Files:**
- Modify: `README.md`
- Modify: any files flagged by `ruff`.

- [ ] **Step 1: Update README**

Add: the unreliable-payer flag to the `check_vat` / analysis description and red-flag list; an "Interactive card" subsection describing `analyze_company_card` (renders in MCP UI-capable hosts; text tool is the fallback). Update the tool count to 9.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: clean (run `ruff format src/ tests/` to fix, then re-run).

- [ ] **Step 3: Run full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md src/ tests/
git commit -m "docs: README unreliable-payer + interactive card; lint clean"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- ADIS "unreliable payer" (the explicitly-deferred Plan-4 item) → Tasks 1–3 (client, `check_vat` enrichment, red flag). ✓
- Interactive MCP App card (the one remaining design-spec extra) → Tasks 4–5 (`render_report_card` + `analyze_company_card` UI tool). ✓
- "return JSON, and optionally an MCP App card so the result renders as an interactive table in-chat" (design spec) → both paths exist: `analyze_company_financials` (structured/text) and `analyze_company_card` (UI). ✓
- Attribution for adapted ADIS code → source header on `adis.py` (`cz-agents-mcp`, MIT — `LICENSES/` already present from Plan 4). ✓

**Placeholder scan:** No TBD/TODO. The ADIS request/response element names (Task 1) are written to the documented shape with an explicit "confirm against the captured fixture and adjust together" instruction — the standard SOAP-discovery loop (identical to the ISIR client already shipped), not unfinished work. The live SOAP call and in-client card rendering are explicit manual smoke steps.

**Type consistency:** `UnreliablePayer(dic, status)` identical across Tasks 1/2. `VatStatus` gains `is_unreliable: bool | None` consistently (Tasks 2/3). `detect_red_flags(..., insolvent=None, unreliable_vat=None)` extends Plan 3/4's signature additively. `analyze_company_financials(query, *, llm=None, insolvency_check=None, vat_check=None)` extends Plan 4's signature additively (old callers unaffected). `render_report_card(report) -> str` consumed by `analyze_company_card` (Tasks 4/5). `EXPOSED_TOOL_NAMES` is the single source for the count assertions (now 9). ✓

**Dependency note:** This plan assumes Plans 1–4 are implemented (they are — verified live). `mcp-ui-server` is a new dependency; client-side rendering depends on the host supporting the MCP Apps / mcp-ui extension, so the card is additive and never breaks text-only hosts.
