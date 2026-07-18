# Final Release v0.7.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship rejstrik-mcp v0.7.1 end-to-end and finish the project: make the live smoke fully keyless, close the Stage E/F leftovers the agent can close, and hand the human a tight sequence of gated release steps (tag → PyPI → registry → listings).

**Architecture:** No product behavior changes. This is a release-hardening pass. The only source edit is to `scripts/smoke.py` (remove the key-gated step); the optional in-server LLM extraction feature stays fully intact in `src/`. Everything else is docs, CI hygiene, and human-gated publish actions.

**Tech Stack:** Python 3.11+, pytest (offline, key-free), ruff. No new dependencies.

**Design spec:** `docs/superpowers/specs/2026-07-17-final-release-v0.7.1.md`

## Global Constraints

- Tests are offline and key-free; mock the LLM via the `DocumentLLM` protocol and registry checks via the `*_check` injection points (CLAUDE.md).
- Before every commit run: `.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q` — all green. (If `ruff format --check` complains, run `.venv/bin/ruff format src/ tests/` and re-check.)
- Use the repo virtualenv at `.venv/` (already created). All tool invocations go through `.venv/bin/…`.
- **The optional server-side LLM extraction feature STAYS.** Do not touch `src/rejstrik/documents/*`, `service.py` extraction paths, `mcp/server.py` tool logic, or the CLI. Only `scripts/smoke.py` changes in `src`-adjacent code.
- Commit messages end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **[HUMAN GATE]** tasks (7, 8, 9, 10, and the live checks in 3/6) are NOT executed by the agent. The agent prepares artifacts and STOPS, reporting what the human must do. Never `git push`, tag, or publish to any external service without an explicit "go".
- Starting state: `main` clean at 0.7.1 in all four version locations; 301 tests green; no `v0.7.1` tag anywhere; PyPI at 0.7.0.

---

### Task 1: Make the live smoke fully keyless

`scripts/smoke.py` step `[5/5]` branches on `has_llm_key()` and only exercises the optional in-server extraction. Remove that branch so the smoke needs zero keys. The `if has_llm_key(): … else: …` block spans roughly lines 98–115.

**Files:**
- Modify: `scripts/smoke.py`

**Interfaces:**
- Produces: a smoke script whose only external dependency is network access to the live Czech registry — no API key path remains.

- [ ] **Step 1: Confirm what the key branch uses**

Run: `grep -n "has_llm_key\|analyze_company_financials\|trend_plausibility_issues" scripts/smoke.py`
Expected: hits in the imports block (lines ~11, ~16, and one more) and inside the `[5/5]` block only. Confirm none of these three names are used anywhere else in the file.

Run: `grep -rn "trend_plausibility_issues" src/ tests/`
Expected: hits in `src/` and/or `tests/` — this confirms the helper is still needed elsewhere and must NOT be deleted from the codebase, only unimported from smoke.py.

- [ ] **Step 2: Edit the smoke script**

In `scripts/smoke.py`:
- Delete the whole `if has_llm_key(): … else: …` block (the `[5/5]` section, including the `IMPLAUSIBLE` handling) and replace it with a single unconditional line:

```python
    print("[5/5] skipped in-server extraction (keyless smoke)")
```

- Remove the now-orphaned imports from the top of the file: `has_llm_key` (from `rejstrik.documents.config`), and `analyze_company_financials` + `trend_plausibility_issues` if they are no longer referenced. Keep `analyze_statements` and `fetch_filing` — they are still used by steps 1–4.

- [ ] **Step 3: Prove it parses and lints clean**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/smoke.py').read())"`
Expected: no output (parses).
Run: `.venv/bin/ruff check scripts/ src/ tests/`
Expected: `All checks passed!` — this is also the guard that catches any import you forgot to remove.

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke.py
git commit -m "refactor(smoke): make live smoke fully keyless; drop in-server extraction step

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Full offline gate (regression guard)

Confirm Task 1 broke nothing.

