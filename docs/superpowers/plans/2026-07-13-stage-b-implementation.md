# Stage B: Hermetic Tests, Windows CI, README Fact Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `python -m pytest -q` pass hermetically on a Windows dev machine that has a real `.env`, add Windows to CI, and correct false claims in the README.

**Architecture:** Fix the root cause of key leakage in `documents/config.py` (dotenv is re-loaded on every call, overriding tests' `monkeypatch.delenv`) by loading it at most once per process and adding an autouse test fixture that blanks keys and disables the loader. Make the one Windows-hostile test fixture build an absolute path, and defensively guard `get_filing` against non-absolute paths. Add `windows-latest` to CI. Fix three README facts and add a legal-form code→name mapping.

**Tech Stack:** Python 3.11+, pytest, python-dotenv, pydantic, FastMCP (`mcp` package), respx (HTTP mocking), ruff, GitHub Actions.

## Global Constraints

- Package root is `src/rejstrik/`; tests live under `tests/` and import via `rejstrik.*` (pytest `pythonpath = ["src"]`).
- Tests are **offline and key-free**. Never make real network calls; never require an API key. Mock HTTP with `respx`.
- Follow strict TDD: write the failing test first, run it to confirm it fails, write the minimal implementation, run it to confirm it passes, commit.
- Every task ends by running the full gate: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q` — all three must pass before committing.
- Code style: double-quoted strings, ruff-formatted. Match the surrounding code.
- Corrected ESM closure date (verified 2026-07-13): **2025-12-17** (Czech beneficial-owners register public access closed 17 December 2025, per the 25 August 2025 Czech Supreme Court ruling applying the 22 November 2022 CJEU judgment). The README's `2026-12-17` is wrong.

---

### Task 1: Hermetic dotenv loading + autouse test fixture

Root cause of the 6 Windows failures: `documents/config.py::_load_local_env()` calls `load_dotenv(find_dotenv(usecwd=True))` on **every** `has_llm_key()` / `resolve_provider()` call, re-importing the repo `.env` (which legitimately holds `OPENAI_API_KEY`) *after* tests `monkeypatch.delenv` it. Fix: load at most once per process so post-import env mutations are respected, and add an autouse fixture that blanks the keys and disables the loader for the whole suite.

**Files:**
- Modify: `src/rejstrik/documents/config.py`
- Create: `tests/conftest.py`
- Test: `tests/documents/test_config.py` (add one test; existing tests must go green **without editing their assertions**)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `config._load_local_env() -> None` — loads the repo `.env` at most once per process; no-op when `config._DOTENV_DISABLED` is `True`.
  - `config._DOTENV_DISABLED: bool` — module flag; set `True` to disable loading.
  - `config._reset_dotenv_cache() -> None` — test helper that forgets the "already loaded" state.
  - `config.load_dotenv`, `config.find_dotenv` — module-level names (imported from `dotenv`) that tests may monkeypatch.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/documents/test_config.py`:

```python
def test_dotenv_loaded_at_most_once_per_process(monkeypatch):
    from rejstrik.documents import config

    monkeypatch.setattr(config, "_DOTENV_DISABLED", False)
    config._reset_dotenv_cache()

    calls = []
    monkeypatch.setattr(config, "find_dotenv", lambda **kwargs: "/tmp/.env")
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: calls.append(1))

    config._load_local_env()
    config._load_local_env()
    config.has_llm_key()

    assert calls == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_config.py::test_dotenv_loaded_at_most_once_per_process -v`
Expected: FAIL — either `AttributeError: ... '_DOTENV_DISABLED'` / `'_reset_dotenv_cache'`, or `assert [1, 1, 1] == [1]` (current code loads on every call).

- [ ] **Step 3: Write the minimal implementation**

Replace the entire contents of `src/rejstrik/documents/config.py` with:

```python
import os

from dotenv import find_dotenv, load_dotenv

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_OPENAI_MODEL = "gpt-4.1"

# Set True by the test suite so a developer's real repo .env never leaks API
# keys into the offline, key-free tests.
_DOTENV_DISABLED = False
_dotenv_loaded = False


def _reset_dotenv_cache() -> None:
    """Test helper: forget that the .env was already loaded this process."""
    global _dotenv_loaded
    _dotenv_loaded = False


def _load_local_env() -> None:
    """Load the repo .env at most once per process.

    Loading once (instead of on every call) means environment mutations made
    after the first call are respected, and removes per-call disk I/O on a hot
    path.
    """
    global _dotenv_loaded
    if _DOTENV_DISABLED or _dotenv_loaded:
        return
    load_dotenv(find_dotenv(usecwd=True))
    _dotenv_loaded = True


def resolve_provider() -> str:
    _load_local_env()
    configured = os.environ.get("REJSTRIK_LLM_PROVIDER")
    if configured:
        return configured.strip().lower()
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def resolve_model(provider: str | None = None) -> str:
    provider = provider or "anthropic"
    fallback = DEFAULT_OPENAI_MODEL if provider == "openai" else DEFAULT_MODEL
    return os.environ.get("REJSTRIK_MODEL") or fallback


def has_llm_key() -> bool:
    _load_local_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))
```

- [ ] **Step 4: Create the autouse fixture**

Create `tests/conftest.py` with exactly:

```python
import pytest

from rejstrik.documents import config


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Make the suite pass identically with or without a repo .env present.

    Blanks the LLM keys and disables the dotenv loader so a developer's real
    .env (which legitimately holds OPENAI_API_KEY for keyed smoke testing)
    cannot leak into these offline, key-free tests. Keyed-mode tests set keys
    explicitly; the dotenv-loading tests re-enable the loader themselves.
    """
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "REJSTRIK_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "_DOTENV_DISABLED", True)
    config._reset_dotenv_cache()
```

Note: the existing `test_resolve_provider_prefers_openai_key_from_dotenv` writes a real `.env` in `tmp_path` and expects it loaded. It must re-enable the loader. Edit that test in `tests/documents/test_config.py` so its body reads (add the two marked lines; keep every existing assertion unchanged):

```python
def test_resolve_provider_prefers_openai_key_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_DOTENV_DISABLED", False)  # re-enable loader
    config._reset_dotenv_cache()  # forget the disabled no-op load
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("REJSTRIK_LLM_PROVIDER", raising=False)

    assert config.resolve_provider() == "openai"
```

- [ ] **Step 5: Run the affected tests to verify they pass**

Run: `python -m pytest tests/documents/test_config.py tests/mcp/test_keyed_degradation.py -v`
Expected: PASS — including `test_has_llm_key_false_when_unset`, all four `test_keyed_degradation` cases, and the new once-per-process test.

- [ ] **Step 6: Prove hermeticity with a fake key in the environment**

Run: `OPENAI_API_KEY=sk-leak python -m pytest tests/documents/test_config.py::test_has_llm_key_false_when_unset tests/mcp/test_keyed_degradation.py -q`
Expected: PASS — the autouse fixture blanks the injected key, so the key-free tests still pass. (This simulates the Windows dev machine's real `.env`.)

- [ ] **Step 7: Run the full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all three pass.

- [ ] **Step 8: Commit**

```bash
git add src/rejstrik/documents/config.py tests/conftest.py tests/documents/test_config.py
git commit -m "fix(config): load .env once per process; hermetic test fixture"
```

---

### Task 2: Windows-portable get_filing fixture + non-absolute path guard

`tests/mcp/test_get_filing.py` fakes `file_path="/cache/00514152-2024-abcd1234.pdf"`, which is not absolute on Windows, so `Path(...).as_uri()` raises `ValueError` and the test crashes. Fix the fixture to build a genuinely absolute path via `tmp_path`, and defensively guard `get_filing` so any host-supplied non-absolute path falls back to plain text instead of crashing the tool.

Audit note: the only hardcoded absolute-path fixture in the suite is `tests/mcp/test_get_filing.py:22` (verified via `grep -rn 'file_path="/' tests/`). No other file needs this change.

**Files:**
- Modify: `tests/mcp/test_get_filing.py`
- Modify: `src/rejstrik/mcp/server.py` (function `get_filing`, lines 158-192)

**Interfaces:**
- Consumes: `server.get_filing(ico, year=None, filing_id=None) -> list[TextContent | EmbeddedResource]`; `server._fetch_filing`; `rejstrik.service.FilingDocument`; `rejstrik.documents.source.PdfSource`.
- Produces: `get_filing` returns a `TextContent` fallback as `parts[1]` (instead of raising) when `doc.file_path` is not absolute.

- [ ] **Step 1: Rewrite the test module to use tmp_path and add the guard test**

Replace the entire contents of `tests/mcp/test_get_filing.py` with:

```python
import asyncio
import base64
import hashlib
import json

from mcp.types import EmbeddedResource, TextContent

from rejstrik.documents.source import PdfSource
from rejstrik.mcp import server
from rejstrik.service import FilingDocument

_PDF = b"%PDF-1.4 fake"


def _make_fake_fetch(file_path):
    def _fake_fetch(query, year=None, filing_id=None):
        doc = FilingDocument(
            ico="00514152",
            company_name="Budvar",
            title="ucetni zaverka 2024",
            year=2024,
            pdf_url="https://verejnerejstriky.msp.gov.cz/dokumenty/sbirka-listin/aaa",
            file_path=str(file_path),
            sha256=hashlib.sha256(_PDF).hexdigest(),
            size_bytes=len(_PDF),
        )
        return doc, PdfSource(data=_PDF, sha256=doc.sha256, filename="filing.pdf")

    return _fake_fetch


def test_get_filing_returns_metadata_and_blob(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    parts = server.get_filing("00514152")
    assert isinstance(parts[0], TextContent)
    meta = json.loads(parts[0].text)
    assert meta["year"] == 2024
    assert meta["file_path"].endswith(".pdf")
    blob_part = parts[1]
    assert isinstance(blob_part, EmbeddedResource)
    assert blob_part.resource.mimeType == "application/pdf"
    assert base64.standard_b64decode(blob_part.resource.blob) == _PDF


def test_get_filing_skips_blob_when_too_large(monkeypatch, tmp_path):
    pdf_path = tmp_path / "00514152-2024-abcd1234.pdf"
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch(pdf_path))
    monkeypatch.setattr(server, "_MAX_EMBED_BYTES", 4)
    parts = server.get_filing("00514152")
    assert len(parts) == 2
    assert isinstance(parts[1], TextContent)
    assert "file_path" in parts[1].text


def test_get_filing_falls_back_when_path_not_absolute(monkeypatch):
    monkeypatch.setattr(server, "_fetch_filing", _make_fake_fetch("cache/rel.pdf"))
    parts = server.get_filing("00514152")
    assert len(parts) == 2
    assert isinstance(parts[1], TextContent)
    assert "rel.pdf" in parts[1].text


def test_get_filing_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert "get_filing" in {t.name for t in tools}
```

- [ ] **Step 2: Run the tests to verify the guard test fails**

Run: `python -m pytest tests/mcp/test_get_filing.py -v`
Expected: `test_get_filing_falls_back_when_path_not_absolute` FAILS with `ValueError: relative path can't be expressed as a file URI` (the other three should already pass, since they now use absolute `tmp_path`).

- [ ] **Step 3: Add the path guard in `get_filing`**

In `src/rejstrik/mcp/server.py`, replace the embed block inside `get_filing` (currently lines 171-191, the `if doc.size_bytes <= _MAX_EMBED_BYTES: ... else: ...`) with:

```python
    if doc.size_bytes <= _MAX_EMBED_BYTES:
        try:
            uri = Path(doc.file_path).as_uri()
        except ValueError:
            uri = None
        if uri is not None:
            parts.append(
                EmbeddedResource(
                    type="resource",
                    resource=BlobResourceContents(
                        uri=uri,
                        mimeType="application/pdf",
                        blob=base64.standard_b64encode(source.data).decode(),
                    ),
                )
            )
        else:
            parts.append(
                TextContent(
                    type="text",
                    text=(
                        f"PDF at {doc.file_path} could not be embedded "
                        f"(path is not absolute). Read it from that path."
                    ),
                )
            )
    else:
        parts.append(
            TextContent(
                type="text",
                text=(
                    f"PDF is {doc.size_bytes} bytes — too large to embed. "
                    f"Read it from file_path: {doc.file_path}"
                ),
            )
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/mcp/test_get_filing.py -v`
Expected: all four PASS.

- [ ] **Step 5: Run the full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all three pass.

- [ ] **Step 6: Commit**

```bash
git add tests/mcp/test_get_filing.py src/rejstrik/mcp/server.py
git commit -m "fix(mcp): absolute-path test fixture + get_filing path guard"
```

---

### Task 3: Legal-form code→name mapping

`find_company` returns the raw `legal_form` code (e.g. `"302"`). Add a small static code→name mapping and surface `legal_form_name` alongside the code on the `Company` model, populated in ARES parsing.

**Files:**
- Modify: `src/rejstrik/registry/models.py`
- Modify: `src/rejstrik/registry/ares.py` (function `parse_detail`, lines 15-23)
- Test: `tests/registry/test_models.py`

**Interfaces:**
- Consumes: `Company` (pydantic `BaseModel`) with fields `ico`, `name`, `address`, `legal_form`, `founded`.
- Produces:
  - `Company.legal_form_name: str | None` — new optional field.
  - `models.LEGAL_FORM_NAMES: dict[str, str]` — code→Czech-name mapping.
  - `models.legal_form_name(code: str | None) -> str | None` — lookup helper.
  - `parse_detail(payload)` sets `legal_form_name` from `legal_form`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/registry/test_models.py`:

```python
from rejstrik.registry.models import legal_form_name


def test_legal_form_name_maps_known_code():
    assert legal_form_name("302") == "národní podnik"
    assert legal_form_name("112") == "společnost s ručením omezeným (s.r.o.)"


def test_legal_form_name_unknown_returns_none():
    assert legal_form_name("99999") is None
    assert legal_form_name(None) is None


def test_company_carries_legal_form_name():
    c = Company(ico="00514152", name="Budvar", legal_form="302")
    c2 = Company(ico="00514152", name="Budvar", legal_form="302", legal_form_name="národní podnik")
    assert c.legal_form_name is None
    assert c2.legal_form_name == "národní podnik"
```

Add to the end of `tests/registry/test_search.py`:

```python
def test_parse_detail_sets_legal_form_name():
    from rejstrik.registry.ares import parse_detail

    company = parse_detail(
        {"ico": "00514152", "obchodniJmeno": "Budějovický Budvar", "pravniForma": "302"}
    )
    assert company.legal_form == "302"
    assert company.legal_form_name == "národní podnik"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/registry/test_models.py tests/registry/test_search.py::test_parse_detail_sets_legal_form_name -v`
Expected: FAIL — `ImportError: cannot import name 'legal_form_name'` and `AttributeError`/validation on `legal_form_name`.

- [ ] **Step 3: Add the mapping and field to the model**

Replace the entire contents of `src/rejstrik/registry/models.py` with:

```python
from pydantic import BaseModel, field_validator

# Common ARES právní forma (legal form) codes → Czech names. Not exhaustive;
# unknown codes surface as None so the raw legal_form code is still available.
LEGAL_FORM_NAMES: dict[str, str] = {
    "101": "OSVČ (živnostník)",
    "111": "veřejná obchodní společnost (v.o.s.)",
    "112": "společnost s ručením omezeným (s.r.o.)",
    "113": "komanditní společnost (k.s.)",
    "121": "akciová společnost (a.s.)",
    "205": "družstvo",
    "301": "státní podnik",
    "302": "národní podnik",
    "421": "odštěpný závod zahraniční právnické osoby",
    "641": "spolek",
    "801": "obec",
}


def legal_form_name(code: str | None) -> str | None:
    """Map an ARES legal-form code to its Czech name, or None if unknown."""
    if code is None:
        return None
    return LEGAL_FORM_NAMES.get(code.strip())


class Company(BaseModel):
    ico: str
    name: str
    address: str | None = None
    legal_form: str | None = None
    legal_form_name: str | None = None
    founded: str | None = None

    @field_validator("ico")
    @classmethod
    def pad_ico(cls, v: str) -> str:
        return v.strip().zfill(8)
```

- [ ] **Step 4: Populate the field in ARES parsing**

In `src/rejstrik/registry/ares.py`, update the import and `parse_detail`:

Change the import line (line 4):

```python
from rejstrik.registry.models import Company, legal_form_name
```

Replace `parse_detail` (lines 15-23) with:

```python
def parse_detail(payload: dict) -> Company:
    sidlo = payload.get("sidlo") or {}
    legal_form = payload.get("pravniForma")
    return Company(
        ico=str(payload["ico"]),
        name=payload.get("obchodniJmeno") or "",
        address=sidlo.get("textovaAdresa"),
        legal_form=legal_form,
        legal_form_name=legal_form_name(legal_form),
        founded=payload.get("datumVzniku"),
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/registry/test_models.py tests/registry/test_search.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all three pass.

- [ ] **Step 7: Commit**

```bash
git add src/rejstrik/registry/models.py src/rejstrik/registry/ares.py tests/registry/test_models.py tests/registry/test_search.py
git commit -m "feat(registry): surface legal_form_name from ARES code mapping"
```

---

### Task 4: Add Windows to CI matrix

Add `windows-latest` to the CI matrix so path/env semantics (`Path.as_uri()`, dotenv, absolute paths) are exercised on Windows. Keep the ruff lint steps Linux-only (runtime economy — the point is path/env semantics, not lint portability); run pytest on both OSes.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none (CI config).

- [ ] **Step 1: Rewrite the workflow with an OS matrix and Linux-only lint**

Replace the entire contents of `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-latest
            python-version: "3.11"
          - os: ubuntu-latest
            python-version: "3.12"
          - os: windows-latest
            python-version: "3.12"
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install
        run: pip install -e ".[dev]"
      - name: Lint
        if: runner.os == 'Linux'
        run: |
          ruff check src/ tests/
          ruff format --check src/ tests/
      - name: Test
        run: python -m pytest -q
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('ok')"`
Expected: prints `ok` with no traceback. (If PyYAML is not installed, run `pip install pyyaml` first, or skip — the workflow is validated by GitHub on push.)

- [ ] **Step 3: Run the full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all three pass (unchanged by this task, but confirms nothing regressed).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add windows-latest to test matrix; lint on Linux only"
```

---

### Task 5: README fact fixes

Three factual corrections on the repo front page: fix the ESM closure date, remove the two broken image references, and (already delivered in Task 3) update the tool table wording is not required — only the three items below.

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Fix the ESM closure date**

In `README.md`, the beneficial-owners paragraph currently reads (lines 67-70):

```
**Beneficial owners.** The public part of ESM (Evidence skutečných
majitelů) closed on 2026-12-17 following an EU Court of Justice ruling, so
beneficial-owner lookups are intentionally not offered here — a documented
scope decision, not a gap.
```

Change `2026-12-17` to `2025-12-17` so it reads:

```
**Beneficial owners.** The public part of ESM (Evidence skutečných
majitelů) closed on 2025-12-17 following an EU Court of Justice ruling, so
beneficial-owner lookups are intentionally not offered here — a documented
scope decision, not a gap.
```

- [ ] **Step 2: Remove the broken media section**

In `README.md`, delete the entire "See it work" section (currently lines 83-89):

```
## See it work

![3-year analysis of Budějovický Budvar](docs/media/budvar-3year.gif)

*The interactive report card (MCP UI hosts):*

![Report card](docs/media/report-card.png)
```

Delete those lines outright (heading, both image references, and the caption). Broken images on the front page cost more credibility than an absent media section; real media lands in Stage E. Leave the surrounding blank lines tidy so `## How it works` follows the keyed-power-mode paragraph with a single blank line between them.

- [ ] **Step 3: Verify no broken references remain**

Run: `grep -n "2026-12-17\|docs/media" README.md`
Expected: no output (exit code 1) — the wrong date and both broken image paths are gone.

- [ ] **Step 4: Run the full gate**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all three pass (README-only change; confirms nothing regressed).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: correct ESM closure date; drop broken media refs"
```

---

## Self-Review

**Spec coverage:**
- §1 Hermetic LLM-key detection → Task 1 (once-per-process load + autouse fixture; the named failing tests `test_has_llm_key_false_when_unset` and the four `test_keyed_degradation` cases go green without assertion edits; verified with an injected key in Step 6).
- §2 Windows-portable fixtures + `get_filing` path guard → Task 2 (tmp_path fixture, suite audit noted, defensive `as_uri()` guard with new test).
- §3 CI gains Windows → Task 4 (`windows-latest` at Python 3.12; pytest both OSes; ruff Linux-only).
- §4 README fact fixes → Task 5 (ESM date `2025-12-17`, broken images removed) + Task 3 (`legal_form_name` mapping surfaced on `find_company`).
- Testing/Acceptance (new unit tests: dotenv loaded once, legal-form mapping, `get_filing` path-guard branch) → covered in Tasks 1, 3, 2 respectively.

**Placeholder scan:** No TBD/TODO/"add error handling"/"write tests for the above". Every code step shows complete code; every command shows expected output.

**Type consistency:** `legal_form_name` used identically as field name and helper function name across Tasks 3's model, ares.py, and tests. `_DOTENV_DISABLED` / `_reset_dotenv_cache` / `_load_local_env` names consistent between config.py (Task 1), conftest.py, and the config tests. `_make_fake_fetch` / `server._fetch_filing` / `FilingDocument` fields consistent in Task 2.
