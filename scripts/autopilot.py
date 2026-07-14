#!/usr/bin/env python3
"""Unattended stage pipeline: Opus plans, Sonnet executes in a worktree,
the script verifies and merges. State is derived from git, so rerunning
is always safe and resumes wherever the repo actually is.

Design: docs/superpowers/specs/2026-07-13-autopilot-design.md
Usage:  python scripts/autopilot.py [--stages a b ...] [--dry-run] [--yolo]
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "docs" / "superpowers" / "plans"
SPECS = REPO / "docs" / "superpowers" / "specs"
LOGS = REPO / ".autopilot" / "logs"

STAGES: dict[str, dict] = {
    "a": {"spec": "2026-07-13-stage-a-filings-fallback-design.md"},
    "b": {"spec": "2026-07-13-stage-b-test-hygiene-windows-ci-design.md"},
    "c": {"spec": "2026-07-13-stage-c-mcp-apps-card-and-large-pdfs-design.md"},
    "d": {"spec": "2026-07-13-stage-d-analysis-depth-valuation-design.md"},
    # Stage E (distribution/demo) is deliberately manual — see its spec.
    # Stages F and G share one spec; "scope" narrows the planner to a section.
    "f": {
        "spec": "2026-07-14-post-audit-hardening-and-features-design.md",
        "scope": (
            "Plan STAGE F ONLY (sections F1-F5). F6 is a human checklist: "
            "carry it into the plan verbatim as HUMAN tasks, no code. Do not "
            "plan anything from Stage G."
        ),
    },
    "g": {
        "spec": "2026-07-14-post-audit-hardening-and-features-design.md",
        "scope": (
            "Plan STAGE G ONLY (sections G1-G4). For G2, read the reference "
            "implementation in ~/projects/obchodni-rejstrik-ai "
            "(apps/api/services/industry_multiples.py, "
            "apps/api/services/business_classification.py, "
            "apps/api/scripts/import_damodaran_multiples.py) and port "
            "NACE_DIVISION_MAP verbatim; if any deviation is genuinely "
            "needed, isolate it in a 'Deviations for product-owner sign-off' "
            "section of the plan rather than silently changing values. The "
            "Damodaran importer script is manual tooling like smoke.py - "
            "network-using, never run in tests or CI; tests read only the "
            "committed JSON dataset."
        ),
    },
}

ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Glob",
        "Grep",
        "Edit",
        "Write",
        "Skill",
        "TodoWrite",
        "Task",
        "WebFetch",
        "WebSearch",
        "Bash(git:*)",
        "Bash(python:*)",
        "Bash(python3:*)",
        "Bash(ruff:*)",
        "Bash(pytest:*)",
        "Bash(pip:*)",
        "Bash(uv:*)",
        "Bash(uvx:*)",
        "Bash(curl:*)",
        "Bash(ls:*)",
        "Bash(mkdir:*)",
    ]
)

CHECKS = [
    ["ruff", "check", "src/", "tests/"],
    ["ruff", "format", "--check", "src/", "tests/"],
    ["python", "-m", "pytest", "-q"],
]


def sh(
    cmd: list[str], cwd: Path, timeout: int = 600, check: bool = True
) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}  (cwd={cwd.name})")
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=check
    )


def git(args: list[str], cwd: Path = REPO, check: bool = True) -> str:
    result = sh(["git", *args], cwd=cwd, check=check)
    return result.stdout.strip()


def base_branch() -> str:
    """The branch autopilot integrates into — the main checkout's current
    HEAD, not a hardcoded 'main'. Stage branches fork from and merge back
    into whatever branch you launched autopilot on."""
    return git(["rev-parse", "--abbrev-ref", "HEAD"])


# ---------------------------------------------------------------- state


def find_plan(stage: str) -> Path | None:
    matches = sorted(PLANS.glob(f"*stage-{stage}-*.md")) + sorted(
        PLANS.glob(f"*stage{stage}-*.md")
    )
    return matches[-1] if matches else None


def branch_exists(stage: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"stage/{stage}"],
            cwd=REPO,
            capture_output=True,
        ).returncode
        == 0
    )


def branch_merged(stage: str) -> bool:
    if not branch_exists(stage):
        return False
    merged = git(["branch", "--merged", base_branch(), "--format=%(refname:short)"])
    return f"stage/{stage}" in merged.splitlines()


def stage_done(stage: str) -> bool:
    # Done = branch merged, or the branch was already cleaned up after a
    # previous successful run (plan exists, no branch, marker in history).
    if branch_merged(stage):
        return True
    if find_plan(stage) and not branch_exists(stage):
        log = git(["log", "--oneline", "--grep", f"stage {stage}: merge", "-i"])
        return bool(log)
    return False


# ---------------------------------------------------------------- claude


def run_claude(
    prompt: str, model: str, cwd: Path, opts: argparse.Namespace, log_name: str
) -> bool:
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude CLI not found on PATH — install and log in first.")
    cmd = [claude, "-p", prompt, "--model", model, "--max-turns", str(opts.max_turns)]
    if opts.yolo:
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd += ["--allowedTools", ALLOWED_TOOLS]
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{log_name}.log"
    print(f"  claude --model {model} (log: {log_path.relative_to(REPO)})")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=opts.timeout_mins * 60,
        )
    except subprocess.TimeoutExpired:
        log_path.write_text("TIMEOUT", encoding="utf-8")
        print(f"  !! timed out after {opts.timeout_mins} min")
        return False
    log_path.write_text(
        (result.stdout or "") + "\n--- stderr ---\n" + (result.stderr or ""),
        encoding="utf-8",
    )
    if result.returncode != 0:
        blob = (result.stdout + result.stderr).lower()
        if (
            "usage limit" in blob
            or "rate limit" in blob
            or "session limit" in blob
            or "log in" in blob
        ):
            sys.exit(
                f"claude CLI unavailable (limits/auth) — see {log_path}. "
                "Rerun autopilot later; it will resume where it stopped."
            )
        print(f"  !! claude exited {result.returncode}")
        return False
    return True


# ---------------------------------------------------------------- verify


def venv_env_python(worktree: Path) -> Path:
    sub = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return worktree / ".venv" / sub


def bootstrap_venv(worktree: Path) -> None:
    python = venv_env_python(worktree)
    if not python.exists():
        if shutil.which("uv"):
            sh(["uv", "venv"], cwd=worktree)
        else:
            sh([sys.executable, "-m", "venv", ".venv"], cwd=worktree)
    if shutil.which("uv"):
        sh(
            ["uv", "pip", "install", "-e", ".[dev]", "--python", str(python)],
            cwd=worktree,
            timeout=900,
        )
    else:
        sh(
            [str(python), "-m", "pip", "install", "-q", "-e", ".[dev]"],
            cwd=worktree,
            timeout=900,
        )


def run_checks(worktree: Path) -> tuple[bool, str]:
    python = venv_env_python(worktree)
    for check in CHECKS:
        cmd = (
            [str(python), "-m", *check]
            if check[0] != "python"
            else [str(python), *check[1:]]
        )
        result = subprocess.run(
            cmd, cwd=worktree, capture_output=True, text=True, timeout=1800
        )
        if result.returncode != 0:
            tail = ((result.stdout or "") + (result.stderr or ""))[-4000:]
            return False, f"`{' '.join(check)}` failed:\n{tail}"
    return True, ""


# ---------------------------------------------------------------- phases


def phase_plan(stage: str, opts: argparse.Namespace) -> Path | None:
    spec = SPECS / STAGES[stage]["spec"]
    scope = STAGES[stage].get("scope", "")
    target = f"docs/superpowers/plans/{dt.date.today()}-stage-{stage}-implementation.md"
    prompt = f"""Read the design spec at {spec.relative_to(REPO).as_posix()} and CLAUDE.md.
{scope}
Use the superpowers:writing-plans skill if available (write a complete
step-by-step implementation plan even if it is not). Save the plan to
{target}. Requirements: executable by an engineer with zero extra
context; exact file paths; strict TDD order (failing test first, minimal
implementation, green); every task ends with the verification commands
`ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`.
Commit ONLY the plan file to git (message: "plan: stage {stage}").
Do not implement anything."""
    for attempt in range(1, opts.max_attempts + 1):
        print(f"[stage {stage}] planning with {opts.plan_model} (attempt {attempt})")
        run_claude(prompt, opts.plan_model, REPO, opts, f"stage-{stage}-plan-{attempt}")
        plan = find_plan(stage)
        if plan:
            if git(["status", "--porcelain", str(plan)], check=False):
                git(["add", str(plan)])
                git(["commit", "-m", f"plan: stage {stage}"])
            return plan
    return None


def phase_execute(stage: str, plan: Path, opts: argparse.Namespace) -> Path | None:
    worktree = REPO.parent / f"rejstrik-stage-{stage}"
    if not worktree.exists():
        if branch_exists(stage):
            git(["worktree", "add", str(worktree), f"stage/{stage}"])
        else:
            git(
                [
                    "worktree",
                    "add",
                    "-b",
                    f"stage/{stage}",
                    str(worktree),
                    base_branch(),
                ]
            )
    bootstrap_venv(worktree)
    base = f"""You are in a git worktree on branch stage/{stage} of rejstrik-mcp.
