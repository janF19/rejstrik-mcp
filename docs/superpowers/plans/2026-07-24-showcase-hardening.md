# Showcase Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the repo of non-showcase content, bring the MCP Apps card to the SEP-1865 spec while keeping markdown as the working default, and give the README a visual demo — all with every quality gate green.

**Architecture:** Five independent tasks over an existing, well-structured Python package. Tasks 2 and 3 are TDD code changes; Task 1 is repo hygiene; Task 4 is docs; Task 5 is a generated media asset. No core analysis/registry/filings/documents code changes.

**Tech Stack:** Python 3.11+, httpx, FastMCP (`mcp>=1.2`), `mcp-ui-server`, pytest, ruff. Demo asset via `asciinema` + `agg`.

## Global Constraints

- Every task ends green on: `ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
- Run all Python via the venv: `source .venv/bin/activate` first (the bare `python`/`ruff` are not on PATH).
- Tests stay offline and key-free (per CLAUDE.md). The only online step is the demo recording in Task 5, which is manual and not part of CI.
- Keep the always-working markdown card path as the default. The interactive card must never regress markdown output.
- Do NOT remove `docs/superpowers/` — the process trail is deliberately kept.
- Commit messages end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: Repo hygiene — remove non-showcase files

**Files:**
- Delete (untracked, filesystem move): `scripts/set_dell_main.sh` → `~/scripts/set_dell_main.sh`
- Remove (tracked): `scripts/autopilot.py`
- Modify: `docs/superpowers/specs/2026-07-13-autopilot-design.md` (add removed-note header)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable. Later tasks are independent of this one.

- [ ] **Step 1: Confirm nothing imports autopilot**

Run: `cd /Users/martinafallerova/projects/rejstrik-mcp && git grep -n "autopilot" -- src tests`
Expected: no output (no source/test references). If anything prints, stop and reassess.

- [ ] **Step 2: Move the personal Mac script out of the repo**

```bash
mkdir -p ~/scripts
mv scripts/set_dell_main.sh ~/scripts/set_dell_main.sh
```

Run: `git status --porcelain scripts/`
Expected: `set_dell_main.sh` no longer appears as untracked.

- [ ] **Step 3: Remove the autopilot script**

```bash
git rm scripts/autopilot.py
```

Expected: `rm 'scripts/autopilot.py'`.

- [ ] **Step 4: Annotate the autopilot design doc so it doesn't dangle**

Insert this line immediately below the first-line heading of
`docs/superpowers/specs/2026-07-13-autopilot-design.md`:

```markdown
> **Note (2026-07-24):** `scripts/autopilot.py` has been removed from the repo. This document is retained as a record of the process only.
```

- [ ] **Step 5: Verify gates still green**

Run: `source .venv/bin/activate && ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all pass, 269 tests (no test touched this task).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: drop autopilot script and personal machine script from repo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Derive User-Agent from the package version

**Files:**
- Modify: `src/rejstrik/core/http.py:5`
- Test: `tests/core/test_http.py:17-18`

**Interfaces:**
- Consumes: `rejstrik.__version__` (a `str`, currently `"0.8.0"`; `src/rejstrik/__init__.py` is a bare assignment, so importing it from `core/http.py` has no circular-import risk).
- Produces: `USER_AGENT: str` — unchanged name and type, now containing the live version.

- [ ] **Step 1: Rewrite the version test to assert the live version**

Replace `tests/core/test_http.py:17-18` with:

```python
def test_user_agent_reflects_current_version():
    from rejstrik import __version__

    assert __version__ in USER_AGENT
    assert "0.4" not in USER_AGENT
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/core/test_http.py::test_user_agent_reflects_current_version -v`
Expected: FAIL — `USER_AGENT` still contains `"0.4"` and not `"0.8.0"`.

- [ ] **Step 3: Derive the User-Agent from `__version__`**

Replace `src/rejstrik/core/http.py:5`:

```python
USER_AGENT = "rejstrik-mcp/0.4 (+https://github.com/janF19/rejstrik-mcp)"
```

with (add the import at the top of the file, after `import httpx`):

```python
from rejstrik import __version__

USER_AGENT = f"rejstrik-mcp/{__version__} (+https://github.com/janF19/rejstrik-mcp)"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/core/test_http.py -v`
Expected: all three tests PASS.

- [ ] **Step 5: Verify gates green**

Run: `source .venv/bin/activate && ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/rejstrik/core/http.py tests/core/test_http.py
git commit -m "fix: derive User-Agent from package version (was pinned at 0.4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Align the MCP Apps card to SEP-1865

**Files:**
- Modify: `src/rejstrik/mcp/server.py` (lines 61-94, 138)
- Test: `tests/mcp/test_card_apps.py`

**Interfaces:**
- Consumes: `mcp_ui_server.create_ui_resource` (emits `UIResource` with `resource.mimeType == "text/html"`; the `mimeType` attribute is mutable post-creation — verified 2026-07-24).
- Produces: unchanged public surface — `_apps_capability(experimental: dict | None) -> bool`, `_render_card_output(...) -> list[TextContent | UIResource]`, resource URI `ui://rejstrik/report`. Only the capability key string, the `_meta` key, and the emitted mimetype change.

Spec values (verbatim from SEP-1865, 2026-01-26):
- capability key: `io.modelcontextprotocol/ui`
- tool/resource meta path: `_meta.ui.resourceUri`
- resource mimetype: `text/html;profile=mcp-app`

- [ ] **Step 1: Update the capability-key test to the spec key**

Replace `tests/mcp/test_card_apps.py:25-28` with:

```python
def test_apps_capability_detects_key():
    assert server._apps_capability({"io.modelcontextprotocol/ui": {}}) is True
    assert server._apps_capability({"mcp-apps": {}}) is False
    assert server._apps_capability({}) is False
    assert server._apps_capability(None) is False
```

- [ ] **Step 2: Add assertions for the spec meta key and mimetype**

Append these two tests to `tests/mcp/test_card_apps.py`:

```python
def test_ui_meta_uses_spec_key():
    assert server._UI_META == {"ui": {"resourceUri": "ui://rejstrik/report"}}


def test_card_ui_resource_uses_app_profile_mimetype():
    out = server._render_card_output(REPORT, apps_supported=True)
    assert out[0].resource.mimeType == "text/html;profile=mcp-app"
```

- [ ] **Step 3: Run the new/changed tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/mcp/test_card_apps.py -v`
Expected: FAIL — `test_apps_capability_detects_key` (still matches `mcp-apps`), `test_ui_meta_uses_spec_key` (key is `mcp/ui`), and `test_card_ui_resource_uses_app_profile_mimetype` (mimetype is `text/html`).

- [ ] **Step 4: Update the capability default key**

In `src/rejstrik/mcp/server.py`, replace line 71:

```python
    key = os.environ.get("REJSTRIK_APPS_CAPABILITY_KEY", "mcp-apps")
```

with:

```python
    key = os.environ.get("REJSTRIK_APPS_CAPABILITY_KEY", "io.modelcontextprotocol/ui")
