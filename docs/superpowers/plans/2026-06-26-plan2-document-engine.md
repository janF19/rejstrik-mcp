# Plan 2 — Document Engine (`extract_financials` + `ask_filing`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a company's Sbírka listin financial-statement PDF, extract a structured, page-cited financial schema (`extract_financials`) and answer arbitrary questions over the full report with page citations (`ask_filing`) — the project's moat.

**Architecture:** Build on Plan 1's `registry`/`filings`/`cli` spine. A new `documents/` package: resolve a filing to PDF bytes, then send the PDF to Claude two ways — `messages.parse` with a Pydantic schema for deterministic extraction, and `messages.create` with citations enabled for open-ended Q&A. Claude reads PDFs natively (base64 document blocks, scanned pages handled by built-in vision), so there is **no** OCR pipeline, image rendering, or vector DB in v1. The Anthropic SDK is isolated behind a `DocumentLLM` protocol so all orchestration is unit-tested against a fake; real API calls are a manual smoke test only.

**Tech Stack:** Python 3.11+, `anthropic` SDK, `pydantic` v2, plus Plan 1's stack (`httpx`, `typer`, `selectolax`, `pytest`, `respx`).

## Global Constraints

- Python 3.11+; all public functions fully type-annotated; return Pydantic models, never raw dicts. (Inherited from Plan 1.)
- **Model:** default `claude-opus-4-8` everywhere. Do not substitute a cheaper model without the user's explicit choice. The model ID is a single constant in `documents/config.py` (`DEFAULT_MODEL`); a Haiku cost-lever override is exposed via env (`REJSTRIK_MODEL`) but defaults to Opus.
- **Thinking/params:** On `claude-opus-4-8`, do NOT send `temperature`/`top_p`/`top_k` or `budget_tokens` (all 400). Extraction runs with defaults (deterministic). If thinking is ever added, use `thinking={"type": "adaptive"}` only.
- **Citations vs structured output are mutually exclusive** — never set `citations` on a request that also uses `output_format`/`output_config.format` (400). `extract_financials` = structured output (page numbers live in the schema). `ask_filing` = citations.
- **No network in tests.** Anthropic calls go through the `DocumentLLM` protocol; tests inject `FakeDocumentLLM`. PDF downloads are `respx`-mocked or read from `tmp_path`. The real `AnthropicDocumentLLM` is exercised only by a manual smoke step (clearly marked, not in CI).
- API key via `ANTHROPIC_API_KEY` env (the SDK reads it; never hardcode).
- All PDF byte access flows through `documents/source.py` — never read PDF bytes elsewhere.

---

### Task 1: Dependencies + model config

**Files:**
- Modify: `pyproject.toml` (add `anthropic` to `dependencies`)
- Create: `src/rejstrik/documents/__init__.py`
- Create: `src/rejstrik/documents/config.py`
- Test: `tests/documents/test_config.py`
- Create: `tests/documents/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DEFAULT_MODEL: str` and `resolve_model() -> str` (returns `REJSTRIK_MODEL` env override if set, else `DEFAULT_MODEL`).

- [ ] **Step 1: Write the failing test**

```python
# tests/documents/test_config.py
import importlib

from rejstrik.documents import config


def test_default_model_is_opus():
    assert config.DEFAULT_MODEL == "claude-opus-4-8"


def test_resolve_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("REJSTRIK_MODEL", "claude-haiku-4-5")
    assert config.resolve_model() == "claude-haiku-4-5"


def test_resolve_model_defaults_to_opus(monkeypatch):
    monkeypatch.delenv("REJSTRIK_MODEL", raising=False)
    assert config.resolve_model() == "claude-opus-4-8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.documents'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/__init__.py
```

```python
# src/rejstrik/documents/config.py
import os

DEFAULT_MODEL = "claude-opus-4-8"


def resolve_model() -> str:
    return os.environ.get("REJSTRIK_MODEL") or DEFAULT_MODEL
```

