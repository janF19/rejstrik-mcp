# Showcase hardening — design

Date: 2026-07-23
Status: proposed
Author: janf19

## Context

The project (v0.8.0, on PyPI) is functionally shipped and technically
strong: 269 offline tests, ruff-clean, CI on three OS/Python combos. It is
about to be shown publicly during job interviews. A review surfaced a small
set of issues that either look unprofessional to a reviewer or leave a
shipped feature in an unverified state. This spec collects the fixes so they
can be planned and executed as one focused pass.

None of these are defects in the core product. They are polish and honesty
items that raise the floor for a public showcase.

## Goals

- Remove repo contents that don't belong in a public showcase.
- Make one shipped-but-unverified feature (the MCP Apps card) either
  correct-by-spec or honestly caveated — no silent claims.
- Give the README a visual demo so a reviewer sees the tool work in seconds.
- Keep every quality gate green: `ruff check && ruff format --check &&
  pytest -q`.

## Non-goals

- No changes to the core analysis, registry, filings, or documents layers.
- No new tools or features beyond what already exists.
- No removal of the `docs/superpowers/` process trail — keeping it is a
  deliberate decision (it demonstrates process and AI-orchestration for
  interviews). Only `scripts/autopilot.py` is removed (see item 2).
- No attempt to make Claude render the interactive card — that is an
  upstream client bug outside this repo (see item 4).

## Work items

### 1. Remove the personal Mac script from the repo

`scripts/set_dell_main.sh` is a machine-specific utility (disables a broken
MacBook internal display via `displayplacer`) with no relation to the
project. It is currently untracked in the repo root's `scripts/`.

- Move it to `~/scripts/set_dell_main.sh` (outside the repo).
- Confirm afterwards that `git status` no longer lists it and the working
  tree is clean of it.

Risk: none. It is untracked, so this is a filesystem move only — nothing to
commit.

### 2. Remove `scripts/autopilot.py`

