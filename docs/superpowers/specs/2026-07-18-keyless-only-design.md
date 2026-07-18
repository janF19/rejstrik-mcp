# Keyless-Only Refactor Design (v0.8.0)

**Date:** 2026-07-18
**Status:** Approved direction (product owner decision, 2026-07-18)
**Supersedes:** the v0.7.1 release plan (`2026-07-17-final-release-v0.7.1.md`) —
the `v0.7.1` tag is **never pushed**; v0.8.0 is the first published release.

## Decision

The product is keyless, period. No code path in this project may require —
or even optionally accept — a server-side LLM API key. All document
understanding (reading the filed PDFs, extracting figures) is done by the
**client** LLM (Claude or any MCP host model). The server's job is data
access + deterministic computation + UI rendering:

- fetch registry data and filed PDFs (ARES, ISIR, ADIS, Sbírka listin)
- deliver PDFs/text/page-images to the host agent in consumable form
- run pure, deterministic analysis over figures the agent extracted
  (`analyze_financials`, `estimate_valuation` — ratios, IN05, trends,
  red flags, valuation)
- render the report card (`render_card`) — already keyless today

**Why this is feasible:** the keyless card path already exists.
`render_card(report)` takes the `CompanyFinancialReport` produced by
`analyze_financials` and returns the same UIResource card that the keyed
`analyze_company_card` produced. The keyed tools were convenience wrappers
duplicating what the calling agent can do itself.

### Considered and rejected: MCP sampling

MCP "sampling" would let the server call the *client's* LLM for
extraction, keeping one-call convenience without a key. Rejected: host
support is still inconsistent across Claude Desktop / other MCP hosts,
it adds a protocol dependency to the core loop, and the agent-does-
extraction pattern is already the documented differentiator. Revisit
only if a future MCP spec makes sampling universal.

## What is removed (the entire keyed surface)

**MCP tools** (`src/rejstrik/mcp/server.py`):
- `extract_financials` (line ~166), `ask_filing` (~180),
  `analyze_company_financials` (~194), `analyze_company_card` (~217)
- `_require_llm_key()` (~148) and the `has_llm_key` import (line 24)

**CLI** (`src/rejstrik/cli/main.py`):
- `extract` and `analyze` subcommands. CLI becomes data-only:
  `find`, `filings`, and any registry lookups that exist.

**`src/rejstrik/documents/`** — delete outright:
- `llm.py` (DocumentLLM protocol + Anthropic/OpenAI impls)
- `extract.py` (server-side extraction; **preserve the instruction text**,
  see "Relocate" below)
- `ask.py`, `answer.py` (Q&A path; agent asks the PDF itself)
- `config.py` (provider/model/key resolution + dotenv loading)

**`src/rejstrik/documents/`** — keep (keyless infrastructure):
- `cache.py`, `schema.py`, `source.py`, `pick.py`, `pdftext.py`,
  `pdfimages.py`

**`src/rejstrik/service.py`**:
- delete `analyze_company_financials` and any `DocumentLLM` /
  `extract_financials` imports and LLM branches in
  `resolve_statement_source`; keep `fetch_filing`, `analyze_statements`,
  `count_pdf_pages` and everything else deterministic.

**Dependencies** (`pyproject.toml`):
- remove `anthropic`, `openai`, `python-dotenv` (its only consumer is
  `config.py`). Verify with a grep before deleting each.

**Tests** — delete: `tests/documents/test_llm.py`, `test_extract.py`,
`test_ask.py`, `test_answer.py`, `test_config.py`,
`tests/cli/test_analyze_cli.py`, `tests/mcp/test_keyed_degradation.py`,
`tests/mcp/test_multiyear_tools.py` (covers keyed multiyear tool).
Rework: `tests/mcp/test_card_tool.py` (now targets `render_card` only),
`tests/cli/test_documents_cli.py`, `tests/test_service*.py`,
`tests/mcp/test_server.py` (tool-list assertions shrink to 13 tools).

## Relocate, don't lose: the extraction instructions

`extract.py`'s `EXTRACT_INSTRUCTIONS` encodes hard-won domain knowledge
(rozvaha/výkaz structure, verbatim figures, the `unit` scale declaration
"v celých tisících Kč", source-page tracking). This moves into the
**`analyze-company` MCP prompt** (`server.py:485`) and the `get_filing` /
`read_filing_text` tool docstrings, so the *client* model extracting the
figures gets the same guidance the server-side extractor had. The
`FinancialStatement` schema (with `unit`) stays — it is the contract the
agent fills in and passes to `analyze_financials`.