Add `anthropic>=0.92` to the `dependencies` list in `pyproject.toml`.

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]" && python -m pytest tests/documents/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/rejstrik/documents/ tests/documents/
git commit -m "feat: documents package scaffold + model config"
```

---

### Task 2: PDF source resolver

**Files:**
- Create: `src/rejstrik/documents/source.py`
- Test: `tests/documents/test_source.py`

**Interfaces:**
- Consumes: `make_client` (Plan 1 `core/http.py`), `Filing` (Plan 1 `filings/models.py`).
- Produces: `PdfSource` Pydantic model: `data: bytes`, `sha256: str`, `filename: str`.
- Produces: `load_pdf(ref: str | Filing, client: httpx.Client | None = None) -> PdfSource` — if `ref` is a `Filing`, use its `pdf_url`; if `ref` is an existing local path, read bytes; if `ref` is an `http(s)` URL, download via the shared client. Computes `sha256`.

- [ ] **Step 1: Write the failing test**

```python
# tests/documents/test_source.py
import hashlib
from pathlib import Path

import httpx
import respx

from rejstrik.documents.source import load_pdf, PdfSource
from rejstrik.filings.models import Filing

PDF_BYTES = b"%PDF-1.4 fake pdf bytes"


def test_load_pdf_from_local_path(tmp_path: Path):
    p = tmp_path / "report.pdf"
    p.write_bytes(PDF_BYTES)
    src = load_pdf(str(p))
    assert isinstance(src, PdfSource)
    assert src.data == PDF_BYTES
    assert src.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert src.filename == "report.pdf"


@respx.mock
def test_load_pdf_from_url():
    url = "https://or.justice.cz/ias/content/download?id=abc"
    respx.get(url).mock(return_value=httpx.Response(200, content=PDF_BYTES))
    src = load_pdf(url)
    assert src.data == PDF_BYTES
    assert src.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()


@respx.mock
def test_load_pdf_from_filing_uses_pdf_url():
    url = "https://or.justice.cz/ias/content/download?id=xyz"
    respx.get(url).mock(return_value=httpx.Response(200, content=PDF_BYTES))
    filing = Filing(title="Účetní závěrka 2023", year=2023, pdf_url=url, is_financial_statement=True)
    src = load_pdf(filing)
    assert src.data == PDF_BYTES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.documents.source'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/source.py
import hashlib
import os

import httpx
from pydantic import BaseModel

from rejstrik.core.http import make_client
from rejstrik.filings.models import Filing


class PdfSource(BaseModel):
    data: bytes
    sha256: str
    filename: str


def _make(data: bytes, filename: str) -> PdfSource:
    return PdfSource(data=data, sha256=hashlib.sha256(data).hexdigest(), filename=filename)


def load_pdf(ref: str | Filing, client: httpx.Client | None = None) -> PdfSource:
    url = ref.pdf_url if isinstance(ref, Filing) else ref

    if not url.lower().startswith(("http://", "https://")) and os.path.exists(url):
        with open(url, "rb") as fh:
            return _make(fh.read(), os.path.basename(url))

    owns = client is None
    client = client or make_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return _make(resp.content, "filing.pdf")
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_source.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/source.py tests/documents/test_source.py
git commit -m "feat: PDF source resolver (path/url/filing -> bytes + sha256)"
```

---

### Task 3: Financial-statement schema

**Files:**
- Create: `src/rejstrik/documents/schema.py`
- Test: `tests/documents/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all structured-output-safe — basic types only, no min/max/length constraints):
  - `Figure`: `label: str`, `value: float | None`, `source_page: int | None`.
  - `NoteItem`: `topic: str`, `summary: str`, `source_page: int | None`.
  - `FinancialStatement`: `company_name: str | None`, `ico: str | None`, `period_year: int | None`, `currency: str | None`, `balance_sheet: list[Figure]`, `income_statement: list[Figure]`, `cash_flow: list[Figure]`, `notes: list[NoteItem]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/documents/test_schema.py
from rejstrik.documents.schema import Figure, NoteItem, FinancialStatement


def test_figure_optional_fields():
    f = Figure(label="Revenue")
    assert f.value is None
    assert f.source_page is None


def test_financial_statement_round_trip():
    fs = FinancialStatement(
        company_name="Test s.r.o.",
        ico="00006947",
        period_year=2023,
        currency="CZK",
        balance_sheet=[Figure(label="Total assets", value=1000.0, source_page=12)],
        income_statement=[Figure(label="Revenue", value=500.0, source_page=14)],
        cash_flow=[],
        notes=[NoteItem(topic="Related parties", summary="Loan to director", source_page=43)],
    )
    dumped = fs.model_dump()
    restored = FinancialStatement(**dumped)
    assert restored.balance_sheet[0].source_page == 12
    assert restored.notes[0].topic == "Related parties"


def test_financial_statement_defaults_empty_lists():
    fs = FinancialStatement()
    assert fs.balance_sheet == []
    assert fs.notes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/schema.py
from pydantic import BaseModel


class Figure(BaseModel):
    label: str
    value: float | None = None
    source_page: int | None = None


class NoteItem(BaseModel):
    topic: str
    summary: str
    source_page: int | None = None


class FinancialStatement(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    balance_sheet: list[Figure] = []
    income_statement: list[Figure] = []
    cash_flow: list[Figure] = []
    notes: list[NoteItem] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/schema.py tests/documents/test_schema.py
git commit -m "feat: financial-statement extraction schema"
```

