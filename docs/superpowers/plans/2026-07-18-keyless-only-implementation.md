# Keyless-Only Refactor (v0.8.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every API-key code path from the project. All document understanding is done by the client LLM; the server does data access, deterministic analysis, and card rendering. Ships as **v0.8.0** — the first published release (the v0.7.1 tag is never pushed).

**Architecture:** Subtraction-only plus one relocation. Delete the 4 keyed MCP tools, 2 keyed CLI subcommands, the `documents/` LLM machinery, and the `anthropic`/`openai`/`python-dotenv` dependencies. The one *addition*: the tuned extraction guidance from `EXTRACT_INSTRUCTIONS` is merged into the `analyze-company` prompt **before** anything is deleted, so client-side extraction keeps the same quality bar (verbatim figures, unit-scale rules, null-not-guess).

**Tech Stack:** Python 3.11+, pytest (offline, key-free), ruff. Dependencies shrink.

**Design spec:** `docs/superpowers/specs/2026-07-18-keyless-only-design.md`

## Global Constraints

- Gate before every commit: `.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q` — all green.
- TDD for deletions too: first update the test that pins the surface (tool count, CLI help, exports), watch it fail, then delete the code, watch it pass.
- **Task 1 (relocation) MUST land before any deletion task.** If Task 1 is not committed, do not start Task 2+.
- Never auto-improvise prompt wording — the exact phrases to preserve are quoted in Task 1. Do not paraphrase away "verbatim as printed", "never rescale or convert", the unit mapping, or "null rather than guessing".
- The keyless tool surface after this plan: exactly **13 tools** — `find_company`, `list_filings`, `get_filing`, `read_filing_text`, `read_filing_page_images`, `analyze_financials`, `estimate_valuation`, `render_card`, `check_insolvency`, `get_statutory_bodies`, `check_vat`, `get_subsidies`, `get_contracts`.
- Commit messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Do NOT push, tag, or publish anything — Task 10 is human-gated.

---

### Task 1: Relocate the extraction guidance into the analyze-company prompt (BEFORE any deletion)

`EXTRACT_INSTRUCTIONS` (`src/rejstrik/documents/extract.py:5-15`) carries domain knowledge the client model must inherit. Diff against the current prompt (`src/rejstrik/mcp/server.py:485`, step 4) shows the prompt already has: verbatim figures, `unit` from "v celých tisících Kč" → `thousands_czk`, `currency`, `period_year`, `source_page`, and the `canonical` mapping. **Missing from the prompt — these four pieces move over:**

1. The statement-part enumeration: *"balance sheet (rozvaha), income statement (výkaz zisku a ztráty), cash flow if present, and the narrative notes (příloha)"*
2. The full unit mapping, not just the thousands example: *"thousands_czk for 'v tisících Kč', czk for plain Kč, millions_czk for 'v milionech Kč'"*
3. The explicit negative: *"never rescale or convert"*
4. The null rule: *"If a value is not present, leave it null rather than guessing."*

**Files:**
- Modify: `src/rejstrik/mcp/server.py` (the `analyze-company` prompt, step 4)
- Modify: `tests/mcp/test_server.py` (or wherever prompt content is asserted — find with `grep -rn "analyze-company\|analyze_company_prompt" tests/`)

- [ ] **Step 1: Write the failing test**

Add a test asserting the rendered prompt contains all four relocated phrases (substring checks are fine):

```python
def test_analyze_company_prompt_carries_extraction_guidance():
    text = analyze_company_prompt("Test s.r.o.", years=2)
    for phrase in [
        "rozvaha",
        "výkaz zisku a ztráty",
        "příloha",
        "never rescale or convert",
        "millions_czk for 'v milionech Kč'",
        "czk for plain Kč",
        "null rather than guessing",
    ]:
        assert phrase in text, f"extraction guidance lost: {phrase!r}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/mcp/test_server.py -q -k extraction_guidance`
Expected: FAIL (phrases not yet in prompt).

- [ ] **Step 3: Merge the guidance into prompt step 4**

Rewrite step 4 of the prompt to open with the part enumeration and close with the negative + null rules. Suggested wording (keep the existing schema/canonical text intact, weave these in):