```

- [ ] **Step 5: Update the `_meta` key to the spec path**

In `src/rejstrik/mcp/server.py`, replace lines 61-65:

```python
# ext-apps _meta UI declaration. The "mcp/ui" meta key is spec-defined and fixed;
# the separate experimental-capability flag name the host must advertise is
# overridable at runtime via REJSTRIK_APPS_CAPABILITY_KEY (default "mcp-apps",
# see _apps_capability). Last reviewed against the MCP Apps spec 2026-07-17.
_UI_META = {"mcp/ui": {"resourceUri": _UI_URI}}
```

with:

```python
# SEP-1865 (MCP Apps, 2026-01-26) _meta UI declaration. The host reads
# _meta.ui.resourceUri, so the top-level meta key is "ui". The capability the
# host must advertise is "io.modelcontextprotocol/ui" (see _apps_capability),
# runtime-overridable via REJSTRIK_APPS_CAPABILITY_KEY. Interactive rendering is
# gated upstream: Claude negotiates the capability but does not yet render the
# iframe (ext-apps#671), so markdown remains the default output.
_UI_META = {"ui": {"resourceUri": _UI_URI}}
```

- [ ] **Step 6: Set the spec mimetype on the resource declaration and the emitted resource**

In `src/rejstrik/mcp/server.py`, replace line 138:

```python
@mcp.resource(_UI_URI, mime_type="text/html", meta=_UI_META)
```

with:

```python
@mcp.resource(_UI_URI, mime_type="text/html;profile=mcp-app", meta=_UI_META)
```

Then, in `_card_ui_resource` (lines 84-94), set the profile mimetype on the
object returned by `create_ui_resource` (which hardcodes `text/html`):

```python
def _card_ui_resource(report: CompanyFinancialReport) -> UIResource:
    resource = create_ui_resource(
        {
            "uri": _UI_URI,
            "content": {
                "type": "rawHtml",
                "htmlString": render_report_card(report),
            },
            "encoding": "text",
        }
    )
    # create_ui_resource emits text/html; SEP-1865 requires the mcp-app profile.
    resource.resource.mimeType = "text/html;profile=mcp-app"
    return resource
```

- [ ] **Step 7: Run the card tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/mcp/test_card_apps.py tests/mcp/test_card_tool.py -v`
Expected: all PASS (existing `UIResource`/URI assertions still hold; new key/mimetype assertions now hold).

- [ ] **Step 8: Verify full gates green**

Run: `source .venv/bin/activate && ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/rejstrik/mcp/server.py tests/mcp/test_card_apps.py
git commit -m "fix(mcp): align Apps card to SEP-1865 (capability, _meta.ui, mcp-app mimetype)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Note on the capability-negotiation read:** `_host_supports_apps` reads
`ctx.session.client_params.capabilities.experimental`. This task changes only
the key string looked up there. Whether `mcp>=1.2` surfaces the
`io.modelcontextprotocol/ui` capability under `experimental` or elsewhere is
unverifiable offline; the default-to-markdown-when-absent behaviour makes an
unrecognised location safe (card simply never activates, markdown renders).
If, during Task 5's live Claude Desktop check, the host is found to advertise
the capability under a different attribute, adjust `_host_supports_apps` then.
Do not speculatively change it here.

---

### Task 4: Honest card docs + drop the dead screenshot reference

**Files:**
- Modify: `README.md` (report-card description)
- Modify: `docs/REMAINING.md` (item 3, the card-verification section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable.

- [ ] **Step 1: Add the host-support caveat in the README**

In `README.md`, find the "Report card" bullet under "Co to umí":

```markdown
- **Report card:** shrnutí jako interaktivní HTML karta (hosté s MCP
  Apps) nebo přehledný markdown (textoví hosté jako Claude Code).
```

Replace it with:

```markdown
- **Report card:** shrnutí jako přehledný markdown (výchozí, funguje
  všude — Claude Code, Desktop, …). Interaktivní HTML karta je
  implementovaná dle MCP Apps (SEP-1865), ale klienti ji zatím
  nevykreslují (upstream [ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)),
  takže se automaticky použije markdown.
```

- [ ] **Step 2: Replace the "never verified" wording in REMAINING with concrete status**

In `docs/REMAINING.md`, replace the whole "## 3. Claude Desktop card check" section (from that heading through its closing "Markdown output in Claude Code is correct-by-design, not a bug." paragraph) with:

```markdown
## 3. Claude Desktop card check (optional — confirms upstream status)

The server is aligned to MCP Apps SEP-1865: it advertises capability
`io.modelcontextprotocol/ui`, declares `_meta.ui.resourceUri`, and emits the
UI resource at `text/html;profile=mcp-app`. Markdown is the default and always
renders.