---

### Task 4: Answer model + citation parsing

**Files:**
- Create: `src/rejstrik/documents/answer.py`
- Test: `tests/documents/test_answer.py`

**Interfaces:**
- Consumes: nothing (operates on duck-typed Anthropic response content).
- Produces: `Citation`: `cited_text: str`, `page: int | None`.
- Produces: `Answer`: `text: str`, `citations: list[Citation]`.
- Produces: `parse_answer(content: list) -> Answer` — concatenates `text`-type blocks into `text`; collects every citation across blocks, mapping `page_location` citations to `Citation(cited_text, start_page_number)`. Tolerates blocks/citations supplied as objects with attributes (the SDK shape).

- [ ] **Step 1: Write the failing test**

```python
# tests/documents/test_answer.py
from types import SimpleNamespace

from rejstrik.documents.answer import parse_answer, Answer, Citation


def _citation(cited_text, page):
    return SimpleNamespace(type="page_location", cited_text=cited_text, start_page_number=page)


def _text_block(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def test_parse_answer_concatenates_text():
    content = [_text_block("Yes, there is a pledge "), _text_block("over the building.")]
    ans = parse_answer(content)
    assert isinstance(ans, Answer)
    assert ans.text == "Yes, there is a pledge over the building."
    assert ans.citations == []


def test_parse_answer_collects_page_citations():
    content = [
        _text_block("A pledge exists.", citations=[_citation("zástavní právo k budově", 43)]),
    ]
    ans = parse_answer(content)
    assert ans.citations == [Citation(cited_text="zástavní právo k budově", page=43)]


def test_parse_answer_ignores_non_text_blocks():
    content = [SimpleNamespace(type="thinking", thinking="..."), _text_block("Answer.")]
    ans = parse_answer(content)
    assert ans.text == "Answer."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_answer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/answer.py
from pydantic import BaseModel


class Citation(BaseModel):
    cited_text: str
    page: int | None = None


class Answer(BaseModel):
    text: str
    citations: list[Citation] = []


def parse_answer(content: list) -> Answer:
    parts: list[str] = []
    citations: list[Citation] = []
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        parts.append(getattr(block, "text", "") or "")
        for cit in getattr(block, "citations", None) or []:
            if getattr(cit, "type", None) == "page_location":
                citations.append(
                    Citation(
                        cited_text=getattr(cit, "cited_text", "") or "",
                        page=getattr(cit, "start_page_number", None),
                    )
                )
    return Answer(text="".join(parts), citations=citations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_answer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/answer.py tests/documents/test_answer.py
git commit -m "feat: Answer model + page-citation parsing"
```

---

### Task 5: DocumentLLM protocol + Anthropic implementation

**Files:**
- Create: `src/rejstrik/documents/llm.py`
- Test: `tests/documents/test_llm.py`

**Interfaces:**
- Consumes: `PdfSource` (Task 2), `Answer`/`parse_answer` (Task 4), `resolve_model` (Task 1), `anthropic` SDK.
- Produces: `pdf_block(source: PdfSource, citations: bool = False, cache: bool = False) -> dict` — builds a base64 `document` content block; adds `"citations": {"enabled": True}` when `citations`, and `"cache_control": {"type": "ephemeral"}` when `cache`. **Pure function, unit-tested.**
- Produces: `DocumentLLM` Protocol with `extract(self, source, schema, instructions) -> BaseModel` and `ask(self, source, question) -> Answer`.
- Produces: `AnthropicDocumentLLM` implementing the protocol via the SDK. **Not unit-tested** (network); exercised only by the manual smoke step in Task 8.