```
4. From each PDF, extract a FinancialStatement JSON object matching this
   schema. Cover the balance sheet (rozvaha), income statement (výkaz zisku
   a ztráty), cash flow if present, and the narrative notes (příloha).
   Record every figure verbatim as printed — never rescale or convert.
   Statements declare their scale near the top of the rozvaha (usually
   'v celých tisících Kč'); set the `unit` field to match: thousands_czk for
   'v tisících Kč', czk for plain Kč, millions_czk for 'v milionech Kč'.
   Set currency to "CZK"; set period_year to the statement year; cite
   source_page for every figure (1-indexed). If a value is not present,
   leave it null rather than guessing. ALSO fill the `canonical` object: …
   (existing canonical text and schema unchanged)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/mcp/test_server.py -q`
Expected: PASS, including the new test.

- [ ] **Step 5: Gate + commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_server.py
git commit -m "feat(prompt): fold server-side extraction guidance into analyze-company prompt

Relocates EXTRACT_INSTRUCTIONS domain knowledge (statement parts, full unit
mapping, never-rescale, null-not-guess) to the client-facing prompt ahead of
removing the keyed extraction path.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Remove the four keyed MCP tools

**Files:**
- Modify: `src/rejstrik/mcp/server.py` — delete `extract_financials` (~166), `ask_filing` (~180), `analyze_company_financials` (~194), `analyze_company_card` (~217), `_require_llm_key` (~148), the `has_llm_key` import (line 24), and any now-unused imports (`Answer`, keyed service imports — let ruff find them).
- Modify: `tests/mcp/test_server.py` — tool-list assertion → the 13 keyless tools.
- Delete: `tests/mcp/test_keyed_degradation.py`, `tests/mcp/test_multiyear_tools.py`.
- Rework: `tests/mcp/test_card_tool.py` — keep only `render_card` coverage; if it lacks a direct `render_card` test, port the card-shape assertions (UIResource type, `mcp/ui` meta, HTML contains report fields) to call `render_card(report)` with a locally-built `CompanyFinancialReport`.

- [ ] **Step 1: Update the tool-list test first**

Find it: `grep -n "extract_financials\|analyze_company" tests/mcp/test_server.py`. Set the expected tool set to exactly the 13 keyless tools. Run `pytest tests/mcp/ -q` — expect FAIL (tools still registered).

- [ ] **Step 2: Delete the keyed tools + helper**

Remove the four tool functions, `_require_llm_key`, and the `has_llm_key` import. Run `ruff check` to sweep newly-unused imports.

- [ ] **Step 3: Delete/rework the keyed tests**

`git rm tests/mcp/test_keyed_degradation.py tests/mcp/test_multiyear_tools.py`; rework `test_card_tool.py` per above.

- [ ] **Step 4: Gate + commit**

Expected: pytest green (count will drop from 301 — record the new number).

```bash
git add -A src/rejstrik/mcp/ tests/mcp/
git commit -m "feat(mcp)!: remove keyed tools; card renders only via keyless render_card

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: CLI goes data-only

**Files:**
- Modify: `src/rejstrik/cli/main.py` — delete the `extract` and `analyze` subcommands and their imports (`extract_financials`, `analyze_company_financials`).
- Delete: `tests/cli/test_analyze_cli.py`.
- Rework: `tests/cli/test_documents_cli.py` — drop keyed-path tests; keep any covering keyless commands. If nothing keyless remains in it, delete the file and confirm `find`/`filings` coverage exists elsewhere (`grep -rn "find\|filings" tests/cli/`).

- [ ] **Step 1: Update CLI surface test first** — assert `extract`/`analyze` absent from the Typer app (e.g. registered command names), watch it fail.
- [ ] **Step 2: Delete the subcommands**; ruff sweeps imports.
- [ ] **Step 3: Delete/rework the CLI tests.**
- [ ] **Step 4: Gate + commit**

```bash
git add -A src/rejstrik/cli/ tests/cli/
git commit -m "feat(cli)!: data-only CLI — drop keyed extract/analyze subcommands

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Purge the keyed paths from service.py

**Files:**
- Modify: `src/rejstrik/service.py` — delete `analyze_company_financials` (line ~123) and the `DocumentLLM` / `extract_financials` imports; strip LLM branches from `resolve_statement_source` (line ~98) so it only resolves already-provided statements/PDF sources. Keep `fetch_filing`, `analyze_statements`, `count_pdf_pages`.
- Rework: `tests/test_service.py`, `tests/test_service_insolvency.py`, `tests/test_service_unreliable.py` — remove tests of the deleted function and any `DocumentLLM` mocks; keep every test of `analyze_statements`/`fetch_filing` (these are the keyless core — do NOT delete coverage of them).

