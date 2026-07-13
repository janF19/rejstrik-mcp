# Autopilot: Unattended Stage Pipeline (Opus plans → Sonnet executes → verify → merge)

**Date:** 2026-07-13
**Status:** Approved design, implemented in `scripts/autopilot.py`
**Parent:** `2026-07-13-roadmap-overview.md`

## Goal

Run the A–D roadmap stages without babysitting, on any machine after
`git clone`, using the operator's Claude subscription (headless
`claude -p`), with per-phase retries, hard limits, and honest stops.

## Shape: state machine, not a loop

There is no timer and no daemon. `scripts/autopilot.py` derives progress
from the repository itself and does the next missing thing:

| Question | Source of truth | If missing |
|---|---|---|
| Stage planned? | `docs/superpowers/plans/*stage-<id>*.md` exists on main | **Plan phase** (Opus) |
| Stage executed? | branch `stage/<id>` exists with commits ahead of main | **Execute phase** (Sonnet, worktree) |
| Stage done? | `stage/<id>` merged into main | **Verify + merge phase** (script) |

Rerunning the script is always safe; it continues wherever git says it
is. Cross-machine resume works because the state lives in commits and
branches, not local files.

## Phases

1. **Plan (Opus, main checkout).** Prompt: read the stage spec, use the
   `superpowers:writing-plans` skill, save to
   `docs/superpowers/plans/<date>-stage-<id>-implementation.md`, commit.
   The script verifies the file exists (and commits it itself if the
   agent forgot), else retries.
2. **Execute (Sonnet, worktree).** Script creates branch `stage/<id>` +
   worktree `../rejstrik-stage-<id>`, bootstraps a venv there
   (`uv venv` + `uv pip install -e ".[dev]"`, fallback to stdlib venv),
   then runs a fresh Sonnet session with the plan, CLAUDE.md rules, and
   an explicit "do not merge/push/tag" boundary.
3. **Verify (script, trust nothing).** The script itself runs
   `ruff check`, `ruff format --check`, `pytest -q` in the worktree. On
   failure: re-invoke Sonnet with the failure tail. Retries bounded.
4. **Merge (script).** `git merge --no-ff stage/<id>` on main, reinstall
   deps (plans may add packages), re-verify on main, remove worktree,
   delete branch, `git push` (unless `--no-push`).

## Limits & failure handling

- `--max-attempts N` per phase (default 3). Exhausted → stop, keep the
  worktree and logs for a human; nothing half-merged.
- `--timeout-mins` per Claude run (default 90) — hung runs are killed
  and count as a failed attempt.
- `--max-turns` per Claude run (default 250) passed to the CLI.
- Merge conflict or dirty main → immediate stop with instructions.
- Usage-limit / auth errors from the CLI are detected by exit status and
  stop the pipeline (retrying would burn attempts pointlessly); rerun
  later — idempotence makes that free.
- All Claude output is teed to `.autopilot/logs/` (gitignored).

## Permissions model

Default: `--allowedTools` with a bounded list (file tools, skills, and
`Bash(git:*)`, `Bash(python:*)`, `Bash(ruff:*)`, `Bash(pytest:*)`,
`Bash(pip:*)`, `Bash(uv:*)`, `Bash(curl:*)` — curl because Stage A
captures live fixtures). Anything outside the list is denied in
headless mode and the agent must route around it.
`--yolo` switches to `--dangerously-skip-permissions` for maximum
autonomy; acceptable risk profile here because execution happens in a
throwaway worktree of a public-data project, but it remains opt-in.

## What is NOT automated (by design)

- **Stage E** (recordings, registry submission, community posts) — human.
- **Releases** (version bump → tag → PyPI publish) — human, per README.
- **Stage C acceptance** ("card visibly renders in Claude Desktop") —
  code lands automated; the human checks the pixel truth before release.
- Spec changes — if a stage turns out to be mis-specified, the pipeline
  stops; specs are amended by the human, not the pipeline.

## Prerequisites on a fresh machine

`git`, Python 3.11+, `uv` (optional but faster), Claude Code CLI
installed and **logged in** (subscription auth carries into `-p` mode),
superpowers plugin installed (prompts degrade gracefully without it —
they instruct the model to plan/execute carefully even if the named
skills are unavailable). No API keys needed; tests are offline.

## Usage

```bash
python scripts/autopilot.py                 # run all remaining stages (a b c d)
python scripts/autopilot.py --stages a      # just stage A
python scripts/autopilot.py --stages c d --yolo --no-push
python scripts/autopilot.py --dry-run       # show derived state + planned actions
```