- [ ] **Step 1: Write the failing test (pure block builder only)**

```python
# tests/documents/test_llm.py
from rejstrik.documents.llm import pdf_block
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF-1.4 x", sha256="deadbeef", filename="f.pdf")


def test_pdf_block_is_base64_document():
    block = pdf_block(SRC)
    assert block["type"] == "document"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "application/pdf"
    # base64 of the bytes, no newlines
    import base64
    assert block["source"]["data"] == base64.standard_b64encode(SRC.data).decode()
    assert "citations" not in block
    assert "cache_control" not in block


def test_pdf_block_citations_and_cache_flags():
    block = pdf_block(SRC, citations=True, cache=True)
    assert block["citations"] == {"enabled": True}
    assert block["cache_control"] == {"type": "ephemeral"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rejstrik.documents.llm'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/llm.py
import base64
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from rejstrik.documents.answer import Answer, parse_answer
from rejstrik.documents.config import resolve_model
from rejstrik.documents.source import PdfSource

T = TypeVar("T", bound=BaseModel)


def pdf_block(source: PdfSource, citations: bool = False, cache: bool = False) -> dict:
    block: dict = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(source.data).decode(),
        },
    }
    if citations:
        block["citations"] = {"enabled": True}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


class DocumentLLM(Protocol):
    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T: ...
    def ask(self, source: PdfSource, question: str) -> Answer: ...


class AnthropicDocumentLLM:
    """Real implementation. Network-bound — covered by the manual smoke test, not CI."""

    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None) -> None:
        self._client = client or anthropic.Anthropic()
        self.model = model or resolve_model()

    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T:
        # structured output → NO citations on this request (mutually exclusive)
        resp = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            output_format=schema,
            messages=[{
                "role": "user",
                "content": [pdf_block(source), {"type": "text", "text": instructions}],
            }],
        )
        return resp.parsed_output

    def ask(self, source: PdfSource, question: str) -> Answer:
        # citations enabled → NO output_format on this request
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [pdf_block(source, citations=True, cache=True),
                            {"type": "text", "text": question}],
            }],
        )
        return parse_answer(resp.content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_llm.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/llm.py tests/documents/test_llm.py
git commit -m "feat: DocumentLLM protocol + Anthropic impl + pdf_block builder"
```

---

### Task 6: extract_financials orchestration

**Files:**
- Create: `src/rejstrik/documents/extract.py`
- Test: `tests/documents/test_extract.py`

**Interfaces:**
- Consumes: `PdfSource` (Task 2), `FinancialStatement` (Task 3), `DocumentLLM` (Task 5).
- Produces: `EXTRACT_INSTRUCTIONS: str` — Czech-financial-statement extraction guidance (mentions rozvaha / výkaz zisku a ztráty / příloha; requires `source_page` on every figure).
- Produces: `extract_financials(source: PdfSource, llm: DocumentLLM | None = None) -> FinancialStatement` — calls `llm.extract(source, FinancialStatement, EXTRACT_INSTRUCTIONS)`; `llm` defaults to `AnthropicDocumentLLM()`.

- [ ] **Step 1: Write the failing test (fake LLM)**

