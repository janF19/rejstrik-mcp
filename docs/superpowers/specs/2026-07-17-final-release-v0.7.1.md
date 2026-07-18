# Final Release Spec — v0.7.1 "Ship It"

**Date:** 2026-07-17
**Owner:** janF19 (human) + implementing agent
**Goal:** Get rejstrik-mcp fully released and verified end-to-end, then
call the project done. This is the last spec.

## Decisions locked in (do not re-litigate)

1. **Keyless smoke.** The optional server-side LLM extraction feature
   STAYS in the code (it is the documented differentiator). We only remove
   the key-dependent *step* from the live smoke so the smoke is 100%
   key-free. Do NOT touch `src/rejstrik/documents/*`, `service.py`,
   `mcp/server.py`, or the CLI extraction paths.
2. **Leftovers are in scope** (demo media, directory listings, live
   `_UI_META` check, CI notifications) — but several require the human.
   The agent does everything it can headlessly and STOPS with a clear
   checklist for the parts only a human can do.

## Global constraints

- TDD per `CLAUDE.md`. Offline, key-free tests.
- Gate before every commit:
  `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
- Use the repo virtualenv at `.venv/` (already created; `.venv/bin/…`).
- Do NOT `git push`, tag, or publish to any external service without the
  explicit human go-ahead marked **[HUMAN GATE]** below.
- Current state: `main` is clean at 0.7.1 in all four version locations;
  301 tests green; no `v0.7.1` tag exists locally or on GitHub; PyPI is at
  0.7.0.

---

## Task 1 — Make the live smoke fully keyless

**Why:** This is an MCP server; the core loop must be provable with zero
keys. Step 5 of `scripts/smoke.py` currently branches on `has_llm_key()`
and only exercises the optional in-server extraction. Remove that branch.

**Steps:**
1. Edit `scripts/smoke.py`:
   - Delete the entire `if has_llm_key(): … else: …` block (the `[5/5]`
     section) and replace it with a single unconditional line, e.g.
     `print("[5/5] skipped in-server extraction (keyless smoke)")` — or
     renumber steps to `[4/4]` if you prefer; either is fine, keep it
     honest.
   - Remove now-unused imports: `has_llm_key`,
     `analyze_company_financials`, and `trend_plausibility_issues` (verify
     each is truly unused after the edit before deleting).
2. Run the gate: `ruff check` must pass (it will fail on unused imports if
   you missed one — that's the check working).
3. Run the smoke offline-safe check: at minimum
   `.venv/bin/python -c "import ast; ast.parse(open('scripts/smoke.py').read())"`
   to confirm it parses. Full live run happens in Task 4.
4. Commit:
   `refactor(smoke): make live smoke fully keyless; drop in-server extraction step`

**Note:** Keep `trend_plausibility_issues` in `src/` — it is still used by
the analysis code and tests. You are only removing its *use in smoke.py*.
Double-check with `grep -rn trend_plausibility_issues src/ tests/` before
assuming anything.

---

## Task 2 — Full offline gate (regression guard)

Run and confirm all green:
```
.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
```
Expected: `301 passed` (or 301±small if Task 1 added/removed a test).
If anything fails, fix before proceeding. Do not continue on red.

---

## Task 3 — Verify `_UI_META` capability key (headless portion)

**Why:** `src/rejstrik/mcp/server.py:67` carries a `VERIFY` note that the
MCP Apps capability key (`mcp/ui`) may differ from what the current spec
negotiates. The runtime override is `REJSTRIK_APPS_CAPABILITY_KEY`.

**Agent does (headless):**
1. Re-read `server.py:60-80` and confirm the `_UI_META` shape and the
   `REJSTRIK_APPS_CAPABILITY_KEY` env override still match the current
   code. Confirm the override actually flows into the meta dict (trace it).
2. If the code path is sound, update the comment from a `VERIFY` warning to
   a note that the key is overridable at runtime and was last reviewed
   2026-07-17. Do NOT change the default key value without evidence.
3. Commit if the comment changed:
   `docs(mcp): note _UI_META key reviewed; overridable via env`

**[HUMAN GATE] — live check (only you can do this):** In a real Claude
Desktop / claude.ai session, install the server, call `analyze_company`,
and confirm the card renders. If the negotiated key differs, set
`REJSTRIK_APPS_CAPABILITY_KEY` accordingly. This is covered by Task 7's
manual install test — fold it in there.

---

## Task 4 — Live smoke run [network required, no key]

Run: `.venv/bin/python scripts/smoke.py`

Expected: steps 1–5 print, ending in `SMOKE OK`. This proves the live core
loop against the real Czech registry (ARES + filings portal) with zero
keys — the end-to-end proof the product's central claim is true today.

If it 403s or fails on the filings portal, STOP and report — that is a
release blocker (the Stage A failure mode), not something to tag around.

---

## Task 5 — Demo media (Stage E leftover)

**Why:** `docs/media/` holds only `README.md` (a placeholder). The main
README's "See it work" section references media that doesn't exist.

**Agent does (headless):**
1. Read `docs/media/README.md` and the README section that references
   media to learn the intended filenames/format.
2. Produce what CAN be produced headlessly: a terminal transcript /
   asciinema-style capture of the keyless CLI flow
   (`rejstrik-mcp` CLI querying a real company), saved under `docs/media/`
   as text or an SVG cast if tooling is available. A real animated GIF of
   Claude Desktop rendering the card CANNOT be produced headlessly.
3. Update the README "See it work" section to reference whatever media now
   actually exists, and remove/soften any reference to media that still
   doesn't. No dead links.
4. Commit: `docs(media): add keyless CLI demo capture; fix See-it-work refs`

**[HUMAN GATE]:** Record the Claude Desktop card GIF during Task 7 if you
want it in the README; agent will leave a clearly-marked placeholder slot.

---

## Task 6 — CI failure notifications (canary)

**Why:** `canary.yml` exists; Stage F left "turn on failure notifications"
open. G4 may already auto-open a tracking issue.

**Agent does (headless):**
1. Read `.github/workflows/canary.yml`. Determine whether it already opens
   / updates a GitHub issue on failure (the G4 behavior).
2. If it does: document that in the workflow header comment and in the spec
   — nothing more is needed; native GitHub issue notifications cover it.
3. If it does NOT: add a minimal failure step that opens/updates a tracking
   issue (mirror whatever pattern G4 established), OR document the exact
   click-path for the human to enable Actions email notifications.
4. Commit if changed: `ci(canary): ensure failure surfaces as a tracking issue`

**[HUMAN GATE]:** Any repo-settings-level notification toggle (email/Slack)
is the human's to click in GitHub settings; agent documents the path.

---

## Task 7 — [HUMAN GATE] Manual install + MCP test in Claude

**This is yours, Jan — the agent prepares, you execute.**

The agent writes a short `RELEASE-CHECKLIST.md` (scratch is fine, or in
docs/) with copy-paste steps for you:

1. **Local install from the built artifact** (pre-PyPI sanity):
   `pip install dist/rejstrik_mcp-0.7.1-*.whl` in a clean venv, then run
   `rejstrik-mcp` (stdio) and confirm it starts.
2. **Register in Claude Desktop / Claude Code** as an MCP server and
   confirm the tools list loads.
3. **Run a real query** (e.g. a known Czech company) keyless and confirm
   filings + analysis come back, and the card renders (Task 3 live check).
4. Note the negotiated `_UI_META` key if it differs from `mcp-apps`.

You report back "install + card OK" before we tag.

---

## Task 8 — [HUMAN GATE] Tag and release v0.7.1

**Only after Task 4 (SMOKE OK) and Task 7 (install OK) both pass, and you
say go.**

```
git push origin main
git tag v0.7.1
git push origin v0.7.1
```
Pushing the tag triggers `.github/workflows/release.yml`:
- builds the wheel/sdist, publishes to **PyPI** (irreversible — a version
  can't be re-uploaded),
- packs the `.mcpb` bundle,
- creates the GitHub release with artifacts.

Watch the Actions run to green before declaring release done.

---

## Task 9 — [HUMAN GATE] Publish the MCP registry entry

**Why:** `io.github.janf19/rejstrik-mcp` is unpublished. `server.json` is
already at 0.7.1 and points at the PyPI package.

**Do this only after Task 8 succeeds** (the registry entry references the
published PyPI version):
1. Agent verifies `server.json` version/identifier match the just-released
   PyPI package (0.7.1). Report any mismatch.
2. Human publishes via the MCP publisher CLI / registry flow using the
   updated `server.json`. (Auth to the registry is a human credential step
   — agent must not attempt it.)

---

## Task 10 — Directory / community listings (Stage E T4–T6)

**[HUMAN GATE], agent-assisted:** Agent drafts the listing text (name,
one-liner, install command, links) once PyPI + registry are live. Human
submits to the external directories — those are account/auth-gated and
must be done by you. Agent produces a ready-to-paste `docs/listings.md`.

---

## Definition of done

- [ ] Smoke is keyless and prints `SMOKE OK` on a live run (Task 4)
- [ ] `ruff` + `pytest` green (Task 2)
- [ ] `_UI_META` reviewed; live card render confirmed (Task 3 + 7)
- [ ] Demo media exists and README refs are honest (Task 5)
- [ ] Canary failures surface somewhere a human will see (Task 6)
- [ ] Manual install + MCP test in Claude passed (Task 7)
- [ ] `v0.7.1` tagged, `release.yml` green, PyPI shows 0.7.1 (Task 8)
- [ ] MCP registry entry published at 0.7.1 (Task 9)
- [ ] Listing text drafted for the human to submit (Task 10)

When all boxes are checked: the project is done. Call it a day.

## Human-only steps, collected (nothing else blocks these)

- Tag push / PyPI publish (Task 8) — irreversible, needs your "go"
- MCP registry publish auth (Task 9)
- External directory submissions (Task 10)
- Live Claude Desktop card render + `_UI_META` key confirmation (Task 7)
- Any GitHub repo-settings notification toggle (Task 6)
