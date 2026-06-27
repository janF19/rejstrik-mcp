# Plan 6 — Polished README + GitHub Actions CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo presentable and trustworthy for a public/portfolio audience: continuous integration that proves the suite is green on every push, and a README that sells the project's positioning and engineering story at a glance.

**Architecture:** No application code changes. One GitHub Actions workflow runs `ruff` + `pytest` on push/PR across Python 3.11 and 3.12 — the suite is fully offline (fakes + fixtures, no `ANTHROPIC_API_KEY`, no live registry calls), so CI is deterministic. The README is a full rewrite around the positioning and the real "registry migrated mid-build" story, with a tool table, quickstart, architecture sketch, and attribution.

**Tech Stack:** GitHub Actions, `ruff`, `pytest`. No new runtime dependencies.

## Global Constraints

- CI must be **network-free and key-free** — it must pass without `ANTHROPIC_API_KEY` and without reaching ARES/justice/ISIR/ADIS. (The suite already meets this; the workflow must not introduce a step that needs them.)
- README claims must be **true at the commit they describe** — only list tools/commands that exist; mark live-verification status honestly (registry verified live; AI document pipeline requires a key to run).
- Keep badges accurate (CI badge points at the real workflow file/branch).

---

### Task 1: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:** none (infra).

- [ ] **Step 1: Verify the suite is offline + green locally first**

Run: `python -m pytest -q`
Expected: ALL PASS with no network. (If any test reaches the network, fix it before adding CI — CI will hang/fail otherwise.)

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install
        run: pip install -e ".[dev]"
      - name: Lint
        run: |
          ruff check src/ tests/
          ruff format --check src/ tests/
      - name: Test
        run: python -m pytest -q
```

- [ ] **Step 3: Validate the workflow YAML locally**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Expected: `yaml ok`. (If `pyyaml` is unavailable, skip — GitHub validates on push.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow (ruff + pytest, py3.11/3.12)"
```

- [ ] **Step 5: Confirm green after push (manual, once the repo is on GitHub)**

After pushing to GitHub, open the Actions tab and confirm both matrix jobs pass. If `ruff format --check` fails, run `ruff format src/ tests/` locally, commit, and push.

---

### Task 2: Polished README

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Rewrite `README.md`**

Use this structure and content (adapt counts/commands to the implemented state — 9 MCP tools after Plan 5, 8 if Plan 5 not yet done):

````markdown
# rejstrik-mcp

**The Czech registry MCP that reads the documents.**

Every other Czech registry tool tells you a company *exists*. `rejstrik-mcp`
opens its 50-page annual report from the Sbírka listin (collection of deeds),
pulls the numbers off page 43, flags the going-concern warning, lets you
interrogate the full report in plain language, and **cites every claim back to a
PDF page**.

