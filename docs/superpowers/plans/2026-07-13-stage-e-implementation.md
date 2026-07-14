# Stage E: Distribution & Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the (now-true) product claims provable on the repo page and discoverable off it — synced version metadata, a drift-guard test, restored demo media, README badges/section, and a verified registry + directory presence.

**Architecture:** Two classes of task. **AGENT tasks** (T1–T3) are in-repo changes an automated worker can write and verify: a version-sync test + metadata fix, README badge/checklist edits, and the demo-recording script + README scaffold. **HUMAN tasks** (T4–T6) require a GUI, real accounts, or credentials — recording terminal/desktop media, publishing to the MCP registry, and submitting directory/community listings — and are written as explicit checklists, not code.

**Tech Stack:** Python 3.11+ (`tomllib`, `json`), pytest, Markdown, asciinema + agg (demo GIF), shields.io badges, the official MCP registry publisher flow with the existing `server.json`.

## Global Constraints

- **Ships as:** v0.6.x — no code-feature version bump required beyond metadata sync. (spec §header)
- **Honesty:** all media must be recorded against the real, fixed product; no mockups. (spec §1)
- **Three version files must agree:** `pyproject.toml`, `server.json` (two fields), `mcpb/manifest.json`. Currently `pyproject.toml` = `0.6.0`, the other two = `0.4.0` — real drift to close. (spec §2, §4)
- **No new runtime dependencies.** asciinema/agg are local tooling, never added to `pyproject.toml`.
- Every AGENT task ends with `.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q` green before commit.

---

### Task 1: Version-drift guard test + metadata sync (AGENT)

Closes the spec's release-hygiene item by making version drift a **test failure** instead of a manual checklist a human forgets. The test is written first and must fail against the current `0.4.0` metadata, then the metadata is bumped to match `pyproject.toml`.

**Files:**
- Test: `tests/test_version_sync.py` (create)
- Modify: `server.json:5` and `server.json:10` (`0.4.0` → `0.6.0`)
- Modify: `mcpb/manifest.json:5` (`0.4.0` → `0.6.0`)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_version_sync.py` — a guard later releases rely on; no importable symbols.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_version_sync.py
"""All version-bearing metadata must agree with pyproject.toml.

Prevents the server.json / manifest.json drift the Stage E spec calls out
(three places currently must agree by hand).
"""
import json
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_server_json_matches_pyproject() -> None:
    version = _pyproject_version()
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == version
    assert server["packages"][0]["version"] == version


def test_manifest_json_matches_pyproject() -> None:
    version = _pyproject_version()
    manifest = json.loads(
        (ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == version
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_version_sync.py -v`
Expected: FAIL — both assertions report `'0.4.0' == '0.6.0'` mismatch.

- [ ] **Step 3: Sync the metadata**

In `server.json`, change both `"version": "0.4.0"` occurrences (top-level line 5 and the `packages[0]` line 10) to `"version": "0.6.0"`.
In `mcpb/manifest.json`, change `"version": "0.4.0"` (line 5) to `"version": "0.6.0"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_version_sync.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Full verify + commit**

```bash
.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/python -m pytest -q
git add tests/test_version_sync.py server.json mcpb/manifest.json
git commit -m "test: guard version drift across pyproject/server.json/manifest"
```

---

### Task 2: PyPI badge + release checklist (AGENT)

Adds the discoverability badge and turns the three-file version rule into a written checklist step so it doesn't drift again (the test in T1 enforces it; the checklist documents it for humans cutting a release).

**Files:**
- Modify: `README.md:3` (add badge next to CI badge)
- Modify: `README.md:157-162` (the `## Releasing` section)

**Interfaces:**
- Consumes: `tests/test_version_sync.py` from Task 1 (referenced by the checklist).
- Produces: nothing importable.

- [ ] **Step 1: Add the PyPI badge**

Replace `README.md` line 3 (the lone CI badge line) with the CI badge followed by a PyPI version badge on the same line:

```markdown
[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/)
```

- [ ] **Step 2: Expand the Releasing section**

