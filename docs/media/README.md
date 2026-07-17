Demo media for the README "See it work" section:

- `cli-demo.txt` — plain-text transcript of the keyless CLI flow
  (`rejstrik find` + `rejstrik filings --financial-only`), captured live
  against ARES and the Sbírka listin portal with no API key set. Present.
- `budvar-3year.gif` — asciinema→agg recording of
  `rejstrik analyze "Budejovicky Budvar" --years 3`. Generate with
  `scripts/record_demo.sh` (keep it <15 s and <5 MB). Note: `analyze`
  extracts financials via a keyed LLM call server-side, so recording this
  requires an API key even though the MCP tool itself is keyless when the
  calling agent reads the PDF. STILL MISSING — human capture pending.
- `report-card.png` — manual screenshot of `analyze_company_card` rendered
  in Claude Desktop (also serves as MCP Apps regression proof). STILL
  MISSING — human capture pending (Task 7).
