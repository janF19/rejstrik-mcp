# rejstrik-mcp

[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) <!-- PyPI badge hidden until first publish (Stage E T5/T6); restore this line: [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/) -->

**Add the Czech business registry to your Claude in 30 seconds — no API key.
It reads the actual filed PDFs with your own subscription.**

```bash
claude mcp add rejstrik -- uvx rejstrik-mcp
```

## See it work

Demo media is being recorded (see `scripts/record_demo.sh`, which needs
asciinema + agg); meanwhile the walkthrough below shows the exact flow.

Then ask: *"What happened to Budějovický Budvar's finances last year?"* —
your agent resolves the company (ARES), pulls the filed statement PDF from
the Sbírka listin, reads it itself, and gets deterministic ratios, red
flags, and trends back from the server. No OCR pipeline, no server-side AI
key, no scraping middleman.

## Why this one

|  | agent-native (MCP) | reads filed PDFs | free & open source | works without any API key |
|---|---|---|---|---|
| cz-agents-mcp and similar | ✅ | ❌ | ✅ | ✅ |
| chytryrejstrik.cz | ❌ | partly (paid) | ❌ | — |
| **rejstrik-mcp** | ✅ | ✅ | ✅ | ✅ |

## Install

**Claude Code:** `claude mcp add rejstrik -- uvx rejstrik-mcp`

**Claude Desktop:** download `rejstrik-mcp.mcpb` from the latest GitHub
release and double-click it (requires [uv](https://docs.astral.sh/uv/)) —
or add to `claude_desktop_config.json`:

```json
{ "mcpServers": { "rejstrik": { "command": "uvx", "args": ["rejstrik-mcp"] } } }
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.rejstrik]
command = "uvx"
args = ["rejstrik-mcp"]
```

**Any HTTP host:** `uvx rejstrik-mcp --http` serves streamable HTTP on
`http://127.0.0.1:8000/mcp`.

## Two modes, one server

**Keyless (default).** Your agent does the reading with your existing
subscription; the server does everything deterministic:

| Tool | What it does |
|---|---|
| `find_company` | Resolve a company by name or IČO (ARES) |
| `list_filings` | List Sbírka listin documents, financial statements first |
| `get_filing` | Download a statement PDF (latest, by year, or by id) — returns local path + `page_count`; `embed` controls whether the PDF bytes are also returned (`"auto"` default, `"always"`, or `"never"`) |
| `read_filing_text` | Keyless extraction of the PDF text layer for a page range (no LLM/OCR); pages without a text layer are reported honestly |
| `analyze_financials` | Your extracted figures in → ratios, red flags, IN05 distress index, year-over-year trends out (no LLM) |
| `estimate_valuation` | Your extracted figures in → indicative valuation range (book value, capitalized earnings, multiples), no LLM. Not investment advice |
| `render_card` | The report as a card — an interactive HTML card for MCP Apps hosts, a markdown summary for text-only hosts like Claude Code |
| `check_insolvency` | Insolvency register (ISIR) |
| `get_statutory_bodies` | Directors / statutory bodies (ARES) |
| `check_vat` | VAT registration + unreliable-payer flag (ARES + ADIS) |
| `get_subsidies` | State subsidies received (IS ReD / former CEDR) |
| `get_contracts` | Public contracts involving the company (Registr smluv) |

**Beneficial owners.** The public part of ESM (Evidence skutečných
majitelů) closed on 2025-12-17 following an EU Court of Justice ruling, so
beneficial-owner lookups are intentionally not offered here — a documented
scope decision, not a gap.

Use the built-in **`analyze-company`** prompt (shows up as a slash command
in Claude) to run the whole loop — find → fetch PDFs → extract → analyze →
card — including multi-year trends.

**Keyed power mode (optional).** Set `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY` where the server runs and four more tools activate, doing
the PDF reading server-side with schema-locked extraction and page
citations: `extract_financials`, `ask_filing`,
`analyze_company_financials`, `analyze_company_card`. Without a key they
politely point you back to the keyless flow.

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

### Autopilot (unattended roadmap execution)

The July 2026 roadmap stages (`docs/superpowers/specs/2026-07-13-*.md`)
can be run unattended: Opus writes each stage's implementation plan,
Sonnet executes it in an isolated git worktree, and the script verifies
(ruff + pytest) and merges only on green. State is derived from git, so
the script can be stopped and rerun anywhere after a clone. Requires a
logged-in Claude Code CLI; see
`docs/superpowers/specs/2026-07-13-autopilot-design.md`.

```bash
python scripts/autopilot.py --dry-run   # show what would happen
python scripts/autopilot.py             # run remaining stages
```

Useful manual smoke tests:

```bash
rejstrik analyze "Budejovicky Budvar"
rejstrik-mcp
python scripts/smoke.py            # live network required — run before releases, not in CI
```

## Attribution

The insolvency (ISIR), VAT/unreliable-payer (ADIS), and statutory-body registry
clients are adapted from
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT, Martin
Havel). See `LICENSES/cz-agents-mcp-LICENSE`.

## Releasing

1. One-time: on pypi.org, add a *Trusted Publisher* for this GitHub repo
   (workflow `release.yml`, environment `pypi`).
2. Bump `version` in **all four** places so they agree: `pyproject.toml`,
   `server.json` (top-level **and** `packages[0].version`), `mcpb/manifest.json`,
   and `src/rejstrik/__init__.py` (`__version__`). `tests/test_version_sync.py`
   fails if any of them drift.
3. If the release changes the published server, re-run the MCP registry
   publisher flow with the updated `server.json`.
4. Commit, tag `vX.Y.Z`, push the tag. CI builds, publishes to PyPI, and
   attaches artifacts to the GitHub release.

## License

MIT.
