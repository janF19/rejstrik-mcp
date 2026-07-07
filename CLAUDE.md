# CLAUDE.md

Guidance for AI agents working in this repository.

## What this is
An MCP server + CLI exposing the Czech company registry, with the
differentiator that it reads the filed PDF financial statements. Keyless by
default (the calling agent reads PDFs); an optional server-side API key
enables in-server extraction.

## Layout
- `core/` shared HTTP (retrying client) + text utilities
- `registry/` ARES, ISIR (insolvency), ADIS (VAT), statutory bodies
- `filings/` Sbírka listin client (verejnerejstriky.msp.gov.cz)
- `documents/` PDF fetch/cache + keyed extraction + Q&A
- `analysis/` normalize → ratios → red flags → trends (pure, no I/O)
- `service.py` orchestration; `cli/` and `mcp/` are two faces over it

## Rules
- Tests are offline and key-free. Mock the LLM via the `DocumentLLM`
  protocol and registry checks via the `*_check` injection points.
- Follow TDD: failing test → minimal impl → green → commit.
- Always run `ruff check src/ tests/ && ruff format --check src/ tests/ &&
  python -m pytest -q` before committing.
- Live network checks live in `scripts/smoke.py`, never in CI.

## Commands
- Install: `pip install -e ".[dev]"`
- Test: `python -m pytest -q`
- Run MCP server (stdio): `rejstrik-mcp`  (HTTP: `rejstrik-mcp --http`)
- Live smoke: `python scripts/smoke.py`