```python
# tests/documents/test_extract.py
from rejstrik.documents.extract import extract_financials, EXTRACT_INSTRUCTIONS
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


class FakeLLM:
    def __init__(self):
        self.calls = []

    def extract(self, source, schema, instructions):
        self.calls.append((source, schema, instructions))
        return schema(company_name="Fake s.r.o.", balance_sheet=[Figure(label="Total assets", value=1.0, source_page=3)])

    def ask(self, source, question):  # unused here
        raise NotImplementedError


def test_extract_financials_delegates_to_llm_with_schema_and_instructions():
    fake = FakeLLM()
    result = extract_financials(SRC, llm=fake)
    assert isinstance(result, FinancialStatement)
    assert result.company_name == "Fake s.r.o."
    src, schema, instructions = fake.calls[0]
    assert src is SRC
    assert schema is FinancialStatement
    assert instructions == EXTRACT_INSTRUCTIONS


def test_extract_instructions_mention_czech_statements_and_pages():
    low = EXTRACT_INSTRUCTIONS.lower()
    assert "rozvaha" in low
    assert "page" in low  # must require page references
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/extract.py
from rejstrik.documents.llm import AnthropicDocumentLLM, DocumentLLM
from rejstrik.documents.schema import FinancialStatement
from rejstrik.documents.source import PdfSource

EXTRACT_INSTRUCTIONS = (
    "This is a Czech company financial statement (účetní závěrka). "
    "Extract the balance sheet (rozvaha), income statement (výkaz zisku a ztráty), "
    "cash flow if present, and the narrative notes (příloha). "
    "For every figure and note, record the source_page it was found on (1-indexed). "
    "Use CZK unless the document states otherwise. "
    "If a value is not present, leave it null rather than guessing."
)


def extract_financials(source: PdfSource, llm: DocumentLLM | None = None) -> FinancialStatement:
    llm = llm or AnthropicDocumentLLM()
    return llm.extract(source, FinancialStatement, EXTRACT_INSTRUCTIONS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_extract.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/extract.py tests/documents/test_extract.py
git commit -m "feat: extract_financials orchestration"
```

---

### Task 7: ask_filing orchestration

**Files:**
- Create: `src/rejstrik/documents/ask.py`
- Test: `tests/documents/test_ask.py`

**Interfaces:**
- Consumes: `PdfSource`, `Answer`, `DocumentLLM`.
- Produces: `ask_filing(source: PdfSource, question: str, llm: DocumentLLM | None = None) -> Answer` — calls `llm.ask(source, question)`; `llm` defaults to `AnthropicDocumentLLM()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/documents/test_ask.py
from rejstrik.documents.ask import ask_filing
from rejstrik.documents.answer import Answer, Citation
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


class FakeLLM:
    def __init__(self):
        self.calls = []

    def extract(self, source, schema, instructions):
        raise NotImplementedError

    def ask(self, source, question):
        self.calls.append((source, question))
        return Answer(text="A pledge exists.", citations=[Citation(cited_text="zástavní právo", page=43)])


def test_ask_filing_delegates_and_returns_answer():
    fake = FakeLLM()
    ans = ask_filing(SRC, "Are there pledges over assets?", llm=fake)
    assert ans.text == "A pledge exists."
    assert ans.citations[0].page == 43
    src, question = fake.calls[0]
    assert src is SRC
    assert question == "Are there pledges over assets?"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/documents/test_ask.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/ask.py
from rejstrik.documents.answer import Answer
from rejstrik.documents.llm import AnthropicDocumentLLM, DocumentLLM
from rejstrik.documents.source import PdfSource


def ask_filing(source: PdfSource, question: str, llm: DocumentLLM | None = None) -> Answer:
    llm = llm or AnthropicDocumentLLM()
    return llm.ask(source, question)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/documents/test_ask.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/rejstrik/documents/ask.py tests/documents/test_ask.py
git commit -m "feat: ask_filing orchestration"
```

---

### Task 8: CLI commands `extract` and `ask`

**Files:**
- Modify: `src/rejstrik/cli/main.py`
- Create: `src/rejstrik/documents/pick.py`
- Test: `tests/documents/test_pick.py`
- Test: `tests/cli/test_documents_cli.py`

**Interfaces:**
- Consumes: `find_company`, `list_filings` (Plan 1), `load_pdf`, `extract_financials`, `ask_filing`.
- Produces: `pick_latest_financial_filing(filings: list[Filing]) -> Filing | None` — first `is_financial_statement` filing (Plan 1 already sorts financial statements first, newest year first); `None` if none.
- Produces CLI commands:
  - `extract <ico>` → resolve company → list filings → pick latest financial statement → `load_pdf` → `extract_financials` → print company/year + each balance-sheet/income figure as `label: value  (p.N)`.
  - `ask <ico> <question>` → same pick + load → `ask_filing` → print answer, then `Sources:` with `cited_text (p.N)` per citation.

- [ ] **Step 1: Write the failing test (pick is pure; CLI is mocked)**

```python
# tests/documents/test_pick.py
from rejstrik.documents.pick import pick_latest_financial_filing
from rejstrik.filings.models import Filing


def test_pick_returns_first_financial_statement():
    filings = [
        Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True),
        Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False),
    ]
    assert pick_latest_financial_filing(filings).year == 2023


def test_pick_returns_none_when_no_financial_statement():
    filings = [Filing(title="Podpisový vzor", pdf_url="https://x/b.pdf", is_financial_statement=False)]
    assert pick_latest_financial_filing(filings) is None
```

