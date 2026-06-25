# rejstrik-mcp — Design Spec

**Date:** 2026-06-25
**Status:** Design — approved pending spec review

## One-liner

Every other Czech registry tool tells you a company *exists*. `rejstrik-mcp` reads its
50-page annual report, pulls the numbers off page 43, flags the going-concern warning,
lets you interrogate the full document in plain language, and cites every claim back to a
PDF page.

## Why this project exists

This is a public, open-source portfolio piece meant to stand out in interviews and be
newsroom-relevant (live fact-checking a company). It must be a genuine differentiator, not
a worse clone of what already exists.

### Competitive landscape (researched 2026-06-25)

- **`martinhavel/cz-agents-mcp`** (MIT, ~2 stars, actively maintained) — 27 tools across
  ARES, ČNB, EU+OFAC sanctions, ISIR insolvency, ADIS VAT, EU registries, UBO chains.
  Comprehensive on **structured registry data**. Handles **zero documents** — no PDFs, no
  financial statements, no Sbírka listin. Has a closed-source paid "ddplus" tier.
- **`vzeman/ares-mcp-server`** — ARES only.
- **chytryrejstrik.cz** — commercial SaaS; ships its own MCP server + API; paid, closed.

### The gap we own

Nobody open-source touches the **documents**. The justice.cz **Sbírka listin** (collection
of deeds) holds scanned/native PDF annual reports and financial statements — 50+ pages,
often image-only scans. Structured APIs give the *index* of these documents but never the
*contents*. Reading them is the hard part agents can't do today, and it's the most
newsroom-relevant part (the actual numbers and the buried warnings, not just "company
exists"). It also reuses prior art from the author's `financialsAI` project.

**Positioning:** documents are the star; structured registry breadth makes it feel
end-to-end. We win on **depth**, and match only "enough" breadth — chasing 27-tool parity
on day one is how the project never ships.

## Architecture — one core, three faces

A pure core library, with CLI and MCP as thin shells over it. The same logic works with or
without an AI agent (also the cleanest story to tell in an interview, and it makes the core
independently testable).

```
core/
  registry/    ARES: company profile, statutory bodies, VAT
               (adapted from cz-agents-mcp, MIT — attribution required)
  filings/     justice.cz Sbírka listin: list deeds for an IČO, classify which are
               financial statements, fetch the PDF
  documents/   the engine: ingest once, serve two paths (see below)
  analysis/    ratios, trends, red-flag rules, notes summarization, citations
cli/           same core, runnable without any AI (also powers tests + the demo)
mcp/           thin wrapper: stateless-HTTP + stdio transport; returns JSON + optional
               interactive MCP App card
```

### Unit responsibilities

- **registry** — talk to ARES; return structured company identity/profile. Depends on: HTTP
  client. Borrowed/adapted from cz-agents-mcp (MIT) with attribution.
- **filings** — talk to or.justice.cz / dataor.justice.cz; list deeds for an IČO with
  metadata (year, doc type, page count) and tag likely financial statements; download PDFs.
- **documents** — the engine. One ingest pipeline, two serving paths (below).
- **analysis** — pure functions over extracted structured data: ratios, trends, red-flag
  rules, notes summarization. No I/O; fully unit-testable.
- **cli** — argparse/typer surface over core; used for the demo and as an integration
  harness.
- **mcp** — register tools, marshal core results to JSON + App cards. No business logic.

## The document engine (the moat)

One ingest, two serving paths over the same ingested document.

### Ingest (shared)

1. **Classify** each PDF page: native-text vs image-only scan.
2. **Extract** text + tables from native pages (`pdfplumber`/`pypdf`); render scanned pages
   to images (`pdf2image`) for vision.
3. **Build a full-document index** (text + tables across *all* pages) for open-ended Q&A.

### Path 1 — Deterministic extraction (reliable numbers)

- **Page-targeting to control cost:** locate the financial-statement pages (rozvaha /
  výkaz zisku a ztráty / příloha) and send only those to a vision model — never blast all
  50 pages.
- Extract into a Pydantic schema: full balance sheet + P&L line items, cash flow, and the
  notes (related-party deals, pledges, going-concern, litigation, auditor qualifications).
- Every figure carries `{value, source_pdf, page}`.

### Path 2 — Open-ended Q&A / RAG (the headline capability)

- Indexes the **entire** document (all pages, all tables, all narrative text — not just
  financial pages), then answers arbitrary questions with citations.
- Less deterministic than Path 1, but the higher-value capability: the schema can't
  anticipate everything, and the real story is often in a narrative paragraph or an
  off-template table the schema never modeled.
- Examples: "Are there pledges over company assets?", "What did management say about next
  year?", "Who are the related parties and what were the transactions?"
- Conversational: an agent can keep asking follow-ups against the same indexed report.

### Analysis layer (over Path 1 output)

- Computed ratios: liquidity, leverage, profitability, working capital.
- Trends: year-over-year deltas, multi-year direction.
- Red-flag detection: going-concern, negative equity, ballooning debt, related-party
  transactions, late/missing filings, auditor qualifications, ISIR insolvency cross-check.
- Notes intelligence: summarize narrative notes most agents never read.
- Cited output: every figure links to source PDF + page.

## Tool surface (8 tools — depth, not breadth)

| Tool | Purpose |
|---|---|
| `find_company(query)` | name/IČO → identity + ARES profile |
| `list_filings(ico)` | Sbírka listin index, tagged with which docs are financial statements + page counts (tells the agent where to grab it) |
| `extract_financials(filing_ref)` | deterministic engine — structured extraction from one PDF, every figure cited to a page |
| `ask_filing(filing_ref, question)` | **flagship** — open-ended cited Q&A over the *full* report (text + tables + narrative); conversational follow-ups |
| `analyze_company_financials(query)` | **flagship orchestrator** — find → pick latest statement → extract → ratios + trends + red-flags + notes → full report + interactive card. One call = the whole demo |
| `check_insolvency(ico)` | ISIR cross-check (adapted, MIT) |
| `get_statutory_bodies(ico)` | directors / UBO chain (adapted, MIT) |
| `check_vat(ico)` | VAT reliability (adapted, MIT) |

The two stars: `ask_filing` (interrogate) and `analyze_company_financials` (quantify).

## Stack

- **Python** — matches the author's `financialsAI`; best PDF + vision ecosystem.
- **MCP Python SDK** — stateless-HTTP + stdio transport.
- **`pdfplumber` / `pypdf`** — native text + table extraction.
- **`pdf2image` + a Claude vision model** — scanned pages.
- **Pydantic** — schemas + structured output.
- Exact model IDs / SDK details pinned at implementation time using the `claude-api`
  reference (default to the latest capable Claude models; use a cost-efficient model for
  bulk vision pages).

## Scope discipline

**v1 ships the 8 tools above**, with financial-statement extraction + full-document Q&A.

**Deferred to v2 (listed, not built now):**

- Full EU+OFAC sanctions screening
- EU registry coverage (GB/SK/PL/NL/DE/FR)
- Monitoring / alerts (chytryrejstrik's turf)
- Generic `analyze_document` beyond company filings
- Real-estate / distress intelligence

## Risks & mitigations

- **Scanned-OCR quality** on old filings → vision model over rendered pages; flag
  low-confidence extractions rather than guessing.
- **Sbírka listin scraping fragility / rate-limits** → isolate in `filings/`, cache,
  back off politely, fail gracefully.
- **Vision cost** on 50+ page reports → page-targeting (Path 1 sends only financial pages);
  Path 2 indexes text and only falls back to vision for scanned pages.
- **Czech accounting taxonomy → clean schema** → map to a documented Pydantic schema;
  keep raw labels alongside normalized fields.

## Licensing / attribution

- Project: choose a permissive license (MIT) for portfolio visibility.
- Registry clients adapted from `cz-agents-mcp` (MIT) — include its copyright/permission
  notice and credit in README and source headers.
- Respect justice.cz / ARES terms of use and rate limits.

## Success criteria (interview-grade)

- End-to-end demo: one prompt → company found → latest annual report located → numbers
  extracted with citations → ratios/trends/red-flags → free-form question answered with a
  page citation.
- Works as both an MCP server (wired to Claude/agents) and a standalone CLI.
- Clean, tested core; honest README that names competitors and states the differentiator.