Replace the body of `## Releasing` (README lines 158-162) with:

```markdown
1. One-time: on pypi.org, add a *Trusted Publisher* for this GitHub repo
   (workflow `release.yml`, environment `pypi`).
2. Bump `version` in **all three** metadata files so they agree:
   `pyproject.toml`, `server.json` (top-level **and** `packages[0].version`),
   and `mcpb/manifest.json`. `tests/test_version_sync.py` fails if they drift.
3. If the release changes the published server, re-run the MCP registry
   publisher flow with the updated `server.json` (see "MCP registry" below).
4. Commit, tag `vX.Y.Z`, push the tag. CI builds, publishes to PyPI, and
   attaches artifacts to the GitHub release.
```

- [ ] **Step 3: Verify links + formatting, then commit**

Run: `.venv/bin/python -m pytest -q` (unchanged green; docs-only change) and eyeball the rendered README badges/section.

```bash
git add README.md
git commit -m "docs: add PyPI badge and three-file version checklist to Releasing"
```

---

### Task 3: Demo-recording script + README "See it work" scaffold (AGENT)

The *scriptable* half of the demo: a reproducible recording command and the README section that references the media. The binaries themselves are produced by the human in Task 4 (an agent has no terminal-GIF or GUI-screenshot capability), so this task creates everything except the two image files and leaves the section pointing at their committed paths.

**Files:**
- Create: `scripts/record_demo.sh`
- Modify: `README.md` (insert a "See it work" section after the install block, ~after line 10)
- Modify: `docs/media/README.md` (note the recording command lives in `scripts/record_demo.sh`)

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/record_demo.sh` — invoked by Task 4; `docs/media/budvar-3year.gif` and `docs/media/report-card.png` are referenced but supplied by Task 4.

- [ ] **Step 1: Write the recording script**

```bash
# scripts/record_demo.sh
#!/usr/bin/env bash
# Records the Budvar 3-year analysis as an asciinema cast and renders a GIF.
# Requires: asciinema, agg (https://github.com/asciinema/agg). Not a runtime dep.
# Usage: scripts/record_demo.sh   (run from repo root, inside the venv)
set -euo pipefail

CAST="docs/media/budvar-3year.cast"
GIF="docs/media/budvar-3year.gif"

echo "Recording — the analyze command will run automatically; keep it <15s."
asciinema rec --overwrite --cols 100 --rows 30 \
  --command 'rejstrik analyze "Budejovicky Budvar" --years 3' \
  "$CAST"

agg --cols 100 --rows 30 "$CAST" "$GIF"
echo "Wrote $GIF ($(du -h "$GIF" | cut -f1)). Target: <5 MB. report-card.png is a manual Claude Desktop screenshot."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/record_demo.sh
```

- [ ] **Step 3: Add the README "See it work" section**

Insert after the install code block (after `README.md` line 10, before the next section):

```markdown
## See it work