```python
# tests/cli/test_documents_cli.py
from unittest.mock import patch

from typer.testing import CliRunner

from rejstrik.cli.main import app
from rejstrik.documents.answer import Answer, Citation
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource
from rejstrik.filings.models import Filing
from rejstrik.registry.models import Company

runner = CliRunner()

FILINGS = [Filing(title="Účetní závěrka 2023", year=2023, pdf_url="https://x/a.pdf", is_financial_statement=True)]
SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


def test_extract_cli_prints_figures_with_pages():
    company = Company(ico="00006947", name="Test s.r.o.")
    fs = FinancialStatement(company_name="Test s.r.o.", period_year=2023,
                            balance_sheet=[Figure(label="Total assets", value=1000.0, source_page=12)])
    with patch("rejstrik.cli.main.find_company", return_value=company), \
         patch("rejstrik.cli.main.list_filings", return_value=FILINGS), \
         patch("rejstrik.cli.main.load_pdf", return_value=SRC), \
         patch("rejstrik.cli.main.extract_financials", return_value=fs):
        result = runner.invoke(app, ["extract", "00006947"])
    assert result.exit_code == 0
    assert "Total assets" in result.stdout
    assert "12" in result.stdout


def test_ask_cli_prints_answer_and_sources():
    company = Company(ico="00006947", name="Test s.r.o.")
    ans = Answer(text="A pledge exists.", citations=[Citation(cited_text="zástavní právo", page=43)])
    with patch("rejstrik.cli.main.find_company", return_value=company), \
         patch("rejstrik.cli.main.list_filings", return_value=FILINGS), \
         patch("rejstrik.cli.main.load_pdf", return_value=SRC), \
         patch("rejstrik.cli.main.ask_filing", return_value=ans):
        result = runner.invoke(app, ["ask", "00006947", "Are there pledges?"])
    assert result.exit_code == 0
    assert "A pledge exists." in result.stdout
    assert "43" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/documents/test_pick.py tests/cli/test_documents_cli.py -v`
Expected: FAIL — `ModuleNotFoundError` (pick) / `ImportError` (cli symbols)

- [ ] **Step 3: Write minimal implementation**

```python
# src/rejstrik/documents/pick.py
from rejstrik.filings.models import Filing


def pick_latest_financial_filing(filings: list[Filing]) -> Filing | None:
    for f in filings:
        if f.is_financial_statement:
            return f
    return None
```

Append to `src/rejstrik/cli/main.py` (add imports at top, commands at bottom):

```python
# add to imports in src/rejstrik/cli/main.py
from rejstrik.documents.source import load_pdf
from rejstrik.documents.extract import extract_financials
from rejstrik.documents.ask import ask_filing
from rejstrik.documents.pick import pick_latest_financial_filing


def _load_latest_statement(ico: str):
    """Resolve -> list -> pick -> download. Returns (company, PdfSource) or exits."""
    company = find_company(ico)
    filing = pick_latest_financial_filing(list_filings(company.ico))
    if filing is None:
        typer.echo("No financial statement found in Sbírka listin.", err=True)
        raise typer.Exit(1)
    return company, load_pdf(filing)


@app.command()
def extract(ico: str) -> None:
    """Extract structured financials from the latest financial statement."""
    company, source = _load_latest_statement(ico)
    fs = extract_financials(source)
    typer.echo(f"{company.name}  ({fs.period_year or '----'})")
    for fig in [*fs.balance_sheet, *fs.income_statement]:
        page = f"(p.{fig.source_page})" if fig.source_page else ""
        value = fig.value if fig.value is not None else "-"
        typer.echo(f"  {fig.label}: {value}  {page}".rstrip())


@app.command()
def ask(ico: str, question: str) -> None:
    """Ask a free-form question about the latest financial statement, with citations."""
    _company, source = _load_latest_statement(ico)
    answer = ask_filing(source, question)
    typer.echo(answer.text)
    if answer.citations:
        typer.echo("\nSources:")
        for c in answer.citations:
            page = f"(p.{c.page})" if c.page else ""
            typer.echo(f"  - {c.cited_text} {page}".rstrip())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/documents/test_pick.py tests/cli/test_documents_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS (Plan 1 + Plan 2).

- [ ] **Step 6: Manual smoke test (real API — NOT in CI; needs `ANTHROPIC_API_KEY`)**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
rejstrik extract 00514152          # Budvar — expect figures with page numbers
rejstrik ask 00514152 "Are there any pledges or guarantees over company assets?"
```

