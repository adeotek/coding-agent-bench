#!/usr/bin/env bash
# Run one profile as N sequential shards, pruning images between them.
#
# Why this exists: the 89-task Terminal-Bench set needs ~145 GB of images
# uncompressed on disk, and Harbor keeps every image for the life of a job. A
# 96 GB host cannot run that as one job — but it can run it as slices, because
# each shard is an ordinary job with its own manifest, and `bench_report.py`
# stitches them back together by task.
#
# Usage:  ./scripts/sharded_run.sh <profile> <shards> [extra harbor args...]
#   TASK_FILE=docs/tb2-all.txt ./scripts/sharded_run.sh full 5
#
# Env:    CONTINUE=1     keep going when a shard fails (default: stop, so a
#                        broken slice does not burn the whole set's tokens)
#         PRUNE=0        do not prune images between shards
#         FREE_MIN_GB    refuse to start a shard below this much free space (12)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
# shellcheck disable=SC1091
[ -f .env ] && set -a && . ./.env && set +a

profile="${1:-}"; shards="${2:-}"
if [ -z "$profile" ] || [ -z "$shards" ]; then
  echo "usage: $0 <profile> <shards> [extra harbor args...]" >&2
  exit 2
fi
shift 2 || true
case "$shards" in ''|*[!0-9]*) echo "sharded_run: shards must be a positive integer" >&2; exit 2 ;; esac
[ "$shards" -ge 1 ] || { echo "sharded_run: shards must be >= 1" >&2; exit 2; }

free_gb() { df -Pk / | awk 'NR==2{print int($4/1048576)}'; }

failed=0
for k in $(seq 1 "$shards"); do
  free="$(free_gb)"
  if [ "$free" -lt "${FREE_MIN_GB:-12}" ]; then
    echo "sharded_run: only ${free}G free before shard $k — prune or free space first" >&2
    failed=1
    [ "${CONTINUE:-0}" = "1" ] || break
    continue
  fi
  echo "===== shard $k/$shards (${free}G free)" >&2
  if ! SHARD="$k/$shards" ./scripts/bench.sh run "$profile" "$@"; then
    echo "sharded_run: shard $k/$shards FAILED" >&2
    failed=1
    [ "${CONTINUE:-0}" = "1" ] || break
  fi
  if [ "${PRUNE:-1}" = "1" ] && [ "$k" -lt "$shards" ]; then
    # Harbor leaves images behind for the job's lifetime; the whole point of
    # sharding is that the next shard gets the space back.
    printf 'sharded_run: pruning images and dead containers\n' >&2
    docker container prune -f >/dev/null 2>&1 || true
    docker image prune -af --filter "label!=keep" >/dev/null 2>&1 || true
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "sharded_run: at least one shard failed — re-run the missing shards; results are per-job, nothing was lost" >&2
  exit 1
fi
echo "sharded_run: all $shards shards finished" >&2
echo "next: python3 scripts/bench_report.py report \$(ls -d results/jobs/cab-$profile-s*of$shards-* | xargs -n1 basename)" >&2