Interactive rendering is blocked **upstream**, not in this repo: as of
[ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)
(open, May 2026) Claude Desktop and claude.ai negotiate the capability and
fetch the resource but do not render the iframe. When a host ships rendering,
install via the `.mcpb` and ask about a company, then call `render_card`:

- **Interactive card renders** → capture `docs/media/report-card.png`.
- **Plain text / widget placeholder** → confirms #671; markdown is used.
  If the host advertises the capability under a different key, note the host +
  version and set `REJSTRIK_APPS_CAPABILITY_KEY` accordingly.
```

- [ ] **Step 3: Confirm no other dead reference to the screenshot**

Run: `cd /Users/martinafallerova/projects/rejstrik-mcp && git grep -n "report-card.png"`
Expected: matches only inside `docs/REMAINING.md` (as an *if-it-renders* future step, not a claim that it exists). No README or media-manifest reference asserting the file is present.

- [ ] **Step 4: Verify gates green (docs-only, but keep the habit)**

Run: `source .venv/bin/activate && ruff check src/ tests/ && python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/REMAINING.md
git commit -m "docs: state card as SEP-1865-aligned with markdown default; cite ext-apps#671

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: README demo GIF

**Files:**
- Create: `docs/media/budvar-3year.gif` (generated)
- Modify: `README.md` (embed the GIF near the top)
- Uses (unchanged): `scripts/record_demo.sh`

**Interfaces:**
- Consumes: `scripts/record_demo.sh`, which runs `rejstrik analyze "Budejovicky Budvar" --years 3` and renders `docs/media/budvar-3year.gif`.
- Produces: a committed GIF asset and a README embed.

**This task is manual and requires network + two external tools.** It cannot run in CI and is not TDD. Do it on a machine with connectivity.

- [ ] **Step 1: Install the recording tools (not currently installed)**

```bash
brew install asciinema agg
```

Run: `command -v asciinema agg`
Expected: both print a path. (If `brew install agg` fails, use
`cargo install --git https://github.com/asciinema/agg`.)

- [ ] **Step 2: Record the demo**

```bash
cd /Users/martinafallerova/projects/rejstrik-mcp
source .venv/bin/activate
scripts/record_demo.sh
```

Expected: produces `docs/media/budvar-3year.cast` and
`docs/media/budvar-3year.gif`. The run makes live ARES / Sbírka listin calls;
keep it under ~15s. Re-run if the output looks truncated or errored.

- [ ] **Step 3: Check the GIF size**

Run: `ls -lh docs/media/budvar-3year.gif`
Expected: ideally under ~2 MB. If larger, re-record `record_demo.sh` with
smaller `--cols`/`--rows` (edit the script's `--cols 100 --rows 30`) rather
than committing a heavy binary.

- [ ] **Step 4: Embed the GIF in the README**

In `README.md`, immediately after the badges line (line 3) and its blank line,
insert:

```markdown
![Ukázka: analýza firmy z příkazové řádky](docs/media/budvar-3year.gif)
```

- [ ] **Step 5: Verify it renders**

Push to a branch and open the README on GitHub (or preview locally) to confirm
the GIF displays and is not broken. The `.cast` file is intermediate — do not
commit it (add `docs/media/*.cast` to `.gitignore` if it isn't already ignored
by an existing rule).

- [ ] **Step 6: Commit**

```bash
git add docs/media/budvar-3year.gif README.md .gitignore
git commit -m "docs(readme): add CLI demo GIF

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

Run the whole gate once more from a clean state:

```bash
source .venv/bin/activate
ruff check src/ tests/ && ruff format --check src/ tests/ && python -m pytest -q
```

Expected: ruff clean, formatted, all tests pass (271 — Task 3 adds two).

Manual confirmations:
- `git status` clean; `git grep -n "autopilot" -- src tests` empty.
- `git grep -n "0.4" src/rejstrik/core/http.py` empty.
- README shows the demo GIF on GitHub.
```
