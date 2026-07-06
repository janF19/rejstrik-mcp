# rejstrik-mcp: Keyless Pivot, Zero-Friction Install, Multi-Year Analysis, Data Breadth

**Date:** 2026-07-06
**Status:** Approved design, pending implementation plans
**Builds on:** `docs/superpowers/specs/2026-06-25-rejstrik-mcp-design.md` (original design, Plans 1–6 shipped)

## Product positioning

Masthead sentence: **"Add the Czech business registry to your Claude in 30
seconds — no API key. It reads the actual filed PDFs with your own
subscription."**

The unique combination in the space:

| | agent-native (MCP) | reads filed PDFs | free / open source | no server API key |
|---|---|---|---|---|
| cz-agents-mcp / mcp-registry-cz | yes | no | yes | yes |
| chytryrejstrik.cz | no | partially (paid) | no | n/a |
| **rejstrik-mcp (this spec)** | **yes** | **yes** | **yes** | **yes** |

The winning claim is being the *agent-native, document-reading, free* option.
Everything below serves that claim.

## Architecture decision: keyless primary, keyed optional

Today every document tool (`extract_financials`, `ask_filing`,
`analyze_company_financials`, `analyze_company_card`) calls Anthropic/OpenAI
**inside the server**, so the server operator needs an API key and pays for
inference. That contradicts "pluggable for anyone".

New model — two modes over one core:

1. **Keyless mode (default, always available).** The server never calls an
   LLM. Document tools hand the PDF to the *calling agent* (Claude Code,
   Claude Desktop, Codex, any MCP host), which reads it with the user's own
   subscription, extracts numbers into the existing Pydantic schema, and
   passes structured data back to deterministic server tools for
   ratios/red-flags/trends/cards. MCP prompts choreograph this loop.
2. **Keyed power mode (opt-in).** When `ANTHROPIC_API_KEY` or
   `OPENAI_API_KEY` is set in the server's environment, today's one-call
   server-side extraction and cited Q&A tools work exactly as they do now.
   Without a key they return a friendly typed message pointing to the keyless
   flow — never a stack trace.

Known trade, accepted: in keyless mode extraction quality depends on the host
model rather than a controlled server-side prompt, and very large scanned
PDFs may exceed what some hosts pass through comfortably. The keyed mode
remains the answer for users who want maximum extraction control.

## Stage 1 — Keyless document flow + zero-friction install

### New tool: `get_filing`

```
get_filing(ico: str, year: int | None = None, filing_id: str | None = None)
```

- Resolves the company (IČO or name via existing `_to_ico` pattern), picks
  the financial statement: latest by default, a specific year via `year`, or
  an exact document via `filing_id` (IDs come from `list_filings`).
- Downloads the PDF from the Sbírka listin portal to a local cache directory
  (platform cache dir, e.g. `platformdirs` user-cache; re-download skipped
  when cached).
- Returns: filing metadata (year, type, filing id, page count/size if
  cheaply available), the **absolute file path** (for filesystem-capable
  hosts like Claude Code/Codex), and the PDF as an **embedded MCP blob
  resource** (for hosts without filesystem access). Both delivery channels
  in one result.

### New tool: `analyze_financials` (deterministic, no LLM)

```
analyze_financials(statements: list[FinancialStatement], ico: str | None = None)
```

- Input: one or more statements the *host model* extracted from PDFs using
  the existing `FinancialStatement` Pydantic schema (the tool description
  embeds the schema so hosts know the shape; the `analyze-company` prompt
  reinforces it).
- Runs the existing pure pipeline: normalize → ratios → red flags; with 2+
  statements also `compute_trends()` (currently dead code — this wires it).
- If `ico` is given, enriches red flags with the existing server-side
  registry cross-checks (ISIR insolvency, ADIS unreliable VAT payer) — these
  are keyless HTTP calls already.
- Returns the existing `CompanyFinancialReport` (with `trends` populated).

### New tool: `render_card`

```
render_card(report: CompanyFinancialReport) -> list[UIResource]
```

- The existing self-contained HTML card renderer, fed by passed-in data
  instead of a server-side LLM call, so the MCP UI card works keyless.
- Existing `analyze_company_card(query)` stays as the keyed one-call variant.

### MCP prompts (choreography)

Register MCP *prompts* on the server (FastMCP `@mcp.prompt()`):

- `analyze-company` — args: company, years (default 1). Recipe text guiding
  the host: `find_company` → `list_filings` → `get_filing` per year → read
  each PDF and fill `FinancialStatement` per the schema → call
  `analyze_financials` → optionally `render_card`. Includes explicit
  instructions on units (thousands CZK), fiscal-year selection, and citing
  page numbers in the narrative.
- `company-health-check` — args: company. Broader recipe combining
  registry breadth tools (insolvency, VAT, statutory bodies; later
  contracts/subsidies/owners) with the latest statement analysis.

Prompts are first-class MCP features surfaced as slash commands in Claude
clients — they make the keyless loop reliable instead of improvised, and
signal spec-current implementation.

### Keyed tools degrade gracefully

