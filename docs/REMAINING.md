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
                             # io.github.janf19/rejstrik-mcp
```

The `io.github.janf19/*` namespace is verified through the GitHub login,
so it must be the owner's account. Verify afterwards:

```bash
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=rejstrik" | head -40
```

## 2. Community listings (optional — discoverability)

All copy is paste-ready in [`docs/listings.md`](listings.md). Highest
value: a PR to an "Awesome MCP Servers" GitHub list adding rejstrik-mcp
under finance/government. Others (host marketplaces, an r/mcp announce
post) as desired.

## 3. Claude Desktop card check (optional — settles the widget question)

Install via the `.mcpb` from the GitHub release or the JSON config, ask
about a company, then have it call `render_card`.

- **Interactive card renders** → done; grab a screenshot as
  `docs/media/report-card.png` (the last missing demo asset).
- **Plain text instead** → the host is negotiating a different capability
  key than `mcp-apps`. Note the host + version and set
  `REJSTRIK_APPS_CAPABILITY_KEY` to the key it actually sends.

Note: the interactive-card path has never been verified in a live MCP
Apps host — the server gates on the `mcp-apps` capability but returns an
`mcp-ui` `rawHtml` resource, and whether Claude Desktop renders that
combination is unproven until someone tries it. Markdown output in Claude
Code is correct-by-design, not a bug.

---

Once item 1 is done, the project is 100% closed.
