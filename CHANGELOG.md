# Changelog

## 0.6.0 — Stage D: analysis depth + indicative valuation

- Extraction now fills a `canonical` object on each `FinancialStatement`
  (total assets, equity, revenue, operating/net profit, interest expense,
  cash, inventories, receivables, operating cash flow) keyed to the exact
  Czech statutory lines. `normalize()` prefers these canonical figures and
  falls back to a hardened keyword matcher that no longer mistakes asset-sale
  revenue for turnover or the operating result for the net result.
- Six new ratios: quick ratio, return on assets, asset turnover, interest
  coverage, operating margin, and operating-cash-flow-to-liabilities.
- New `IN05` distress index (Neumaier & Neumaierová) with distress / grey /
  value-creating zones, feeding `in05_distress` (critical) and `in05_grey_zone`
  (info) red flags. New red flags: `low_interest_coverage` (critical) and
  `negative_operating_cash_flow` with a reported profit (warning).
- Reports now carry a full multi-year `trend_series` (year-by-year values plus
  CAGR when ≥3 years with positive endpoints), in addition to the latest-vs-prior
  `trends`.
- New keyless tool `estimate_valuation(statements, assumptions=None)`: book
  value, capitalized earnings, and generic EV/EBIT and price/revenue multiples,
  with an overall range, the assumptions used, and a caveats list. Indicative
  only — not investment advice.

## 0.5.0 — Stage C: card delivery + large PDFs

- Card output now degrades gracefully: hosts that negotiate the MCP Apps
  capability get an interactive HTML card (registered as the `ui://rejstrik/report`
  resource); text-only hosts (Claude Code, etc.) get a compact markdown summary
  instead of raw HTML. The card now shows a multi-year figures table, ratios with
  plain-language one-liners, severity-sorted red flags, and a public-money section.
- `get_filing` gains an `embed` parameter (`"auto" | "always" | "never"`, default
  `"auto"`). The default embed cap is raised 15 MB → 25 MB
  (`REJSTRIK_MAX_EMBED_BYTES`). Large PDFs are never silently dropped — filesystem
  hosts are steered to `embed="never"` and the local `file_path`. Metadata now
  includes `page_count`.
- New keyless tool `read_filing_text(ico, year=None, filing_id=None, pages="1-10")`
  extracts the PDF text layer for a page range (pypdf, no LLM/OCR). Pages without a
  text layer are reported honestly rather than as empty strings.
- New dependency: `pypdf`.
