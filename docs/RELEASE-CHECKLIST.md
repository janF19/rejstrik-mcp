# v0.7.1 Release Checklist (for Jan)

This is the human-side checklist for shipping v0.7.1. The agent has already
built the local sanity artifacts in `dist/` (not committed — `dist/` is
gitignored). Work through the steps below in order; each has a HUMAN GATE
unless noted otherwise.

---

## 1. Clean-venv install smoke test

```bash
python3 -m venv /tmp/rejstrik-release-check
source /tmp/rejstrik-release-check/bin/activate
pip install dist/rejstrik_mcp-0.7.1-*.whl
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

Restart the client and confirm the tool list loads (you should see tools
such as `find_company`, `list_filings`, `get_filing`, `analyze_financials`,
`analyze_company_financials`, `analyze_company_card`, etc.).

---

## 3. Run a real keyless query — with an important caveat

Run a keyless lookup + filings query against a known Czech company, e.g.
via the CLI:

```bash
rejstrik find "Budějovický Budvar"
rejstrik filings <ICO-from-above> --financial-only
```

Confirm both return real data with no API key set. **These two commands
(`find` and `filings`) are the only genuinely keyless CLI paths.**

Caveat discovered during Task 5 of this release: the CLI's `analyze`
subcommand is **not** keyless — it calls `extract_financials`, which goes
through `Anthropic messages.parse` server-side, so it will prompt for (or
fail without) an API key. This is also true of the MCP tools
`analyze_company_financials` and `analyze_company_card` — both call
`_require_llm_key()` (see `src/rejstrik/mcp/server.py`) and need a
server-side key. Don't be surprised when any of these ask for a key —
that is expected, not a regression.

The genuinely keyless path — matching the "agent reads the PDF itself"
model from `CLAUDE.md` — is the `get_filing` + `analyze_financials` tool
pair (`analyze_financials` is the "Analyze extracted financials" tool,
`src/rejstrik/mcp/server.py` around line 392): the calling agent fetches
the filed PDF via `get_filing`, extracts the statement itself, and passes
the structured data to `analyze_financials` for ratios/trends — no
server-side key involved. To validate this and the card rendering:

1. In Claude Desktop/Code (registered per step 2), ask it to look up the
   same company, fetch its filing via `get_filing`, and analyze it via
   `analyze_financials` (not `analyze_company_card`/`analyze_company_financials`,
   which require a key).
2. Confirm the model is able to read the filed PDF itself (no server-side
   key needed) and that filings + analysis come back.
3. To exercise the report card UI specifically, you will need a
   server-side key set and call `analyze_company_card` — the card only
   renders through that keyed tool. Confirm it renders (see capability
   note below — if the host doesn't advertise the experimental capability
   under the expected key, the card silently won't render and you'll only
   get plain tool output).

---

## 4. Note the negotiated `_UI_META` / apps capability key

`src/rejstrik/mcp/server.py` gates the report-card UI resource on an
experimental capability flag the host must advertise. Default key is
`"mcp-apps"` (see `_apps_capability` in `server.py`, around line 74).

If your Claude Desktop/Code build negotiates a different experimental
capability key for MCP Apps/UI support, set:

```bash
export REJSTRIK_APPS_CAPABILITY_KEY="<the-key-your-host-actually-sends>"
```

before launching `rejstrik-mcp`, and record here what value you used, so
it can be documented for other users:

- Capability key used: `______________________`

---

## 5. Also pending: manual media captures (from Task 5 / `docs/media/README.md`)

Two demo assets in `docs/media/` are still marked "STILL MISSING — human
capture pending":

- `budvar-3year.gif` — asciinema→agg recording of
  `rejstrik analyze "Budejovicky Budvar" --years 3`. This **requires an
  API key** (see the `analyze` caveat in step 3 above). Generate with
  `scripts/record_demo.sh`, keep it under 15s and 5MB.
- `report-card.png` — manual screenshot of `analyze_company_card`
  rendered in Claude Desktop. Capture this while doing step 3 above (it
  doubles as your MCP Apps regression proof).

Both are blocking the README's "See it work" section from being fully
populated; there's no agent-side way to produce them (live LLM key /
live screenshot).

---

## 6. Tag, publish, and register (Tasks 8–10 of the release plan) — verbatim

**Only proceed once steps 1–4 above report "install + card OK".**

### Task 8: Tag and release v0.7.1

Only after the smoke script printed `SMOKE OK` and you're ready to go:

```bash
git push origin main
git tag v0.7.1
git push origin v0.7.1
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

Confirm it shows `0.7.1` (or check the PyPI project page directly).

### Task 9: Publish the MCP registry entry

Only after Task 8 succeeds — the entry references the published PyPI
version.

1. Agent-verifiable: `grep -n "version\|identifier" server.json` should
   show top-level `version`, `packages[0].version` = `0.7.1`, and
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
verified, keyless `find`/`filings` + MCP-tool-level `analyze_company_card`
verified (with the `analyze` CLI caveat understood), capability key noted,
media captures recorded, tag pushed, PyPI live, registry entry published,
and listings submitted.