`extract_financials`, `ask_filing`, `analyze_company_financials`,
`analyze_company_card` check for a configured provider up front. Without a
key they return a typed error result: what's missing, and the exact keyless
alternative to use (e.g. "call get_filing then analyze_financials, or set
ANTHROPIC_API_KEY"). Tool descriptions state which mode each tool belongs to.

### Transport: stdio default

- `rejstrik-mcp` → **stdio** (what `claude mcp add`, Claude Desktop configs,
  and Codex stdio servers expect for local-first use).
- `rejstrik-mcp --http [--port 8000]` → today's stateless streamable-http.
- README documents both; all examples lead with stdio.

### Packaging & distribution

- Publish to **PyPI** so `uvx rejstrik-mcp` works with zero clone/install.
- Document the one-liner: `claude mcp add rejstrik -- uvx rejstrik-mcp`.
- Build a **.mcpb Desktop Extension** bundle (manifest + server) for
  one-click install in Claude Desktop; built in CI and attached to GitHub
  releases.
- Submit to the official MCP registry and community directories
  (mcpservers directories, awesome-mcp lists).

## Stage 2 — Multi-year analysis end to end

- `year`/`filing_id` parameters added to the keyed document tools
  (`extract_financials`, `ask_filing`) — replacing the hardwired
  `pick_latest_financial_filing()`; picker gains
  `pick_financial_filing(filings, year=None, filing_id=None)`.
- `analyze_company_financials(query, years: int = 1)` in keyed mode: extract
  up to N most recent annual statements, run per-year analysis, populate
  `CompanyFinancialReport.trends` via `compute_trends()` (removing the
  hardcoded `trends=[]` in `service.py`).
- Keyless path gets multi-year for free via Stage 1 (`analyze_financials`
  accepts a list; `analyze-company` prompt takes `years`).
- Acceptance demo: "What happened to Budějovický Budvar over the last 3
  years?" pulls 3 PDFs and returns computed trends in both modes.
- Guardrail: cap `years` at 5 per call to bound cost/latency; document it.

## Stage 3 — Data breadth (contracts, subsidies, beneficial owners)

Three new keyless registry clients, same pattern as ISIR/ADIS (plain HTTP,
Pydantic models, offline-fixture tests, exposed as MCP tools + CLI):

- `get_contracts(ico)` — **Registr smluv** (smlouvy.gov.cz open data):
  contracts with public bodies — counterparty, subject, value, date. Sorted
  newest-first, capped list with total count/value summary.
- `get_subsidies(ico)` — **CEDR/RED** subsidy records: provider, programme,
  amount, year, with a total summary.
- `get_beneficial_owners(ico)` — **Evidence skutečných majitelů** public
  extract: names, roles, nature of control.

Integration:

- New red flags fed into `analyze_financials` when the data is available,
  e.g. "public-contract revenue concentration" (contracts total vs revenue),
  "subsidy dependence".
- `company-health-check` prompt and the UI card gain
  contracts/subsidies/owners sections.

**Feasibility gate:** exact endpoint shapes for these three sources must be
verified live at the start of Stage 3 planning. Registr smluv and CEDR have
documented open-data interfaces; ESM's public interface may require
HTML-level access. If a source has no stable public interface, the fallback
is to ship the other tools and drop or degrade that one (documented in the
README), not to block the stage.

## Cross-cutting

### Error handling

Every tool returns typed, explanatory errors rather than exceptions leaking
to the host: company not found, no financial filings on record, requested
year not available (with the years that are), PDF download failure (with the
portal URL for manual retrieval), missing API key (keyed tools only), scanned
PDF too large hint. Agents recover well from honest errors, and users see
them verbatim.

### Testing

- Preserve the offline, key-free CI suite: fixture-backed unit tests for
  every new tool, picker parameters, prompt registration, graceful key-less
  degradation of keyed tools, and blob-resource envelope shape.
- `scripts/smoke.py`: manual live end-to-end (Budvar: find → filings →
  get_filing for 3 years → deterministic analysis with pre-extracted fixture
  data; keyed path when a key is present). Run before releases, not in CI.

### README / demo

- Rewrite around the 30-second install (`claude mcp add rejstrik -- uvx
  rejstrik-mcp`), keyless-by-default story, and the two modes.
- Add a comparison table (vs cz-agents-mcp, chytryrejstrik.cz), a GIF of the
  3-year Budvar analysis, and a screenshot of the UI card.
- Document MCP UI card host support honestly (renders in MCP-Apps-capable
  hosts; JSON fallback elsewhere).

## Implementation order

1. **Stage 1** — keyless flow + stdio + packaging (this is the release that
   makes the masthead sentence true).
2. **Stage 2** — multi-year (flagship demo).
3. **Stage 3** — breadth (feature-list growth, competitive parity).

Each stage is independently shippable and gets its own implementation plan
via the writing-plans skill.

## Out of scope (explicitly)

- Hosted public server, auth, rate limiting (may revisit later).
- Company-vs-company comparison tooling (deferred; user chose not to include).
- OCR pipeline / vector store — PDFs go to models as documents, as today.
- Any dependency on the user's separate SaaS product; at most light prompt
  inspiration.
