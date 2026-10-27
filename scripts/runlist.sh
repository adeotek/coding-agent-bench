#!/usr/bin/env bash
# Derive the run lists from the audit — the only place that decides what may be measured.
#
#   docs/tb2-measurable.txt  cells whose oracle passes HERE (a pass means work was done)
#   docs/tb2-watch.txt       cells that are not healthy — re-audit, never score
#
# Both are generated from the audit job store, so they cannot drift from the evidence;
# and `render_config.py` refuses (well, drops, loudly) a cell that is on the watch list,
# which is what stops a broken task from quietly costing tokens in the next round.
#
# Usage:
#   ./scripts/runlist.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Every audit marker, from both the main sweep and the watch re-checks.
jobs="$(find results -path '*/audit*/jobs/*.job' -exec cat {} + 2>/dev/null | sort -u || true)"
if [ -z "$jobs" ]; then
  echo "runlist: no audit markers — run ./scripts/audit.sh first" >&2
  exit 1
fi

python3 scripts/bench_report.py runlist $jobs --out=docs/tb2-measurable.txt
python3 scripts/bench_report.py runlist $jobs --watch --out=docs/tb2-watch.txt
