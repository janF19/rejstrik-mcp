# Stage E: Distribution & Demo — Make It Findable and Believable

**Date:** 2026-07-13
**Status:** Approved design, pending implementation plan
**Parent:** `2026-07-13-roadmap-overview.md`
**Ships as:** v0.6.x (no code-feature version bump required)

## Problem

The product claims are (post Stages A–D) true, but unproven on the repo
page and undiscoverable off it. `server.json` exists but submission to
the official MCP registry is unverified; `docs/media/` still holds only a
placeholder; nobody outside this repo knows the project exists.

## Design

### 1. Demo media (recorded against the real, fixed product)

- `budvar-3year.gif` — terminal recording of
  `rejstrik analyze "Budejovicky Budvar" --years 3`
  (asciinema → agg/gif). Keep under ~15 s and ~5 MB.
- `report-card.png` — screenshot of the Stage C card actually rendering
  in Claude Desktop (also serves as regression proof of the MCP Apps
  migration).
- Restore the README "See it work" section with these files committed.

### 2. Official MCP registry

- Verify whether `io.github.janf19/rejstrik-mcp` is actually published in
  the official registry (`registry.modelcontextprotocol.io`); if not, run
  the publisher flow with the existing `server.json`; bump `version`
  fields in `server.json` as part of the release checklist (add to the
  README "Releasing" section so it doesn't drift from pyproject again).

### 3. Directory + community listings (checklist, not code)

- mcpservers.org / mcp.so / Smithery / awesome-mcp-servers PR.
- One honest Czech-community post (root.cz forum, or X/LinkedIn thread):
  the "ministry portal now 403s automated clients; here's an open-source
  fallback" story is genuinely newsworthy locally and states the
  project's reason to exist.
- README top: add PyPI version badge next to CI badge.

### 4. Release hygiene item

`mcpb/manifest.json` and `server.json` versions join the release
checklist alongside `pyproject.toml` (three places currently must agree
by hand — the checklist prevents drift; scripting it is optional polish).

## Not in scope

- Hosted public HTTP instance (still deferred, as in the 2026-07-06 spec).
- Paid promotion, launch-week theatrics.

## Acceptance

Registry entry resolves; README renders both media files; at least three
external directories list the server; release checklist updated.
