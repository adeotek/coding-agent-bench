#!/usr/bin/env bash
# Re-audit the cells that are not healthy — the gate that keeps a rotten cell out
# of a paid round, or lets a repaired one back in.
#
# Zero tokens: this is oracle/nop only. Two classes are handled differently on
# purpose:
#
#   broken-task   the task or its reference solution is broken -> re-audit every round.
#                 Cells get fixed upstream ("build-cython-ext" rotted the other way in
#                 a single day), so this is how one earns its way back into the set.
#   host-limited  unmeasurable on THIS host (no /dev/kvm, a vCPU missing instructions).
#                 Re-running them here just reproduces the same failure, so they are
#                 skipped unless WATCH_ALL=1 — the trigger for those is a host change,
#                 not a round.
#
# Usage:
#   ./scripts/audit-watch.sh            # broken cells only
#   WATCH_ALL=1 ./scripts/audit-watch.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

./scripts/runlist.sh
watch=docs/tb2-watch.txt
[ -f "$watch" ] || { echo "audit-watch: $watch missing — run make runlist" >&2; exit 1; }

if [ "${WATCH_ALL:-0}" = "1" ]; then
  cells="$(grep -v '^#' "$watch" | grep -v '^$' || true)"
else
  cells="$(grep -v '^#' "$watch" | grep -v '^$' | grep -v 'host-limited$' || true)"
fi

if [ -z "$cells" ]; then
  echo "audit-watch: nothing to re-audit (all watch cells are host-limited; WATCH_ALL=1 to force)"
  exit 0
fi

# A separate marker store: overwriting the main sweep's batch-NN.job pointers would
# erase the evidence the run lists are derived from.
mkdir -p results/audit-watch/jobs
printf '%s\n' "$cells" | awk '{print $1}' > results/audit-watch/watch-list.txt
echo "audit-watch: re-auditing $(grep -c . results/audit-watch/watch-list.txt) cell(s)"
OUT=results/audit-watch ./scripts/audit.sh results/audit-watch/watch-list.txt 3

./scripts/runlist.sh
echo "audit-watch: done — anything whose oracle now passes is back in docs/tb2-measurable.txt"
