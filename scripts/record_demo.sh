#!/usr/bin/env bash
# Records the Budvar 3-year analysis as an asciinema cast and renders a GIF.
# Requires: asciinema, agg (https://github.com/asciinema/agg). Not a runtime dep.
# Usage: scripts/record_demo.sh   (run from repo root, inside the venv)
set -euo pipefail

CAST="docs/media/budvar-3year.cast"
GIF="docs/media/budvar-3year.gif"

echo "Recording — the analyze command will run automatically; keep it <15s."
asciinema rec --overwrite --cols 100 --rows 30 \
  --command 'rejstrik analyze "Budejovicky Budvar" --years 3' \
  "$CAST"

agg --cols 100 --rows 30 "$CAST" "$GIF"
echo "Wrote $GIF ($(du -h "$GIF" | cut -f1)). Target: <5 MB. report-card.png is a manual Claude Desktop screenshot."
