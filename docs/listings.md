# Directory / Community Listing Copy

Ready-to-paste copy for submitting rejstrik-mcp to MCP directories and
community lists. Pick the fields each directory asks for. All facts below
are current as of v0.8.0 (published to PyPI 2026-07-18).

**Canonical links** (paste as needed):
- Repo: https://github.com/janF19/rejstrik-mcp
- PyPI: https://pypi.org/project/rejstrik-mcp/
- Registry name: `io.github.janF19/rejstrik-mcp`
- License: MIT
- Install: `claude mcp add rejstrik -- uvx rejstrik-mcp`

---

## Name

rejstrik-mcp

## One-liner (≤ 80 chars)

Czech company registry for your AI — reads the filed PDF financials, no API key.

## Short description (1–2 sentences)

An MCP server that brings the Czech business registry (ARES, insolvency,
VAT, statutory bodies, filed financial statements) to any MCP host. It's
keyless: the calling agent reads the filed PDFs with its own model, and
the server does the deterministic work — ratios, IN05 distress index,
trends, red flags, and an indicative valuation.

## Long description (paragraph)

rejstrik-mcp adds the Czech business registry to Claude (or any MCP host)
in about 30 seconds, with no API key of any kind. Point it at a company by
name or IČO and it resolves the registry record, lists the filings in the
Sbírka listin, and fetches the actual filed PDF financial statements. The
host model reads those PDFs itself — so document understanding runs on your
existing subscription, not a separate paid API — and hands the extracted
figures back to the server, which computes financial ratios, the IN05
bankruptcy-prediction index, year-over-year trends, red flags, and an
indicative valuation range. It also checks insolvency proceedings, VAT
reliability, statutory bodies, state subsidies, and public contracts. Runs
over stdio or streamable HTTP; ships as a PyPI package and a one-click
`.mcpb` bundle for Claude Desktop.

## Categories / tags

`finance` · `government-data` · `czech-republic` · `company-registry` ·
`pdf` · `financial-analysis` · `keyless` · `due-diligence`

## Install snippets

**Claude Code**
```bash
claude mcp add rejstrik -- uvx rejstrik-mcp
```

**Claude Desktop** — download `rejstrik-mcp.mcpb` from the latest GitHub
release and double-click (requires [uv](https://docs.astral.sh/uv/)), or
add to `claude_desktop_config.json`:
```json
{ "mcpServers": { "rejstrik": { "command": "uvx", "args": ["rejstrik-mcp"] } } }
```

**Codex** (`~/.codex/config.toml`)
```toml
[mcp_servers.rejstrik]
command = "uvx"
args = ["rejstrik-mcp"]
```

**Any HTTP host**
```bash
uvx rejstrik-mcp --http   # streamable HTTP on http://127.0.0.1:8000/mcp
```

## Tools exposed (13, all keyless)

`find_company`, `list_filings`, `get_filing`, `read_filing_text`,
`read_filing_page_images`, `analyze_financials`, `estimate_valuation`,
`render_card`, `check_insolvency`, `get_statutory_bodies`, `check_vat`,
`get_subsidies`, `get_contracts`

## Why it's different (for directories that want a hook)

Most registry tools stop at the JSON metadata. rejstrik-mcp goes to the
filed PDF financial statements — the real numbers — and because it's
keyless, the reading is done by the host model you're already paying for.
No OpenAI or Anthropic API key is required or accepted anywhere in the
project.

---

## Suggested submission targets

- Official MCP registry (`io.github.janF19/rejstrik-mcp` — publish via
  `mcp-publisher`; see the release checklist)
- Awesome MCP Servers lists (GitHub) — open a PR adding the repo under a
  finance/government category
- MCP host marketplaces / directories that accept community submissions
- r/mcp or relevant community channels (optional announce post using the
  long description above)

> Auth to each directory (GitHub PR, registry login, forum account) is a
> manual step — this file only provides the copy.
