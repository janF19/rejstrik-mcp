#!/usr/bin/env bash
# Records the ROBE lighting financial analysis (via the actual MCP flow:
# find_company -> list_filings -> read the filed PDF -> analyze_financials)
# as an asciinema cast and renders a GIF.
# Requires: asciinema, agg (https://github.com/asciinema/agg). Not a runtime dep.
# Usage: scripts/record_demo.sh   (run from repo root, inside the venv)
set -euo pipefail

CAST="docs/media/robe-analyze.cast"
GIF="docs/media/robe-analyze.gif"

echo "Recording — makes live ARES/ISIR/ADIS/Sbirka listin calls; keep it under ~20s."
asciinema rec --overwrite --cols 100 --rows 30 \
  --command 'python3 scripts/demo_analyze.py' \
  "$CAST"

agg --cols 100 --rows 30 "$CAST" "$GIF"
echo "Wrote $GIF ($(du -h "$GIF" | cut -f1)). Target: <5 MB. report-card.png is a manual Claude Desktop screenshot."