- [ ] **Step 1: Inventory before cutting**

Run: `grep -n "analyze_company_financials\|DocumentLLM\|extract_financials\|resolve_statement_source" src/rejstrik/service.py tests/test_service*.py scripts/smoke.py`
Confirm `scripts/smoke.py` no longer references any of these (it was made keyless earlier). Map which tests die vs. stay.

- [ ] **Step 2: Update tests first** (remove/adjust), watch relevant failures, **Step 3: cut the service code**, **Step 4: gate + commit**

```bash
git add -A src/rejstrik/service.py tests/
git commit -m "feat(service)!: remove server-side LLM extraction path

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Delete the documents/ LLM machinery

**Files:**
- Delete: `src/rejstrik/documents/llm.py`, `extract.py`, `ask.py`, `answer.py`, `config.py`
- Keep: `cache.py`, `schema.py`, `source.py`, `pick.py`, `pdftext.py`, `pdfimages.py`
- Modify: `src/rejstrik/documents/pdftext.py` — `_NO_TEXT_NOTE` says "call the keyed extract_financials tool"; rewrite to point only at reading the PDF directly or `read_filing_page_images`.
- Check: `src/rejstrik/documents/__init__.py` for re-exports of deleted modules.
- Delete: `tests/documents/test_llm.py`, `test_extract.py`, `test_ask.py`, `test_answer.py`, `test_config.py`. Also fix `tests/documents/test_pdftext.py` if it asserts the old `_NO_TEXT_NOTE` wording.

- [ ] **Step 1: Confirm no survivors import the doomed modules**

Run: `grep -rn "documents.llm\|documents.extract\|documents.ask\|documents.answer\|documents.config" src/ tests/ scripts/`
Expected after Tasks 2–4: hits only inside the files being deleted here and their tests. Any other hit is a missed reference — fix it first.

- [ ] **Step 2: Delete files + tests, fix `_NO_TEXT_NOTE` + `__init__.py`**
- [ ] **Step 3: Gate + commit**

```bash
git add -A src/rejstrik/documents/ tests/documents/
git commit -m "feat(documents)!: delete server-side LLM machinery (llm/extract/ask/answer/config)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Drop the dependencies

**Files:**
- Modify: `pyproject.toml` — remove `anthropic>=0.92`, `openai>=2.30`, `python-dotenv>=1.0`.

- [ ] **Step 1: Prove each is orphaned**

Run: `grep -rn "anthropic\|openai\|dotenv" src/ tests/ scripts/ --include="*.py"`
Expected: no hits. Any hit blocks this task.

- [ ] **Step 2: Remove from pyproject, reinstall, gate**

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest -q`
Then prove the tree is clean: `.venv/bin/pip uninstall -y anthropic openai python-dotenv 2>/dev/null; .venv/bin/python -m pytest -q`
Expected: green both times.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build!: drop anthropic, openai, python-dotenv dependencies

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Docs sweep — every key mention dies

**Files:** `README.md`, `CLAUDE.md`, `docs/RELEASE-CHECKLIST.md`, `docs/media/README.md`, `mcpb/manifest.json` (verify only), `src/rejstrik/mcp/server.py` (health-check prompt verify only)

- [ ] **Step 1: README** — delete the "Keyed power mode (optional)" section (~line 86) and the OpenAI smoke line (~118); the comparison-table "works without any API key" row and keyless pitch stay, now unconditionally true.
- [ ] **Step 2: CLAUDE.md** — intro: drop "an optional server-side API key enables in-server extraction"; Rules: drop "Mock the LLM via the `DocumentLLM` protocol" (keep the `*_check` injection-points rule).
- [ ] **Step 3: RELEASE-CHECKLIST.md** — rewrite for v0.8.0: remove the keyed caveats block (§3) and the keyed `budvar-3year.gif` item (§5); card verification = `get_filing → agent extraction → analyze_financials → render_card`; version references 0.7.1 → 0.8.0.
- [ ] **Step 4: docs/media/README.md** — drop the keyed gif item; keyless CLI transcript + Desktop card screenshot remain the demo story.
- [ ] **Step 5: Verify** `mcpb/manifest.json` and both MCP prompts contain no key/keyed-tool references: `grep -rn -i "api key\|keyed\|OPENAI\|ANTHROPIC" README.md CLAUDE.md docs/ mcpb/ src/rejstrik/mcp/server.py` — remaining hits must only be historical (CHANGELOG, superseded specs/plans under docs/superpowers/, which stay untouched as history).
- [ ] **Step 6: Gate + commit**

```bash
git add README.md CLAUDE.md docs/ mcpb/
git commit -m "docs: purge all API-key mentions; keyless is unconditional

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Version 0.8.0 + CHANGELOG

