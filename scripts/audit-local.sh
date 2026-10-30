#!/bin/bash
# Oracle/nop audit of the cells this repo owns (tasks/repairs, tasks/authored).
#
# Costs no model tokens: Harbor's `oracle` runs each task's own solution, `nop` does nothing. A cell is
# healthy only when oracle PASSES and nop FAILS — that pair is the whole point, because a verifier that
# passes everything (or fails everything) cannot score an agent.
#
# Usage:
#   ./scripts/audit-local.sh                 # both directories
#   ./scripts/audit-local.sh tasks/authored  # one directory or one task dir
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO" || exit 1

HARBOR="${HARBOR:-$(uv tool dir)/harbor/bin/harbor}"
[ -x "$HARBOR" ] || HARBOR="$(command -v harbor || true)"
[ -n "$HARBOR" ] && [ -x "$HARBOR" ] || { echo "audit-local: harbor not found (uv tool install harbor)" >&2; exit 1; }

TARGETS=("$@")
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=("tasks/repairs" "tasks/authored")

STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p results/audit
LOG="results/audit/local-audit-${STAMP}.log"
: > "$LOG"

overall=0
for target in "${TARGETS[@]}"; do
  name=$(basename "${target%/}")
  cfg="results/effective-local-audit-${name}-${STAMP}.json"
  echo "== $target" | tee -a "$LOG"
  if ! LOCAL_TASKS="$target" python3 scripts/render_config.py audit -o "$cfg" >>"$LOG" 2>&1; then
    echo "   render failed (see $LOG)" | tee -a "$LOG"
    overall=1
    continue
  fi
  "$HARBOR" run --config "$cfg" -y --job-name "cab-local-audit-${name}" >>"$LOG" 2>&1
  rc=$?
  [ $rc -ne 0 ] && { echo "   harbor exited $rc" | tee -a "$LOG"; overall=1; }
  echo "   job: cab-local-audit-${name}" | tee -a "$LOG"
done

echo
echo "summary (oracle must be 1.0, nop must be 0.0):"
python3 - "$LOG" <<'PY'
import json
import pathlib
import sys

rows = []
for job in sorted(pathlib.Path("results/jobs").glob("cab-local-audit-*")):
    for trial in job.glob("*/result.json"):
        data = json.loads(trial.read_text())
        agent = (data.get("agent_info") or {}).get("name")
        reward = ((data.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        task = trial.parent.name.split("__")[0]
        rows.append((job.name, task, agent, reward))

latest = {}
for job, task, agent, reward in rows:
    latest.setdefault((task, agent), (job, reward))

bad = 0
seen = set()
for (task, agent), (job, reward) in sorted(latest.items()):
    seen.add((task, agent))
for task in sorted({t for (t, _a) in latest}):
    o = latest.get((task, "oracle"), (None, None))[1]
    n = latest.get((task, "nop"), (None, None))[1]
    ok = o == 1.0 and n == 0.0
    bad += 0 if ok else 1
    print(f"  {'OK  ' if ok else 'BAD '} {task:28} oracle={o} nop={n}")
print(f"\n{len({t for (t, _a) in latest})} cell(s), {bad} needing attention")
sys.exit(1 if bad else 0)
PY
exit $?