- [ ] **Step 1: Run the gate**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q`
Expected: `All checks passed!`, `… files already formatted`, and `301 passed` (±0 — Task 1 touches no tests).
If red, fix before continuing. Do not proceed on failure.

---

### Task 3: Refresh the `_UI_META` capability-key note (headless portion)

`src/rejstrik/mcp/server.py:67` carries a stale `VERIFY` comment about the MCP Apps capability key. The runtime override is `REJSTRIK_APPS_CAPABILITY_KEY` (line ~76). The live confirmation is deferred to Task 7; here we only make the code comment honest.

**Files:**
- Modify: `src/rejstrik/mcp/server.py` (comment only)

- [ ] **Step 1: Trace the override**

Run: `sed -n '60,80p' src/rejstrik/mcp/server.py`
Confirm: `_UI_META = {"mcp/ui": {"resourceUri": _UI_URI}}` and that `REJSTRIK_APPS_CAPABILITY_KEY` (default `"mcp-apps"`) actually flows into where the meta/capability is declared. If the override does NOT reach the meta dict, that is a real bug — STOP and report it rather than editing the comment.

- [ ] **Step 2: Update the comment**

If the path is sound, change the `VERIFY` warning comment to note the key is overridable at runtime via `REJSTRIK_APPS_CAPABILITY_KEY` and was last reviewed 2026-07-17. Do NOT change the default key value — that requires the live evidence from Task 7.

- [ ] **Step 3: Gate + commit (only if the comment changed)**

Run the full gate (Task 2 Step 1). Then:
```bash
git add src/rejstrik/mcp/server.py
git commit -m "docs(mcp): note _UI_META key reviewed 2026-07-17; overridable via env

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**[HUMAN GATE]:** live card render + real negotiated-key check happens in Task 7.

---

### Task 4: Live keyless smoke run [network required]

The end-to-end proof the product's central claim holds today, with no key.

- [ ] **Step 1: Run it**

Run: `.venv/bin/python scripts/smoke.py`
Expected: steps `[1/5]`…`[5/5]` print, ending in `SMOKE OK`, hitting the real ARES + filings portal.

- [ ] **Step 2: Triage failure**

If it 403s or fails on the filings portal, STOP and report — this is the Stage A failure mode and a hard release blocker. Do not tag around it. If it prints `SMOKE OK`, record that in the release checklist (Task 7).

---

### Task 5: Demo media + honest README refs (Stage E leftover)

`docs/media/` holds only a placeholder `README.md`; the main README's "See it work" section references media that doesn't exist.

**Files:**
- Add: capture file(s) under `docs/media/`
- Modify: `README.md`, and possibly `docs/media/README.md`

- [ ] **Step 1: Learn the intended media**

Run: `cat docs/media/README.md` and `grep -n "See it work\|\.gif\|\.png\|docs/media" README.md`
Note the intended filenames/format so new media slots in cleanly.

- [ ] **Step 2: Produce what's possible headlessly**

Capture the keyless CLI flow — the `rejstrik-mcp` CLI querying a real Czech company — as a terminal transcript or SVG cast (use `asciinema`/`svg-term` only if already available; otherwise a plain captured text transcript saved under `docs/media/`). A live Claude Desktop card GIF CANNOT be produced headlessly — leave a clearly-labelled placeholder slot for the human (Task 7).

- [ ] **Step 3: Fix the README**

Update "See it work" to reference only media that now actually exists; remove or soften any dead reference. No broken links.

- [ ] **Step 4: Gate + commit**

Run the full gate. Then:
```bash
git add README.md docs/media/
git commit -m "docs(media): add keyless CLI demo capture; fix See-it-work references

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Canary CI failure surfacing (Stage F leftover)

**Files:**
- Read (maybe modify): `.github/workflows/canary.yml`

- [ ] **Step 1: Determine current behavior**

Run: `cat .github/workflows/canary.yml`
Decide: does it already open/update a GitHub issue on failure (the G4 behavior)?

- [ ] **Step 2a: If it already opens an issue**

Add/confirm a one-line header comment in `canary.yml` documenting that failures surface as an auto-opened tracking issue; no functional change needed.

- [ ] **Step 2b: If it does NOT**

Add a minimal failure step that opens/updates a tracking issue, mirroring whatever pattern G4 established elsewhere in the repo. If that pattern doesn't exist, instead document the exact GitHub-settings click-path for the human to enable Actions failure notifications (this becomes a [HUMAN GATE] line in the checklist).

- [ ] **Step 3: Commit (only if the workflow changed)**

```bash
git add .github/workflows/canary.yml
git commit -m "ci(canary): ensure failures surface as a tracking issue

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Prepare the human release checklist + build the artifact

The agent builds the distributable and writes copy-paste steps; the human runs them. This unblocks Tasks 8–10.

**Files:**
- Add: `docs/RELEASE-CHECKLIST.md`
- Produces: `dist/rejstrik_mcp-0.7.1-*.whl` (+ sdist) for local install testing

- [ ] **Step 1: Build the wheel locally**