`scripts/autopilot.py` is an unattended agent pipeline ("Opus plans, Sonnet
executes in a worktree, the script verifies and merges"). For an authorship
story it undercuts the narrative, and it is not part of the shipped product.

- Verify nothing in `src/` or `tests/` imports it (grep first).
- `git rm scripts/autopilot.py`.
- Leave `docs/superpowers/specs/2026-07-13-autopilot-design.md` in place; it
  is part of the process trail being kept. Add a one-line note at the top of
  that design doc marking the script as removed, so the doc doesn't dangle.

Risk: the design doc references a script that no longer exists — mitigated by
the note above.

### 3. Fix the stale User-Agent version

`src/rejstrik/core/http.py:5` hardcodes `rejstrik-mcp/0.4` while the package
is at `0.8.0`. Every other version string (`__init__`, `server.json`,
`mcpb/manifest.json`) is correct; this one drifted.

- Derive the UA from the single source of truth so it can never drift again:

  ```python
  from rejstrik import __version__
  USER_AGENT = f"rejstrik-mcp/{__version__} (+https://github.com/janF19/rejstrik-mcp)"
  ```

- Guard against a circular import: `core/http.py` is a low-level module and
  `rejstrik/__init__.py` defines `__version__`. Importing the package root
  from a submodule is normally fine because `__init__` only assigns a string,
  but verify by running the test suite. If a cycle appears, fall back to
  reading the version via `importlib.metadata.version("rejstrik-mcp")`, and
  only if that is also unworkable, hardcode `0.8.0` with a comment pointing at
  the release checklist.

Testing: `tests/` may assert on the UA string or `0.4`. Grep and update any
such assertion to derive from `__version__` too, so the test can't pin a
stale value.

### 4. MCP Apps card — align to SEP-1865 and caveat honestly

Research (2026-07): MCP Apps is the official SEP-1865 extension
(Anthropic + OpenAI, 2026-01-26). Two facts drive this item:

1. **Claude does not render MCP Apps HTML cards yet.** Open, unresolved bug
   [ext-apps #671](https://github.com/modelcontextprotocol/ext-apps/issues/671)
   (May 2026): Claude Desktop and claude.ai negotiate the capability, fetch
   the resource via `resources/read`, then display
   `"[This tool call rendered an interactive widget…]"` instead of an iframe.
   Even a spec-perfect server shows nothing in Claude today.
2. **The current implementation is off-spec.** The finalized spec requires:
   - capability key `io.modelcontextprotocol/ui`
   - tool meta `_meta.ui.resourceUri`
   - resource mimetype `text/html;profile=mcp-app`

   The code (`src/rejstrik/mcp/server.py`) currently uses capability key
   `mcp-apps` (env-overridable), meta key `mcp/ui`, and emits `mcp-ui`'s
   `rawHtml` at mimetype `text/html`.

Decision: bring the wiring to spec so the feature is *correct*, keep the
markdown path as the guaranteed-rendering default, and document the upstream
gap plainly. This converts an unverified claim into a defensible "built to
SEP-1865; client rendering is a tracked upstream bug" position.

Changes in `src/rejstrik/mcp/server.py`:

- `_apps_capability` / `REJSTRIK_APPS_CAPABILITY_KEY` default:
  `mcp-apps` → `io.modelcontextprotocol/ui`.
- `_UI_META`: `{"mcp/ui": {"resourceUri": _UI_URI}}` →
  `{"ui": {"resourceUri": _UI_URI}}` so the emitted key path is
  `_meta.ui.resourceUri`.
- `@mcp.resource(_UI_URI, mime_type=...)`: `text/html` →
  `text/html;profile=mcp-app`.
- `_card_ui_resource`: investigate whether `mcp_ui_server.create_ui_resource`
  can emit the `text/html;profile=mcp-app` profile. If it cannot, hand-roll
  the `EmbeddedResource` (a `TextResourceContents`/blob with the correct
  `mimeType`) directly instead of going through `create_ui_resource`, so the
  emitted mimetype matches the spec. Keep `render_report_card` as the HTML
  source either way.

Investigation task (resolve during implementation, not assumed here):

- Confirm how `mcp>=1.2` FastMCP surfaces the negotiated
  `io.modelcontextprotocol/ui` capability. `_host_supports_apps` currently
  reads `ctx.session.client_params.capabilities.experimental`. The spec's
  capability may not live under `experimental` in this SDK version. Verify
  against the installed `mcp` package and adjust `_apps_capability` /
  `_host_supports_apps` to read wherever the SDK actually exposes it. If the
  SDK does not expose it at all, keep the env-override path and default to
  markdown.

Fallback: if spec-compliant emission is not cleanly achievable with the
pinned `mcp` / `mcp-ui-server` versions, do NOT ship a broken card — keep
markdown as the default and document the card as "implemented to SEP-1865,
pending SDK support" rather than claiming it works.

Documentation:

- `README.md`: where the report card is described, state that interactive
  rendering depends on host support for MCP Apps (SEP-1865) and link #671;
  make clear the default, always-working output is markdown.
- `docs/REMAINING.md`: replace the current "never verified in a live host"
  wording with the concrete status — spec-aligned server, client rendering
  blocked upstream by #671.

Testing:

- Update `tests/mcp/test_card*.py`, `test_annotations.py`, and any test
  asserting the capability key / meta key / mimetype to the new values.
- Add/adjust a test asserting the resource mimetype is
  `text/html;profile=mcp-app` and the tool meta carries `ui.resourceUri`.
- Markdown-fallback tests stay as-is (that path is unchanged and is the
  default).

### 5. README demo GIF

The README has only badges — no visual. `scripts/record_demo.sh` already
exists to record `rejstrik analyze "Budejovicky Budvar" --years 3` as an
asciinema cast and render a GIF.

Prerequisites (NOT currently installed — verified 2026-07-23):

- `asciinema` — `brew install asciinema`
- `agg` — `brew install agg` (or `cargo install --git
  https://github.com/asciinema/agg`)

Steps:

- Install the two tools.
- Run `scripts/record_demo.sh` from the repo root inside the venv. This runs
  the real CLI, which makes live network calls to ARES / Sbírka listin —
  ensure connectivity and that the run stays under ~15s.
- Commit `docs/media/budvar-3year.gif`. (`.gitignore` ignores `*.pdf`, not
  `*.gif`, so the asset commits cleanly.)
- Embed the GIF near the top of `README.md`, above or just under the badges.
- Sanity-check the file size; if the GIF is large (> ~2 MB), reduce cols/rows
  or trim the recording rather than committing a heavy binary.

Dead reference cleanup:

- `docs/REMAINING.md` references `docs/media/report-card.png` as "the last
  missing demo asset." Since the card does not render in Claude (item 4),
  do NOT try to produce that screenshot. Remove the reference instead.
- Confirm no other doc links a missing `report-card.png`.

## Verification (whole pass)

After each item and again at the end:

```bash
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
```

Additional manual checks:

- `git status` clean of `set_dell_main.sh` (item 1).
- `git grep autopilot` returns only the (annotated) design doc (item 2).
- The rendered GIF displays correctly in the GitHub README preview (item 5).

## Open questions / risks

- **Item 4 SDK behaviour** is the only real unknown: whether `mcp>=1.2`
  exposes the `io.modelcontextprotocol/ui` capability in a readable place,
  and whether `mcp-ui-server` can emit the `mcp-app` profile mimetype. The
  plan must treat these as investigation-then-decide, with the markdown
  default as the guaranteed-safe fallback. The feature must never regress the
  always-working markdown path.
- **Item 5 network dependency**: the demo records a live run; if the target
  company's data shifts, re-record. This is a one-time asset, acceptable.
```
