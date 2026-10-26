#!/usr/bin/env bash
# Oracle/nop audit: is every task in the set a task at all?
#
# Harbor's `oracle` agent runs the reference solution; `nop` does nothing. For a
# task to be worth a single cent of agent time it must be green on both sides:
#   oracle passes  -> the task is solvable exactly as specified
#   nop fails      -> the verifier cannot be satisfied by doing nothing
# A task that fails oracle is broken (or its reference solution is), and a task
# that passes nop is vacuous. Both are task-side findings and neither costs tokens.
#
# Terminal-Bench images average ~0.65 GB and the full set is ~58 GB, which does not
# fit in the free space on this host. So the audit runs in batches and drops the
# images of the batch afterwards — except for the 24-task comparison set, which is
# kept warm for the next real run.
#
# Usage:
#   ./scripts/audit.sh [task-list] [batch-size]
#   KEEP_IMAGES=1 ./scripts/audit.sh      # never delete images
#   FORCE=1 ./scripts/audit.sh            # re-run batches that already have a job
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SOURCE="${1:-docs/tb2-all.txt}"
BATCH_SIZE="${2:-${BATCH_SIZE:-18}}"
N_CONCURRENT="${N_CONCURRENT:-3}"
OUT="${OUT:-results/audit}"
KEEP_IMAGES="${KEEP_IMAGES:-0}"
FORCE="${FORCE:-0}"

[ -f "$SOURCE" ] || { echo "audit: no task list at $SOURCE" >&2; exit 1; }
mkdir -p "$OUT/batches" "$OUT/jobs"

# Split into batches, keeping the comparison set first so its images stay warm.
python3 - "$SOURCE" "$OUT" "$BATCH_SIZE" <<'PY'
import pathlib, sys

source, out, size = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), int(sys.argv[3])
tasks = [l.split()[0] for l in source.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
keep = set()
subset = pathlib.Path("docs/tb2-subset-24.txt")
if subset.is_file():
    keep = {l.split()[0] for l in subset.read_text().splitlines() if l.strip() and not l.strip().startswith("#")}
ordered = [t for t in tasks if t in keep] + [t for t in tasks if t not in keep]
for old in (out / "batches").glob("batch-*.txt"):
    old.unlink()
batches = [ordered[i:i + size] for i in range(0, len(ordered), size)]
for i, batch in enumerate(batches, 1):
    (out / "batches" / f"batch-{i:02d}.txt").write_text("\n".join(batch) + "\n")
print(f"audit: {len(ordered)} tasks in {len(batches)} batches of <= {size}")
PY

drop_images() { # task...
  [ "$KEEP_IMAGES" = "1" ] && return 0
  local task ref
  for task in "$@"; do
    # Keep the comparison set warm: it is what the next real run needs.
    grep -qx "$task" docs/tb2-subset-24.txt 2>/dev/null && continue
    for ref in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "/${task}:" || true); do
      docker rmi "$ref" >/dev/null 2>&1 || true
    done
  done
}

already_done() { # batch-file -> a previous batch run recorded this one
  local marker="$OUT/jobs/$(basename "$1" .txt).job"
  [ -f "$marker" ] && [ "$FORCE" != "1" ]
}

for batch in "$OUT"/batches/batch-*.txt; do
  name="$(basename "$batch" .txt)"
  if already_done "$batch"; then
    echo "== $name already audited ($(cat "$OUT/jobs/$name.job")) — FORCE=1 to re-run"
    continue
  fi
  mapfile -t tasks < <(grep -v '^#' "$batch" | grep -v '^$')
  echo "== $name: ${#tasks[@]} tasks, agents oracle+nop, concurrency $N_CONCURRENT"
  TASK_FILE="$batch" N_CONCURRENT="$N_CONCURRENT" ./scripts/bench.sh run audit || {
    echo "audit: batch $name failed (harbor exit non-zero) — images kept for inspection" >&2
    exit 1
  }
  job="$(basename "$(ls -dt results/jobs/cab-audit-* 2>/dev/null | head -1)" 2>/dev/null || echo none)"
  echo "$job" > "$OUT/jobs/$name.job"
  echo "== $name -> $job"
  drop_images "${tasks[@]}"
done

echo
echo "audit: done. Report with:"
echo "  python3 scripts/bench_report.py audit \$(cat $OUT/jobs/*.job | sort -u)"