Execute the implementation plan at {plan.relative_to(REPO).as_posix()} COMPLETELY.
Use the superpowers:executing-plans and test-driven-development skills if
available; follow CLAUDE.md rules exactly. Tests stay offline and
key-free. Commit after each green step. Before finishing, make
`ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
fully pass. Do NOT merge, push, tag, or bump versions. If a step needs
live network, attempt it; if it needs human judgment, leave a clearly
marked TODO in the plan file and continue with the rest."""
    prompt = base
    for attempt in range(1, opts.max_attempts + 1):
        print(f"[stage {stage}] executing with {opts.exec_model} (attempt {attempt})")
        run_claude(
            prompt, opts.exec_model, worktree, opts, f"stage-{stage}-exec-{attempt}"
        )
        ok, failure = run_checks(worktree)
        if ok:
            dirty = git(["status", "--porcelain"], cwd=worktree, check=False)
            if dirty:
                git(["add", "-A"], cwd=worktree)
                git(
                    ["commit", "-m", f"stage {stage}: autopilot checkpoint"],
                    cwd=worktree,
                )
            return worktree
        print("  !! verification failed, feeding failures back")
        prompt = (
            base
            + f"\n\nA previous session left verification failing. Fix this first:\n{failure}"
        )
    return None


def phase_merge(stage: str, worktree: Path, opts: argparse.Namespace) -> bool:
    if git(["status", "--porcelain"], check=False):
        sys.exit("main checkout is dirty — commit/stash before autopilot merges.")
    print(f"[stage {stage}] merging stage/{stage} into main")
    merge = subprocess.run(
        [
            "git",
            "merge",
            "--no-ff",
            f"stage/{stage}",
            "-m",
            f"stage {stage}: merge autopilot branch",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if merge.returncode != 0:
        git(["merge", "--abort"], check=False)
        print(f"  !! merge conflict — resolve by hand:\n{merge.stdout}{merge.stderr}")
        return False
    bootstrap_venv(REPO)  # plans may add dependencies
    ok, failure = run_checks(REPO)
    if not ok:
        print(f"  !! post-merge verification failed on main — investigate:\n{failure}")
        return False
    git(["worktree", "remove", str(worktree), "--force"], check=False)
    git(["branch", "-d", f"stage/{stage}"], check=False)
    if opts.push:
        git(["push", "origin", base_branch()])
    print(f"[stage {stage}] DONE")
    return True


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="*", default=list(STAGES), choices=STAGES)
    parser.add_argument("--plan-model", default="opus")
    parser.add_argument("--exec-model", default="sonnet")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=250)
    parser.add_argument("--timeout-mins", type=int, default=90)
    parser.add_argument("--yolo", action="store_true", help="skip permission prompts")
    parser.add_argument("--no-push", dest="push", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args()

    for stage in opts.stages:
        if stage_done(stage):
            print(f"[stage {stage}] already merged — skipping")
            continue
        plan = find_plan(stage)
        if opts.dry_run:
            state = "execute" if plan else "plan"
            print(f"[stage {stage}] next action: {state}")
            continue
        if not plan:
            plan = phase_plan(stage, opts)
            if not plan:
                sys.exit(f"[stage {stage}] planning failed after retries — stopping.")
        worktree = phase_execute(stage, plan, opts)
        if not worktree:
            sys.exit(
                f"[stage {stage}] execution failed after {opts.max_attempts} "
                f"attempts. Worktree and .autopilot/logs/ kept for inspection."
            )
        if not phase_merge(stage, worktree, opts):
            sys.exit(f"[stage {stage}] merge/verify failed — human needed.")
    if not opts.dry_run:
        print("All requested stages complete.")


if __name__ == "__main__":
    main()