- [ ] **Step 1: Bump all five locations** — `pyproject.toml`, `server.json` (top-level AND `packages[0].version`), `mcpb/manifest.json`, `src/rejstrik/__init__.py`, `tests/test_smoke.py` (pin assert). Verify: `grep -rn "0\.7\.1" pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py tests/test_smoke.py` → no output.
- [ ] **Step 2: CHANGELOG.md** — add 0.8.0: keyless-only; removed keyed MCP tools + CLI subcommands + LLM deps; extraction guidance relocated to the analyze-company prompt; card via `render_card`. Note 0.7.1 was never published.
- [ ] **Step 3: Gate + commit**

```bash
git add pyproject.toml server.json mcpb/manifest.json src/rejstrik/__init__.py tests/test_smoke.py CHANGELOG.md
git commit -m "chore(release): bump version to 0.8.0

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Acceptance verification (spec criteria 1–6)

- [ ] **Step 1: The hard grep**

Run: `grep -rn "OPENAI\|ANTHROPIC_API\|has_llm_key\|_require_llm_key\|DocumentLLM\|dotenv" src/ tests/ scripts/`
Expected: zero hits.

- [ ] **Step 2: Fresh wheel, clean tree**

Run: `.venv/bin/python -m build` then in a scratch venv: `pip install dist/rejstrik_mcp-0.8.0-*.whl && pip show anthropic openai python-dotenv`
Expected: wheel installs; all three "not found".

- [ ] **Step 3: MCP surface** — drive the installed server over stdio (initialize + tools/list): expect `serverInfo … v0.8.0`, exactly 13 tools, `mcp/ui` meta present on `render_card` and the UI resource only.

- [ ] **Step 4: Live keyless smoke** — `.venv/bin/python scripts/smoke.py` → `SMOKE OK` (network; no key in env — run under `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY`).

- [ ] **Step 5: Keyless card end-to-end over stdio** — script it: `find_company` → `list_filings` → build a valid `FinancialStatement` dict (as the agent would) → `analyze_financials` → `render_card(report)`; assert the result contains a UIResource with HTML. This is spec criterion 6 — the release-blocking proof.

- [ ] **Step 6: Report results** — all five green → ready for the human gate. Any red → fix before Task 10.

---

### Task 10: [HUMAN GATE] Release v0.8.0

Reuses the superseded plan's Tasks 8–10 at the new version. Agent does nothing here without an explicit "go".

- [ ] Jan: manual install + card check in Claude Desktop/Code per the rewritten `docs/RELEASE-CHECKLIST.md` (keyless recipe — no key needed anywhere, including the card).
- [ ] Jan (or agent on "go"): `git push origin main && git tag v0.8.0 && git push origin v0.8.0` → watch `release.yml` to green → verify PyPI shows 0.8.0. Never push the stale local v0.7.1 state as a tag.
- [ ] Jan: publish MCP registry entry (`io.github.janf19/rejstrik-mcp`) from the 0.8.0 `server.json`.
- [ ] Agent: draft `docs/listings.md`; Jan submits directory listings.

## Definition of done

- [ ] Task 1: extraction guidance verifiably relocated (test pins all key phrases)
- [ ] Tasks 2–5: keyed tools/CLI/service/documents machinery deleted; gate green after each
- [ ] Task 6: anthropic/openai/python-dotenv gone from the dependency tree; tests green without them installed
- [ ] Task 7: zero key mentions outside historical docs
- [ ] Task 8: 0.8.0 everywhere; CHANGELOG entry
- [ ] Task 9: hard grep clean; 13 tools; live `SMOKE OK`; keyless card proven over stdio
- [ ] Task 10: tagged, PyPI live, registry published, listings drafted

When all boxes are checked, the project is keyless, released, and done.
