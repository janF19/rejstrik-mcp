# Stage C: MCP Apps Card + Large-PDF Delivery

**Date:** 2026-07-13
**Status:** Approved design, pending implementation plan
**Parent:** `2026-07-13-roadmap-overview.md`
**Ships as:** v0.5.0

## Problem

Two related delivery problems, both about getting content to the user:

1. **The card renders almost nowhere.** `render_card` /
   `analyze_company_card` emit an mcp-ui `rawHtml` UIResource. The
   official **MCP Apps** extension (2026-01-26,
   blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps) is what Claude
   Desktop / claude.ai / Cowork, ChatGPT, Goose, and VS Code render;
   there are open reports of mcp-ui-style embedded resources NOT
   rendering in Claude Desktop (ext-apps issue #671). Claude Code renders
   no UI at all — there the card is raw HTML text noise.
2. **Filed PDFs are big and that's normal.** ~50-page statements at
   20–25 MB are routine. Product decision (2026-07-13): large PDFs must
   reach the calling agent — a blunt embed cap that silently drops the
   PDF is unacceptable. At the same time, a 25 MB PDF is ~33 MB of
   base64; no host can put that in context, so "embed harder" is not the
   answer either. The design must make the *file path* the primary
   channel and give path-less hosts a workable alternative.

## Design — Part 1: MCP Apps migration

- Adopt the official MCP Apps pattern: declare the card's `ui://` HTML
  as a **server resource** referenced from the tool's metadata
  (`_meta` UI declaration per the ext-apps spec), with capability
  negotiation, instead of embedding raw HTML in the tool result.
  Use the official Python SDK support / `ext-apps` helper if available at
  implementation time; verify current API on day one (the ecosystem moves
  monthly).
- **Graceful degradation is mandatory:** when the host does not negotiate
  the apps capability, `render_card` returns a compact **markdown
  summary** (table of ratios, flag list with severities, trend arrows)
  instead of raw HTML — this makes the tool genuinely useful in Claude
  Code rather than emitting 3 KB of angle brackets.
- Keep `mcp-ui-server` compatibility only if it costs nothing; otherwise
  drop the dependency and note it in the changelog. Verify against MCP
  Inspector + at least one real Apps host (Claude Desktop) before release.

### Card content (earns its place)

The current card shows five ratios and flags. The redesigned card adds,
in order:

1. Header: company, IČO, period, currency, source filing title.
2. **Multi-year table**: normalized figures (revenue, net profit, total
   assets, equity) per year with YoY deltas — this is the flagship
   multi-year feature, currently absent from the card entirely.
3. Ratios with plain-language one-liners (e.g. current_ratio 0.8 —
   "short-term obligations exceed liquid assets").
4. Red flags sorted by severity, color-coded (existing palette fine).
5. When provided: public-money section (subsidies + contracts totals vs
   revenue).
6. Footer: source + "figures as filed; typically thousands of CZK".

Self-contained HTML/CSS, no external requests (Apps iframes are
sandboxed). Interactivity is optional polish, not scope: a static,
well-designed card ships Stage C.

`CompanyFinancialReport` already carries statements/trends; if the card
needs per-year normalized figures, extend the report model additively
(don't break `analyze_financials` consumers).

## Design — Part 2: Large-PDF delivery

`get_filing` changes:

- **`embed` parameter: `"auto" | "always" | "never"`, default `"auto"`.**
  - `auto`: embed only if size ≤ `REJSTRIK_MAX_EMBED_BYTES`. **Default
    raised 15 MB → 25 MB** (owner decision 2026-07-13: filed statements
    of 20–25 MB are routine and must never be silently dropped). The
    context-blowup risk is managed by steering filesystem hosts to
    `embed="never"`, not by capping the PDF.
  - `never`: metadata + file path only. The `analyze-company` prompt and
    tool description instruct filesystem-capable hosts (Claude Code,
    Codex, Desktop with fs access) to pass `embed="never"` — the path is
    strictly better for them.
  - `always`: embed regardless (host explicitly accepts the cost), still
    hard-capped at the env limit with an honest message beyond it.
- Metadata gains `page_count` (pypdf, cheap) so hosts can plan reading.

**New tool: `read_filing_text(ico, year=None, filing_id=None,
pages="1-10")`** — extracts the embedded text layer of the requested page
range with pypdf. No LLM, no OCR, keyless.

- Purpose: hosts without filesystem access get the statement content in
  digestible slices regardless of PDF size; even filesystem hosts can use
  it to target the balance-sheet pages.
- Czech filings are frequently scanned images with no text layer. When a
  page yields no text, say so explicitly per page and suggest the keyed
  mode (`extract_financials`) or filesystem reading. This honesty rule is
  part of the spec: never return empty string as if the page were blank.
- Page-range grammar: `"3"`, `"1-5"`, `"1-3,7"`; cap total pages per call
  (default 20) with an honest over-cap message.

Dependency note: adds `pypdf` (pure Python, no system deps) — acceptable.

## Not in scope

- OCR of scanned pages (stays keyed-mode territory).
- Interactive card actions (tool round-trips from the iframe) — future.

## Testing

Offline: capability-negotiation branch (Apps resource vs markdown
fallback), card HTML golden-ish assertions (sections present, escaping),
`embed` tri-state matrix incl. over-limit honesty, `read_filing_text`
page-range parsing + no-text-layer honesty (fixture PDFs: one with text
layer, one image-only — tiny generated fixtures, not real filings).

## Acceptance

- Card visibly renders in Claude Desktop (screenshot feeds Stage E).
- In Claude Code, `render_card` yields readable markdown, no raw HTML.
- A 25 MB fixture-path flow works end-to-end via `embed="never"` + path.
- `read_filing_text` returns real text for a text-layer PDF and an honest
  explanation for a scanned one.