Run: `.venv/bin/pip install -q build && .venv/bin/python -m build`
Expected: `dist/rejstrik_mcp-0.7.1-py3-none-any.whl` and the `.tar.gz` sdist appear. (This is a local sanity build; the real publish build runs in `release.yml`.)

- [ ] **Step 2: Write `docs/RELEASE-CHECKLIST.md`**

Include, as numbered copy-paste steps for the human:
1. Clean-venv install: `pip install dist/rejstrik_mcp-0.7.1-*.whl` then run `rejstrik-mcp` (stdio) and confirm it starts.
2. Register in Claude Desktop / Claude Code as an MCP server; confirm the tool list loads.
3. Run a real keyless query on a known Czech company; confirm filings + analysis return AND the card renders.
4. Note the negotiated `_UI_META` capability key; if it differs from `mcp-apps`, record the `REJSTRIK_APPS_CAPABILITY_KEY` value to set.
5. The tag/PyPI/registry/listings gates (Tasks 8–10), verbatim.

- [ ] **Step 3: Commit**

```bash
git add docs/RELEASE-CHECKLIST.md
git commit -m "docs: add v0.7.1 release checklist for manual install + publish

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: [HUMAN GATE] — Jan runs the manual install + MCP test**

Human performs checklist steps 1–4 and reports "install + card OK" (and any differing capability key). Agent STOPS here until that confirmation.

---

### Task 8: [HUMAN GATE] Tag and release v0.7.1

**Only after Task 4 printed `SMOKE OK`, Task 7 reported "install + card OK", and Jan says go.**

- [ ] **Step 1: Push main and the tag**

```bash
git push origin main
git tag v0.7.1
git push origin v0.7.1
```

- [ ] **Step 2: Watch `release.yml`**

The tag push triggers `.github/workflows/release.yml`: build → **PyPI publish (irreversible)** → `.mcpb` pack → GitHub release with artifacts. Watch the Actions run to green before declaring the release done. If PyPI publish fails, do NOT retry with the same version — diagnose first.

- [ ] **Step 3: Verify PyPI**

Confirm `pip index versions rejstrik-mcp` (or the PyPI page) shows `0.7.1`.

---

### Task 9: [HUMAN GATE] Publish the MCP registry entry

**Only after Task 8 succeeds** — the entry references the published PyPI version.

- [ ] **Step 1: Agent verifies server.json**

Run: `grep -n "version\|identifier" server.json`
Confirm top-level `version`, `packages[0].version` = `0.7.1`, and `packages[0].identifier` = `rejstrik-mcp`. Report any mismatch and STOP if found.

- [ ] **Step 2: [HUMAN GATE] Human publishes**

Human publishes `io.github.janf19/rejstrik-mcp` via the MCP publisher CLI / registry flow using the updated `server.json`. Registry auth is a human credential step — the agent must not attempt it.

---

### Task 10: [HUMAN GATE] Draft directory/community listings (Stage E T4–T6)

**Only after Tasks 8–9 are live.**

**Files:**
- Add: `docs/listings.md`

- [ ] **Step 1: Agent drafts listing copy**

Write `docs/listings.md` with ready-to-paste text: name, one-liner, keyless install command (`pip install rejstrik-mcp` / `.mcpb`), repo + PyPI + registry links, and a short feature blurb. Commit it.

```bash
git add docs/listings.md
git commit -m "docs: draft community directory listing copy

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 2: [HUMAN GATE] Human submits**

Jan submits to the external directories (account/auth-gated). Agent's job ends at producing the paste-ready copy.

---

## Definition of done

- [ ] Task 1–2: smoke keyless, gate green (301 passed)
- [ ] Task 3: `_UI_META` note refreshed (or bug reported)
- [ ] Task 4: live `SMOKE OK` with no key
- [ ] Task 5: demo media exists, README refs honest
- [ ] Task 6: canary failures surface for a human
- [ ] Task 7: artifact built, checklist written, manual install confirmed
- [ ] Task 8: `v0.7.1` tagged, `release.yml` green, PyPI at 0.7.1
- [ ] Task 9: registry entry published at 0.7.1
- [ ] Task 10: listing copy drafted (+ human-submitted)

When all boxes are checked, the project is done.

## Execution order note

Tasks 1–7 (Step 1–3) are agent-headless and can run in one session. Task 7 Step 4 onward is a hard human gate — the agent completes everything up to it, then stops and reports the checklist. Tasks 8–10 resume only on Jan's explicit go, one gate at a time.
