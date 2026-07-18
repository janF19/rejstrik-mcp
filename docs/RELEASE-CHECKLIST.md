# v0.8.0 Release Checklist (for Jan)

This is the human-side checklist for shipping v0.8.0 — the first published
release (v0.7.1 was never tagged/pushed). The agent has already built the
local sanity artifacts in `dist/` (not committed — `dist/` is gitignored).
Work through the steps below in order; each has a HUMAN GATE unless noted
otherwise.

---

## 1. Clean-venv install smoke test

```bash
python3 -m venv /tmp/rejstrik-release-check
source /tmp/rejstrik-release-check/bin/activate
pip install dist/rejstrik_mcp-0.8.0-*.whl
rejstrik-mcp
```

Expected: the server starts on stdio and blocks waiting for MCP input (no
traceback). Ctrl-C to stop, then `deactivate` when done.

---

## 2. Register with Claude Desktop / Claude Code

Add an MCP server entry pointing at the venv's `rejstrik-mcp` executable,
e.g. in Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rejstrik": {
      "command": "/tmp/rejstrik-release-check/bin/rejstrik-mcp"
    }
  }
}
```

Restart the client and confirm the tool list loads — exactly 13 tools,
including `find_company`, `list_filings`, `get_filing`,
`analyze_financials`, `render_card`, etc. No key-gated tools remain.

---

## 3. Run a real keyless query, end to end

Run a keyless lookup + filings query against a known Czech company, e.g.
via the CLI:

```bash
rejstrik find "Budějovický Budvar"
rejstrik filings <ICO-from-above> --financial-only
```

Confirm both return real data with no API key set — the CLI is entirely
data-only now (no `extract`/`analyze` subcommands to worry about).

To validate the full card verification flow, drive it through the MCP
server in Claude Desktop/Code (registered per step 2):

1. `get_filing` — fetch the filed statement PDF for the company.
2. Agent extraction — the calling agent (Claude itself) reads the PDF and
   produces the structured `FinancialStatement` figures. No server-side
   key involved anywhere in this step.
3. `analyze_financials` — pass the extracted figures in; confirm ratios,
   red flags, and year-over-year trends come back.
4. `render_card` — pass the report in; confirm it renders as an
   interactive HTML card (MCP Apps hosts) or a markdown summary
   (text-only hosts like Claude Code).

---

## 4. Note the negotiated `_UI_META` / apps capability key

`src/rejstrik/mcp/server.py` gates the report-card UI resource on an
experimental capability flag the host must advertise. Default key is
`"mcp-apps"` (see `_apps_capability` in `server.py`).

If your Claude Desktop/Code build negotiates a different experimental
capability key for MCP Apps/UI support, set:

```bash
export REJSTRIK_APPS_CAPABILITY_KEY="<the-key-your-host-actually-sends>"
```

before launching `rejstrik-mcp`, and record here what value you used, so
it can be documented for other users:

- Capability key used: `______________________`

---

## 5. Also pending: manual media capture

One demo asset in `docs/media/` is still pending a human capture:

- `report-card.png` — manual screenshot of `render_card`'s output
  rendered in Claude Desktop (also serves as MCP Apps regression proof).
  Capture this while doing step 3 above.

The keyless CLI transcript (`cli-demo.txt`) is already captured and
present; see `docs/media/README.md`.

---

## 6. Tag, publish, and register (Tasks 8–10 of the release plan) — verbatim

**Only proceed once steps 1–4 above report "install + card OK".**

### Task 8: Tag and release v0.8.0

Only after the smoke script printed `SMOKE OK` and you're ready to go:

```bash
git push origin main
git tag v0.8.0
git push origin v0.8.0
```

Watch `.github/workflows/release.yml` — the tag push triggers it: build →
**PyPI publish (irreversible)** → `.mcpb` pack → GitHub release with
artifacts. Watch the Actions run to green before declaring the release
done. If PyPI publish fails, do NOT retry with the same version —
diagnose first.

Then verify PyPI:

```bash
pip index versions rejstrik-mcp
```

Confirm it shows `0.8.0` (or check the PyPI project page directly).

### Task 9: Publish the MCP registry entry

Only after Task 8 succeeds — the entry references the published PyPI
version.

1. Agent-verifiable: `grep -n "version\|identifier" server.json` should
   show top-level `version`, `packages[0].version` = `0.8.0`, and
   `packages[0].identifier` = `rejstrik-mcp`.
2. Human step: publish `io.github.janf19/rejstrik-mcp` via the MCP
   publisher CLI / registry flow using the updated `server.json`.
   Registry auth is a human credential step — the agent will not attempt
   it.

### Task 10: Draft directory/community listings

Only after Tasks 8–9 are live. `docs/listings.md` (ready-to-paste name,
one-liner, install command, links, feature blurb) is drafted separately
by the agent as its own task — once it exists, submit the copy to the
external directories yourself (account/auth-gated, so this step is
manual regardless).

---

## Definition of done

All of the above complete: clean install verified, MCP registration
verified, keyless `find`/`filings` and the full
`get_filing → agent extraction → analyze_financials → render_card` card
flow verified, capability key noted, the report-card screenshot
captured, tag pushed, PyPI live, registry entry published, and listings
submitted.
