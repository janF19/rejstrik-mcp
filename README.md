# rejstrik-mcp

Czech company registry MCP that reads the documents.

## About

A Python MCP server for exploring Czech companies via the ARES registry and their financial filings from the Sbírka listin (Records) database. Provides company lookup, document listing, and a document engine that extracts structured financials from PDF filings and answers free-form questions with page citations.

### Competitive positioning

- **cz-agents-mcp** (registry lookup only) – provides basic registry search but no document reading
- **chytryrejstrik.cz** (commercial web tool) – web-based interface
- **rejstrik-mcp** – open-source document engine: structured financial extraction + cited Q&A over the actual PDF

## Installation

```bash
pip install -e ".[dev]"
```

This installs the package with development dependencies (pytest, ruff, respx).

## CLI Commands

Two commands are available via the `rejstrik` entry point:

### `rejstrik find`

Resolve a company by name or IČO via ARES:

```bash
$ rejstrik find "Budějovický Budvar"
00002836  Budějovický Budvar, n.p.  Karolíny Světlé 594/4, 370 01 České Budějovice
```

### `rejstrik filings`

List Sbírka listin documents for a company:

```bash
$ rejstrik filings 00514152 --financial-only
[FS] 2023  Účetní závěrka 2023  https://or.justice.cz/ias/ui/vypis-sl-31231.pdf
[FS] 2022  Účetní závěrka 2022  https://or.justice.cz/ias/ui/vypis-sl-31232.pdf
```

The `[FS]` marker indicates a financial statement (ucetní závěrka, výroční zpráva, rozvaha, výkaz zisku, zpráva auditora). Use `--financial-only` to filter to financial statements only.

## Document engine

Requires an Anthropic API key. Claude reads the PDF natively (scanned pages included) and cites exact pages — no OCR pipeline.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Defaults to `claude-opus-4-8`. Override with `REJSTRIK_MODEL` (e.g. `claude-haiku-4-5`) for lower cost at the expense of quality.

### `rejstrik extract`

Extract structured financials from the latest financial statement PDF:

```bash
$ rejstrik extract 00514152
Budějovický Budvar, n.p.  (2023)
  Dlouhodobý majetek: 2847432000.0  (p.5)
  Oběžná aktiva: 1923847000.0  (p.6)
  Výsledek hospodaření: 312847000.0  (p.8)
  Tržby z prodeje výrobků: 4123847000.0  (p.9)
```

Returns rozvaha, výkaz zisku a ztráty, cash flow (if present), and narrative notes — every figure tagged with the page it was found on.

### `rejstrik ask`

Ask any free-form question about the filing, with page citations:

```bash
$ rejstrik ask 00514152 "Are there any pledges or guarantees over company assets?"
No significant pledges or guarantees were identified over company assets. The company
holds real estate and machinery free of encumbrance as stated in the notes.

Sources:
  - zástavní právo nebylo zřízeno (p.43)
  - majetek není zatížen zástavním právem (p.44)
```

## Analysis

### `rejstrik analyze`

Run the full analysis pipeline over the latest financial statement:

```bash
$ rejstrik analyze 00514152
Budějovický Budvar, n.p.  (2023)  [00514152]
Ratios:
  current_ratio: 1.842
  equity_ratio: 0.517
  debt_to_equity: 0.934
  net_margin: 0.076
  return_on_equity: 0.147
Red flags:
  [INFO] Related-party note: Transactions with related parties are disclosed in the notes.
```

The analysis layer normalizes fuzzy Czech or English line labels into canonical fields, computes core ratios, checks ISIR for active insolvency proceedings, and scans note summaries for red flags such as going-concern language, related-party disclosures, low liquidity, high leverage, net losses, negative equity, and insolvency.

## MCP server

Run the stateless FastMCP server with Streamable HTTP transport:

```bash
rejstrik-mcp
```

The server exposes these eight tools:

- `find_company`
- `list_filings`
- `extract_financials`
- `ask_filing`
- `analyze_company_financials`
- `check_insolvency`
- `get_statutory_bodies`
- `check_vat`

Point an MCP-capable client at the default `/mcp` endpoint served by FastMCP. The tools return structured Pydantic output, so agents can consume either raw extracted financial statements or the higher-level analysis report.

`check_vat` reports VAT registration and DIČ from ARES. The ADIS unreliable-payer flag is a separate SOAP integration and is intentionally deferred.

## Architecture

- **Core library** (`rejstrik.registry`, `rejstrik.filings`) — model definitions, API clients, parsers
- **Document engine** (`rejstrik.documents`) — PDF resolver, financial schema, LLM protocol, extraction and Q&A orchestration
- **CLI** (`rejstrik.cli.main`) – typer-based command interface for interactive use
- **Analysis layer** (`rejstrik.analysis`, `rejstrik.service`) – normalization, ratios, red flags, trends, and one-call financial analysis
- **MCP server** (`rejstrik.mcp.server`) – FastMCP server exposing the registry, document, and analysis tools

## Attribution

The insolvency (ISIR) and statutory-body registry clients are adapted from
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT License,
(c) Martin Havel). See `LICENSES/cz-agents-mcp-LICENSE`.

## License

MIT License. See LICENSE file for details.
