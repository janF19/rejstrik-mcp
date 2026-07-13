# Stage B: Hermetic Tests, Windows CI, README Fact Fixes

**Date:** 2026-07-13
**Status:** Approved design, pending implementation plan
**Parent:** `2026-07-13-roadmap-overview.md`
**Ships as:** v0.4.2

## Problem

`python -m pytest -q` fails on the primary dev machine (Windows, repo has
a real `.env`): 6 failures, all environmental, none caught by Linux-only
CI. The CLAUDE.md contract — "tests are offline and key-free" — is
currently untrue on the machine where development happens.

## Design

### 1. Hermetic LLM-key detection

Root cause: `documents/config.py::has_llm_key()` calls
`load_dotenv(find_dotenv(usecwd=True))` on **every call**, re-importing
the repo `.env` (which legitimately contains `OPENAI_API_KEY` for keyed
smoke testing) after tests `monkeypatch.delenv` it.

Fix at the source, not in tests:

- Make dotenv loading **once per process** (module-level or cached
  `functools.lru_cache` sentinel) so environment mutation after import is
  respected — this also removes per-call disk I/O on a hot path.
- Add an autouse fixture in `tests/conftest.py` that (a) blanks
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `REJSTRIK_LLM_PROVIDER` and
  (b) disables the dotenv loader, so the suite passes identically with or
  without a `.env` present. Keyed-mode tests set keys explicitly.

Affected failing tests that must go green without modification of their
assertions: `tests/documents/test_config.py::test_has_llm_key_false_when_unset`,
all four `tests/mcp/test_keyed_degradation.py` cases.

### 2. Windows-portable test fixtures

`tests/mcp/test_get_filing.py` fakes `file_path="/cache/..."`, which is
not absolute on Windows → `Path.as_uri()` raises `ValueError`. Fix the
fixture to build a genuinely absolute path via `tmp_path`. Audit the rest
of the suite for the same pattern (`grep` for hardcoded `"/` paths).

Consider (cheap, do it): `get_filing` in `mcp/server.py` wrapping
`as_uri()` failures into the plain-text fallback branch instead of
crashing the tool — a defensive guard for any host-supplied odd path.

### 3. CI matrix gains Windows

`.github/workflows/ci.yml`: add `windows-latest` to the matrix (Python
3.12 only is fine — the point is path/env semantics, not version
coverage). Ruff steps stay Linux-only if runtime is a concern; pytest
runs on both.

### 4. README fact fixes (no media work — that's Stage E)

- ESM closure date: "2026-12-17" is a future date described as a past
  event. Verify the real date of the Czech ESM public-access closure and
  correct it.
- Remove or comment out the two broken image references
  (`docs/media/budvar-3year.gif`, `docs/media/report-card.png`) until
  Stage E records real media — broken images on the repo front page cost
  more credibility than having no media section.
- While present: `find_company` returns raw `legal_form` code ("302");
  add a small static code→name mapping for the common forms (s.r.o.,
  a.s., národní podnik, družstvo, OSVČ...) in `registry/models.py` or
  `ares.py`, surfacing `legal_form_name` alongside the code. (Small,
  user-visible, fits "hygiene".)

## Testing

Green `pytest -q` on Windows dev machine **with the `.env` present**, and
on both CI legs. New unit tests: dotenv loaded once; legal-form mapping;
`get_filing` path-guard branch.

## Acceptance

CI badge covers Windows; a fresh clone on Windows with a populated `.env`
passes the suite; README contains no false claims.
