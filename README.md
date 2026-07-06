# rejstrik-mcp

**The Czech registry MCP that reads the documents.**

Every other Czech registry tool tells you a company *exists*. `rejstrik-mcp`
opens its annual report from the Sbirka listin (collection of deeds), pulls the
numbers out of the PDF, flags buried risk signals, lets you interrogate the
report in plain language, and keeps the registry/document/analysis layers usable
from both CLI and MCP clients.

## Why this exists

Open-source Czech-registry tooling, such as `cz-agents-mcp`, covers structured
registry data well: ARES, CNB, sanctions, insolvency, VAT. None of it touches
the documents: scanned/native PDF financial statements that hold the actual
numbers and warnings. Reading those is the hard part agents cannot do today, and
it is the most useful part for fact-checking a company. `rejstrik-mcp` is built
around that gap.

## What it does

| Tool | What it does |
|---|---|
| `find_company` | Resolve a company by name or ICO (ARES) |
| `list_filings` | List the company's Sbirka listin documents, financial statements first |
| `extract_financials` | Deterministic structured extraction from the latest statement |
| `ask_filing` | Free-form Q&A over the full report |
| `analyze_company_financials` | One call: extract -> ratios -> red flags -> structured report |
| `analyze_company_card` | The same report as an interactive HTML card for MCP UI hosts |
| `check_insolvency` | Insolvency cross-check (ISIR) |
| `get_statutory_bodies` | Directors / statutory bodies (ARES public register) |
| `check_vat` | VAT registration plus unreliable-payer flag (ARES + ADIS) |

The two stars are `ask_filing` (interrogate the report) and
`analyze_company_financials` (quantify and flag it). Use
`analyze_company_card` when the MCP host supports UI resources; the structured
analysis tool remains the fallback for text-only hosts.

## Quickstart

```bash
pip install -e ".[dev]"
export OPENAI_API_KEY=sk-...          # supported for document extraction
# or
export ANTHROPIC_API_KEY=sk-ant-...   # supported for document extraction and cited Q&A

# CLI
rejstrik find "Budejovicky Budvar"
rejstrik filings 00514152 --financial-only
rejstrik analyze "Budejovicky Budvar"

# MCP server (stateless streamable-http on /mcp)
rejstrik-mcp
```

Point any MCP client at the server's `/mcp` endpoint to use all nine tools.

## How it works

```text
core/      shared HTTP + text utilities
registry/  ARES, ISIR (insolvency), ADIS (VAT), statutory bodies
filings/   verejnerejstriky.msp.gov.cz Sbirka listin client
documents/ native-PDF extraction + document Q&A
analysis/  normalize -> ratios -> red flags -> trends (pure, no I/O)
service/   orchestration (registry + filings + documents + analysis)
cli/ mcp/  two faces over one core
```

The document engine sends PDFs directly to the configured model, so there is no
OCR pipeline or vector database. Structured extraction uses Pydantic schemas;
open-ended Q&A uses the same document abstraction and returns citations when the
provider supports them.

### A Note On Real-World Drift

Midway through the build, the Czech Ministry of Justice migrated the Sbirka
listin from `or.justice.cz` to a new Nuxt portal
(`verejnerejstriky.msp.gov.cz`). The filings client was re-pointed at the new
portal's API. Registry, filings, insolvency, statutory-body, VAT, and ADIS
lookups are covered by fixtures/unit tests; live smoke testing verified the
registry/document analysis path against Budejovicky Budvar with OpenAI.

## CI

The GitHub Actions workflow in `.github/workflows/ci.yml` runs `ruff` and
`pytest` on Python 3.11 and 3.12. The test suite is deliberately offline and
key-free, so a green CI run means the fixtures, parsers, service layer, CLI, and
MCP registrations are internally consistent without live endpoint luck.

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/
ruff format --check src/ tests/
python -m pytest -q
```

Useful manual smoke tests:

```bash
rejstrik analyze "Budejovicky Budvar"
rejstrik-mcp
```

## Attribution

The insolvency (ISIR), VAT/unreliable-payer (ADIS), and statutory-body registry
clients are adapted from
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT, Martin
Havel). See `LICENSES/cz-agents-mcp-LICENSE`.

## Releasing

1. One-time: on pypi.org, add a *Trusted Publisher* for this GitHub repo
   (workflow `release.yml`, environment `pypi`).
2. Bump the version in `pyproject.toml`, commit, tag `vX.Y.Z`, push the tag.
   CI builds, publishes to PyPI, and attaches artifacts to the GitHub release.

## License

MIT.
