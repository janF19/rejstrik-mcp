Demo media for the README "See it work" section:

- `cli-demo.txt` — plain-text transcript of the keyless CLI flow
  (`rejstrik find` + `rejstrik filings --financial-only`), captured live
  against ARES and the Sbírka listin portal with no API key set. Present.
- `robe-analyze.gif` — recorded via `scripts/record_demo.sh` (which runs
  `scripts/demo_analyze.py`): find_company → list_filings → read the real
  filed PDF (ROBE lighting s.r.o., účetní závěrka 2023) → analyze_financials,
  captured live against ARES/ISIR/ADIS/Sbírka listin with no API key set.
  Present.
- `report-card.png` — manual screenshot of the `render_card` output
  rendered in Claude Desktop (also serves as MCP Apps regression proof).
  STILL MISSING — human capture pending.