## Text/docs cleanup (every key mention dies)

- `pdftext.py` `_NO_TEXT_NOTE`: currently says "call the keyed
  extract_financials tool" — rewrite to point at
  `read_filing_page_images` only.
- `README.md`: delete the "Keyed power mode (optional)" section (~line
  86) and the OpenAI smoke mention (~line 118); the keyless pitch lines
  stay and become unconditionally true.
- `CLAUDE.md`: rewrite the intro ("optional server-side API key" clause)
  and the Rules bullet about mocking `DocumentLLM` — there is no LLM to
  mock anymore; tests are offline by construction.
- `docs/RELEASE-CHECKLIST.md`: rewrite for v0.8.0 — the keyed caveats
  section disappears; card verification uses the keyless
  `get_filing → analyze_financials → render_card` recipe.
- `docs/media/README.md`: drop the keyed `budvar-3year.gif` item;
  the demo story is the keyless flow (CLI transcript already captured +
  a Claude Desktop card screenshot, still human-captured).
- MCP prompts (`analyze-company`, `company-health-check`): rewrite the
  recipe to the keyless flow ending in `render_card`.
- `mcpb/manifest.json`: description already says "No API key needed" —
  verify no key-related env/config remains anywhere in the manifest.

## Version & release

- Bump to **0.8.0** in all four locations: `pyproject.toml`,
  `server.json` (top-level + `packages[0].version`), `mcpb/manifest.json`,
  `src/rejstrik/__init__.py`, and the pin in `tests/test_smoke.py`.
- `CHANGELOG.md`: 0.8.0 entry — "keyless-only: removed server-side LLM
  extraction and all API-key code paths; client agent does document
  understanding; card renders via render_card".
- The unpushed local `v0.7.1` tag work is abandoned; release flow (tag
  `v0.8.0` → `release.yml` → PyPI + GitHub release → MCP registry →
  listings) inherits from the superseded plan's Tasks 8–10 unchanged
  except for the version.

## Acceptance criteria

1. `grep -rn "OPENAI\|ANTHROPIC_API\|has_llm_key\|_require_llm_key\|DocumentLLM\|dotenv" src/ tests/ scripts/` → no hits.
2. `pip show anthropic openai python-dotenv` in a fresh install of the
   wheel → none present (not in the dependency tree).
3. MCP `tools/list` → exactly 13 tools, none of which can raise a
   missing-key error; `render_card` and the UI resource keep `_UI_META`.
4. Full gate green: `ruff check` + `ruff format --check` + `pytest -q`
   (offline, no keys, no mocks of any LLM).
5. Live keyless smoke (`scripts/smoke.py`) prints `SMOKE OK`.
6. Keyless card path proven over real MCP stdio: `find_company` →
   `list_filings` → `get_filing` → (agent-shaped `FinancialStatement`) →
   `analyze_financials` → `render_card` returns the UIResource.
7. README/CLAUDE.md/prompts contain zero references to API keys, keyed
   tools, or "power mode".

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Client model must read ~50-page / 25 MB PDFs | Already solved surface: `read_filing_text` (chunked text) and `read_filing_page_images` (PNGs for scans) — Stage C shipped this |
| Scanned filings with no text layer | `read_filing_page_images` path; `_NO_TEXT_NOTE` rewritten to point there |
| Extraction quality regression vs. tuned server-side prompt | `EXTRACT_INSTRUCTIONS` relocated into the `analyze-company` prompt + tool docs, so the client model gets identical guidance (incl. `unit` scale rules) |
| CLI loses `analyze`/`extract` | Accepted (product decision): CLI is data-only; analysis lives in MCP hosts |
| Weak-host degradation (host model can't read PDFs) | Accepted: such hosts get raw data tools; no server-side fallback exists anymore |

## Out of scope

- MCP sampling support (revisit when host support matures)
- Any new analysis features; this is a subtraction-only release plus doc
  relocation
- The human-gated release steps themselves (tag, PyPI, registry,
  listings) — they re-run from the superseded plan at 0.8.0