[![CI](https://github.com/<user>/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/<user>/rejstrik-mcp/actions/workflows/ci.yml)

## Why this exists

Open-source Czech-registry tooling (e.g. `cz-agents-mcp`) covers *structured*
registry data well — ARES, ČNB, sanctions, insolvency, VAT. None of it touches
the **documents**: the scanned/native PDF financial statements that hold the
actual numbers and the buried warnings. Reading those is the hard part agents
can't do today, and it's the most useful part for fact-checking a company.
`rejstrik-mcp` is built around that gap.

## What it does

| Tool | What it does |
|---|---|
| `find_company` | Resolve a company by name or IČO (ARES) |
| `list_filings` | List the company's Sbírka listin documents (financial statements first) |
| `extract_financials` | Deterministic, page-cited structured extraction from the latest statement |
| `ask_filing` | Free-form, page-cited Q&A over the *full* report |
| `analyze_company_financials` | One call: extract → ratios → red flags → cited report |
| `analyze_company_card` | The same report as an interactive HTML card (MCP UI hosts) |
| `check_insolvency` | Insolvency cross-check (ISIR) |
| `get_statutory_bodies` | Directors / statutory bodies (ARES public register) |
| `check_vat` | VAT registration + unreliable-payer flag (ARES + ADIS) |

The two stars: **`ask_filing`** (interrogate the report) and
**`analyze_company_financials`** (quantify + flag it), both page-cited.

## Quickstart

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...      # required for the document tools

# CLI
rejstrik find "Budějovický Budvar"
rejstrik filings 00514152 --financial-only
rejstrik analyze "Budějovický Budvar"

# MCP server (stateless streamable-http on /mcp)
rejstrik-mcp
```

Point any MCP client (Claude, etc.) at the server's `/mcp` endpoint to use all
nine tools.

## How it works

```
core/      shared HTTP + text utilities
registry/  ARES, ISIR (insolvency), ADIS (VAT), statutory bodies
filings/   verejnerejstriky.msp.gov.cz Sbírka listin client
documents/ the engine: native-PDF extraction (structured) + cited Q&A (RAG-free)
analysis/  normalize → ratios → red flags → trends  (pure, no I/O)
service/   orchestration (registry + filings + documents + analysis)
cli/ mcp/  two faces over one core
```

Claude reads the PDFs natively (scanned pages via built-in vision), so there is
no OCR pipeline or vector DB — structured extraction uses structured outputs;
open-ended Q&A uses the citations API.

### A note on real-world drift

Midway through the build, the Czech Ministry of Justice migrated the Sbírka
listin from `or.justice.cz` to a new Nuxt portal
(`verejnerejstriky.msp.gov.cz`). The filings client was re-pointed at the new
portal's API. Registry, filings, insolvency, statutory-body, and VAT lookups are
verified against live endpoints; the document tools require an Anthropic API key
to run.

## Attribution

The insolvency (ISIR), VAT/unreliable-payer (ADIS), and statutory-body registry
clients are adapted from
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT, © Martin
Havel). See `LICENSES/cz-agents-mcp-LICENSE`.

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/ && ruff format --check src/ tests/
python -m pytest -q          # fully offline — no API key or network needed
```

## License

MIT.
````

- [ ] **Step 2: Verify the README is accurate against the code**

Run: `python -c "from rejstrik.mcp.server import EXPOSED_TOOL_NAMES; print(len(EXPOSED_TOOL_NAMES), EXPOSED_TOOL_NAMES)"`
Cross-check that every tool named in the README's table exists in `EXPOSED_TOOL_NAMES`, and that the CLI commands (`find`, `filings`, `analyze`, `extract`, `ask`) exist in `cli/main.py`. Fix any mismatch (e.g. drop `analyze_company_card` from the table if Plan 5 is not yet implemented).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: polished README (positioning, tool table, architecture, migration note)"
```

---

### Task 3: Repo metadata polish (optional, low-risk)

**Files:**
- Modify: `pyproject.toml`

**Interfaces:** none.

- [ ] **Step 1: Add project URLs + classifiers**

Add to `[project]` in `pyproject.toml` (adjust the GitHub URL):

```toml
license = "MIT"
readme = "README.md"
authors = [{ name = "<your name>" }]
classifiers = [
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
]

[project.urls]
Repository = "https://github.com/<user>/rejstrik-mcp"
```

- [ ] **Step 2: Verify the package still builds/imports**

Run: `pip install -e ".[dev]" && python -c "import rejstrik; print(rejstrik.__version__)"`
Expected: prints `0.1.0` with no metadata errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: project metadata (urls, classifiers, license)"
```

---

## Self-Review

**Coverage:**
- GitHub Actions CI (ruff + pytest, matrix, offline) → Task 1. ✓
- Polished README (positioning, tool table, quickstart, architecture, migration story, attribution) → Task 2. ✓
- Portfolio metadata (badge, URLs, classifiers) → Tasks 1/3. ✓

**Placeholder scan:** The `<user>` / `<your name>` tokens in the README and `pyproject.toml` are real values the implementer fills with the actual GitHub handle/name — flagged, not forgotten. Task 2 Step 2 enforces accuracy by cross-checking the tool table against `EXPOSED_TOOL_NAMES` and the CLI commands, so the README cannot claim tools that don't exist.

**Consistency / honesty:** The README's tool count and command list are verified against the code in Task 2 Step 2; the migration note and live-verification status reflect what was actually confirmed (registry live; document tools need a key). CI is constrained to the offline suite so the badge is meaningful.

**Note:** This plan is independent of Plan 5 — run it in either order. If Plan 5 is not yet implemented, drop `analyze_company_card` and the ADIS unreliable-payer mention from the README table (Task 2 Step 2 catches this) and the tool count is 8.
