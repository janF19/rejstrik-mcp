# rejstrik-mcp

Czech company registry MCP that reads the documents.

## About

A Python MCP server for exploring Czech companies via the ARES registry and their financial filings from the Sbírka listin (Records) database. Currently provides company lookup and document listing; a document analysis engine is coming in Plan 2.

### Competitive positioning

- **cz-agents-mcp** (registry lookup only) – provides basic registry search but no document reading
- **chytryrejstrik.cz** (commercial web tool) – web-based interface
- **rejstrik-mcp** – open-source document engine (financial statement extraction and Q&A) coming in Plan 2

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

## Architecture

- **Core library** (`rejstrik.registry`, `rejstrik.filings`) — model definitions, API clients, parsers
- **CLI** (`rejstrik.cli.main`) — typer-based command interface for interactive use
- **MCP server** — deferred to Plan 3

## Attribution

This project will adapt registry code from [cz-agents-mcp](https://github.com/havel-martin/cz-agents-mcp) (MIT License © Martin Havel) in Plan 3. Credit will be added at that time.

## License

MIT License. See LICENSE file for details.
