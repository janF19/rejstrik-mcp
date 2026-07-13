# rejstrik-mcp: July 2026 Hardening & Depth Roadmap (Umbrella Spec)

**Date:** 2026-07-13
**Status:** Approved direction, pending per-stage implementation plans
**Builds on:** `2026-07-06-keyless-pivot-and-growth-design.md` (Stages 1–3 shipped as v0.4.0)

## Why this roadmap exists

A full audit on 2026-07-13 (live-tested against the running MCP server)
found the product close to its goal on paper but not in practice:

1. **The core loop is broken live.** `verejnerejstriky.msp.gov.cz` now
   returns 403 (Azure Front Door block page) to every programmatic client
   tested — httpx with the project UA, curl with browser UA + cookies +
   referer, a sandboxed Chromium, and Anthropic's remote fetcher. Since
   `list_filings` and `get_filing` depend on it, "reads the actual filed
   PDFs" fails today. The legacy portal `or.justice.cz` still returns 200
   and the repo retains its parsers.
2. **The UI card doesn't render where users are.** The card ships as an
   mcp-ui `rawHtml` UIResource. The official **MCP Apps** extension
   (launched 2026-01-26) is what Claude Desktop / claude.ai / Cowork,
   ChatGPT, Goose, and VS Code render; Claude Code renders neither. In
   Claude Code the card arrives as raw HTML text.
3. **The test suite fails on Windows (6 failures)** and is not hermetic:
   a repo-root `.env` leaks `OPENAI_API_KEY` into `has_llm_key()` because
   `documents/config.py` reloads dotenv on every call, undoing
   `monkeypatch.delenv`; and `tests/mcp/test_get_filing.py` uses a
   POSIX-only fake path that breaks `Path.as_uri()` on Windows. CI is
   Linux-only, so it stays green.
4. **README credibility gaps.** The "See it work" GIF and card screenshot
   don't exist (`docs/media/` holds only a placeholder); the ESM closure
   date reads "2026-12-17" (a future date described as past).
5. **Analysis is thin vs. the stated ambition** ("financial analysis,
   valuation etc."): 5 ratios, keyword-substring normalization that can
   silently pick wrong figures (e.g. "trzby" matching one-off asset-sale
   revenue), trends limited to latest-vs-prior even when 5 years are
   fetched, and no valuation at all.
6. **Large PDFs are a real constraint, not an edge case.** Filed
   statements run to ~50 pages / 20–25 MB. Delivery of those PDFs to the
   host agent must work; a blunt embed cap is not acceptable
   (product owner decision, 2026-07-13).

## Stages

Each stage is independently shippable, gets its own design spec (linked)
and its own implementation plan via the writing-plans skill, and is sized
for roughly one working session.

| Stage | Spec | Goal | Ships as |
|---|---|---|---|
| A | `2026-07-13-stage-a-filings-fallback-design.md` | Filings work live again: legacy-portal fallback + endpoint canary | v0.4.1 |
| B | `2026-07-13-stage-b-test-hygiene-windows-ci-design.md` | Hermetic tests, Windows CI leg, README fact fixes | v0.4.2 |
| C | `2026-07-13-stage-c-mcp-apps-card-and-large-pdfs-design.md` | Card renders in Claude Desktop/claude.ai (MCP Apps); large-PDF delivery strategy | v0.5.0 |
| D | `2026-07-13-stage-d-analysis-depth-valuation-design.md` | Canonical extraction fields, more ratios, IN05, full trend series, indicative valuation | v0.6.0 |
| E | `2026-07-13-stage-e-distribution-demo-design.md` | Registry submission verified, demo media recorded, directory listings | v0.6.x |

## Order and rationale

**A before everything** — every demo, screenshot, and new feature is
worthless while the core loop 403s. **B second** — it's small, and every
later stage lands on a suite that must be trusted on the dev machine
(Windows). **C before D** — the card is the visible surface that D's
richer analysis will render into; building D's output model with C's
rendering in mind avoids reshaping twice. **E last** — distribution
pushes only after the claim is true and demonstrable.

If Stage A's live investigation finds the new portal reachable again (the
block may be tuned server-side at any time), Stage A shrinks to
"fallback + canary" and nothing else changes.

## Working agreement per session

1. Open the stage spec; run `writing-plans` skill to produce
   `docs/superpowers/plans/<date>-stage<X>-*.md`.
2. Execute with TDD per CLAUDE.md; offline, key-free tests.
3. `ruff check` + `ruff format --check` + `pytest -q` green **on Windows**
   (after Stage B, also in CI on both OSes) before commit.
4. Live verification via `scripts/smoke.py` before any release tag.
