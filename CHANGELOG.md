# Changelog

## 0.5.0 — Stage C: card delivery + large PDFs

- Card output now degrades gracefully: hosts that negotiate the MCP Apps
  capability get an interactive HTML card (registered as the `ui://rejstrik/report`
  resource); text-only hosts (Claude Code, etc.) get a compact markdown summary
  instead of raw HTML. The card now shows a multi-year figures table, ratios with
  plain-language one-liners, severity-sorted red flags, and a public-money section.
- `get_filing` gains an `embed` parameter (`"auto" | "always" | "never"`, default
  `"auto"`). The default embed cap is raised 15 MB → 25 MB
  (`REJSTRIK_MAX_EMBED_BYTES`). Large PDFs are never silently dropped — filesystem
  hosts are steered to `embed="never"` and the local `file_path`. Metadata now
  includes `page_count`.
- New keyless tool `read_filing_text(ico, year=None, filing_id=None, pages="1-10")`
  extracts the PDF text layer for a page range (pypdf, no LLM/OCR). Pages without a
  text layer are reported honestly rather than as empty strings.
- New dependency: `pypdf`.