![Analyzing Budějovický Budvar's last 3 years of filings](docs/media/budvar-3year.gif)

The `analyze_company_card` report rendered in Claude Desktop:

![Report card in Claude Desktop](docs/media/report-card.png)

Reproduce the GIF with `scripts/record_demo.sh` (needs asciinema + agg).
```

- [ ] **Step 4: Update the media placeholder note**

Replace `docs/media/README.md` contents with:

```markdown
Demo media for the README "See it work" section:

- `budvar-3year.gif` — asciinema→agg recording of
  `rejstrik analyze "Budejovicky Budvar" --years 3`. Generate with
  `scripts/record_demo.sh` (keep it <15 s and <5 MB).
- `report-card.png` — manual screenshot of `analyze_company_card` rendered
  in Claude Desktop (also serves as MCP Apps regression proof).
```

- [ ] **Step 5: Verify + commit**

Run: `.venv/bin/ruff check src/ tests/ && .venv/bin/python -m pytest -q` (green; no code changed).

> Note: the README now references two not-yet-committed images. That is intentional — Task 4 commits them. If you want CI/link-checkers green in between, land Task 3 and Task 4 together.

```bash
git add scripts/record_demo.sh README.md docs/media/README.md
git commit -m "docs: add demo recording script and See it work section"
```

---

### Task 4: Record and commit the demo media (HUMAN)

**Why human:** producing a terminal GIF requires an interactive TTY + asciinema/agg installed locally, and `report-card.png` requires visually rendering the card in Claude Desktop and taking a screenshot. Neither is possible from a headless agent. No repo code changes — just two binary assets.

- [ ] Install tooling: `asciinema` and `agg` (`brew install asciinema agg` / distro equivalent).
- [ ] From repo root inside the venv, run `scripts/record_demo.sh`. Confirm the produced `docs/media/budvar-3year.gif` is <15 s and <5 MB (re-record if over).
- [ ] Add rejstrik to Claude Desktop, run the Budvar analysis so `analyze_company_card` renders, screenshot it to `docs/media/report-card.png`. Crop to the card.
- [ ] Verify both images resolve in the README preview (GitHub or a local Markdown viewer).
- [ ] Commit: `git add docs/media/budvar-3year.gif docs/media/report-card.png && git commit -m "docs: add demo GIF and report-card screenshot"`. (Optionally squash with Task 3 so the README never references missing files on `main`.)

---

### Task 5: Verify / publish the MCP registry entry (HUMAN)

**Why human:** requires querying the live registry and running the authenticated publisher flow (GitHub-based auth for the `io.github.janf19/*` namespace) — credentials an agent must not hold.

- [ ] Check whether the server is already published:
      `curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=rejstrik-mcp"` (or the current registry query endpoint) and look for `io.github.janf19/rejstrik-mcp`.
- [ ] If absent, install the MCP publisher CLU and run the publish flow with the (now 0.6.0) `server.json`, authenticating via the GitHub `janf19` account that owns the namespace.
- [ ] Confirm the entry resolves after publish (re-run the search/query).
- [ ] Record the resolved registry URL in `docs/media/README.md` or the README so the acceptance check is auditable.

---

### Task 6: Directory + community listings (HUMAN)

**Why human:** external PRs, forum/social accounts, and editorial judgment about wording. Checklist only, no repo code.

- [ ] Submit/verify listings on at least three of: mcpservers.org, mcp.so, Smithery, `awesome-mcp-servers` (open a PR).
- [ ] Post one honest Czech-community note (root.cz forum, or an X/LinkedIn thread) with the "ministry portal now 403s automated clients — here's an open-source fallback" framing. No overclaiming; link the repo.
- [ ] Confirm the PyPI badge (Task 2) renders a real version once the package is on PyPI.

---

## Self-Review

**1. Spec coverage:**
- §1 Demo media → T3 (script + README scaffold) + T4 (record GIF/PNG, restore "See it work"). ✅
- §2 Official MCP registry (verify/publish, bump `server.json`) → T1 (server.json bump to 0.6.0) + T5 (verify/publish). ✅
- §3 Directory + community listings + PyPI badge → T6 (listings/post) + T2 (PyPI badge). ✅
- §4 Release hygiene (three files agree; checklist) → T1 (drift-guard test + sync) + T2 (Releasing checklist). ✅
- Acceptance ("registry entry resolves; README renders both media files; ≥3 directories list; checklist updated") → T5 / T4 / T6 / T2 respectively. ✅
- Not-in-scope (hosted HTTP, paid promo) → honored; no such tasks. ✅

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"write tests for the above" — every AGENT step shows the exact test/edit/command; HUMAN steps are concrete manual actions, deliberately not code. ✅

**3. Type/name consistency:** `tests/test_version_sync.py`, `_pyproject_version()`, `scripts/record_demo.sh`, and the `docs/media/budvar-3year.gif` / `report-card.png` paths are named identically wherever referenced across tasks. ✅

**Executor legend:** T1–T3 = AGENT (in-repo, verifiable here). T4–T6 = HUMAN (GUI / accounts / credentials).