Confirm real extraction returns figures with page citations and `ask` returns a cited answer. (This call costs tokens — a 50-page PDF on Opus 4.8 runs roughly $0.25–0.75 per call; the document is prompt-cached within an `ask` session.)

- [ ] **Step 7: Commit**

```bash
git add src/rejstrik/documents/pick.py src/rejstrik/cli/main.py tests/documents/test_pick.py tests/cli/test_documents_cli.py
git commit -m "feat: CLI extract + ask commands (end-to-end document engine)"
```

---

### Task 9: README + lint

**Files:**
- Modify: `README.md`
- Modify: any files flagged by `ruff`.

- [ ] **Step 1: Update README**

Add a "Document engine" section: the two flagship commands (`extract`, `ask`) with example output, the `ANTHROPIC_API_KEY` requirement, the model note (defaults to `claude-opus-4-8`; override with `REJSTRIK_MODEL`), and a one-line note that Claude reads the PDF natively (scanned pages included) and cites pages.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ && ruff format --check src/ tests/`
Expected: clean (run `ruff format src/ tests/` to fix, then re-run).

- [ ] **Step 3: Run full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md src/ tests/
git commit -m "docs: README document-engine section + lint clean"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- `extract_financials` (deterministic, page-cited) → Tasks 3, 5, 6 (schema with `source_page` + structured output). ✓
- `ask_filing` (open-ended, full-report, cited, conversational) → Tasks 4, 5, 7 (citations API). ✓
- "two paths over one ingested document" → both paths take the same `PdfSource` (Task 2). ✓
- "scanned + 50+ page PDFs" → handled by Claude's native PDF/vision (no OCR pipeline needed); base64 document block (Task 5). ✓
- "cite every figure to a page" → `source_page` in the schema (extract) + `page_location` citations (ask). ✓
- "footnote/notes intelligence" → `FinancialStatement.notes` + free-form `ask_filing`. ✓
- "tells the agent where to grab it" → `pick_latest_financial_filing` + `load_pdf` from Plan 1's `list_filings`. ✓
- Computed ratios / trends / red-flags → **deferred to Plan 3** (analysis layer + orchestrator). The design spec places the analysis layer over Path-1 output; this plan delivers the extraction it consumes. Noted, not a gap. ✓
- MCP server, breadth tools → **Plan 3**, as designed. ✓

**Placeholder scan:** No TBD/TODO. The only network-bound, non-unit-tested code (`AnthropicDocumentLLM`) is fully written (not a stub) and covered by the explicit manual smoke step (Task 8, Step 6).

**Type consistency:** `PdfSource(data, sha256, filename)` identical across Tasks 2/5/6/7/8. `FinancialStatement` / `Figure` / `NoteItem` identical across Tasks 3/6/8. `Answer` / `Citation` identical across Tasks 4/5/7/8. `DocumentLLM.extract(source, schema, instructions)` and `.ask(source, question)` signatures match between the protocol (Task 5), the fakes (Tasks 6/7), and the real impl (Task 5). CLI patches (`find_company`, `list_filings`, `load_pdf`, `extract_financials`, `ask_filing`) all reference symbols imported into `cli/main.py` (Task 8). ✓

**API-correctness notes for the implementer:**
- `messages.parse(output_format=PydanticModel)` returns `.parsed_output` — used in `AnthropicDocumentLLM.extract`. Do NOT add `citations` to that request (structured output + citations = 400).
- `messages.create(..., citations enabled)` returns `response.content` with cited `text` blocks carrying a `citations` list (`page_location` → `start_page_number`) — parsed in Task 4. Do NOT add `output_format` to that request.
- On `claude-opus-4-8`: never send `temperature`/`top_p`/`top_k`/`budget_tokens` (all 400).
- If a future doc exceeds the 32 MB base64 request limit, switch that path to the Files API (beta `files-api-2025-04-14`) — out of scope for v1; note it in code if you hit it.
