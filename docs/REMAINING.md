# What's left

As of v0.8.0 (published to PyPI 2026-07-18), the project is functionally
shipped: code, tests, PyPI package, GitHub release, `.mcpb` bundle, Czech
README, and the CI canary with auto-issues are all live and verified.

Only **item 1** is a "real" remaining step. The rest is optional polish.

## 1. Publish to the MCP registry (the main one)

Makes the server discoverable at registry.modelcontextprotocol.io.
`server.json` is already correct at 0.8.0. From the repo directory:

```bash
brew install mcp-publisher   # or grab the binary from
                             # github.com/modelcontextprotocol/registry releases
mcp-publisher login github   # opens GitHub device-flow auth — this is why
                             # only the repo owner can do it
mcp-publisher publish        # reads ./server.json and publishes
                             # io.github.janF19/rejstrik-mcp
```

The `io.github.janF19/*` namespace is verified through the GitHub login,
so it must be the owner's account. Verify afterwards:

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=rejstrik" | head -40
```

## 2. Community listings (optional — discoverability)

All copy is paste-ready in [`docs/listings.md`](listings.md). Highest
value: a PR to an "Awesome MCP Servers" GitHub list adding rejstrik-mcp
under finance/government. Others (host marketplaces, an r/mcp announce
post) as desired.

## 3. Claude Desktop card check (optional — confirms upstream status)

The server is aligned to MCP Apps SEP-1865: it advertises capability
`io.modelcontextprotocol/ui`, declares `_meta.ui.resourceUri`, and emits the
UI resource at `text/html;profile=mcp-app`. Markdown is the default and always
renders.

The markdown/HTML card screenshot is captured: `docs/media/report-card.png`
(rendered by `scripts/render_showcase_card.py` from a real
`analyze_financials` + `estimate_valuation` run and now the README hero).
Only the *interactive host rendering* check below remains blocked.

Interactive rendering is blocked **upstream**, not in this repo: as of
[ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)
(open, May 2026) Claude Desktop and claude.ai negotiate the capability and
fetch the resource but do not render the iframe. When a host ships rendering,
install via the `.mcpb` and ask about a company, then call `render_card`:

- **Interactive card renders** → confirms the upstream fix landed.
- **Plain text / widget placeholder** → confirms #671; markdown is used.
  If the host advertises the capability under a different key, note the host +
  version and set `REJSTRIK_APPS_CAPABILITY_KEY` accordingly.

---

Once item 1 is done, the project is 100% closed.
