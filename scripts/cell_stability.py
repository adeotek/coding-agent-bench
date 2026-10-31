#!/usr/bin/env python3
"""Derive each cell's measured stability from the job store.

Why this exists: a cell's pass/fail at one attempt is a single draw from that
cell's own rate, and this bench has four times written a cell-level claim from
one draw. On the 2026-10-30 k=3 check (`docs/tb2-noisebar.txt`), **10 of 24
(cell, agent) pairs were still split at three attempts**, and the sweep-to-sweep
swing (4-6 cells of 23 on unchanged binaries) is exactly what those rates must
produce. So the registry answers the only question that makes a cell usable in a
comparison: *how often does this agent pass it, over how many attempts?*

Output is derived, never hand-edited:

  docs/cell-stability.json   per (cell, agent) k/n, rate, Wilson interval, class
  docs/tb2-ranking.txt       the cells that can actually rank agents (>=2 agents
                             measured >=3 times with rates >= 0.33 apart)

Usage:
  python3 scripts/cell_stability.py                       # every job in the store
  python3 scripts/cell_stability.py --jobs a,b            # scope to jobs
  python3 scripts/cell_stability.py --print               # human table
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JOBS = REPO / "results" / "jobs"

# Reuse the reporting layer's loader and interval, so a rate in this file cannot
# disagree with the rate in `bench_report.py summary`.
_spec = importlib.util.spec_from_file_location("bench_report", REPO / "scripts" / "bench_report.py")
assert _spec and _spec.loader
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

MIN_ATTEMPTS = 3      # below this a rate is not evidence (0/n bounds a rate only at <=63 %)
SPREAD = 0.33         # a cell ranks agents only if their measured rates differ by at least this
# Harbor's own calibration agents: `nop` must fail every task and `oracle` must
# pass every task. Their 0/1 and 1/1 columns are a verifier audit, not an agent
# result, and folding them in would inflate every cell's spread.
CALIBRATION = {"nop", "oracle"}


def is_local_job(job: dict) -> bool:
    """True when the job ran a local dataset (`datasets[0].path`) instead of the registry.

    Repaired and authored cells are local-only by policy (tasks/README.md): their
    verdicts are about the verifier this repo wrote, not about terminal-bench, and
    folding them in would put e.g. `build-cython-ext` next to real cells as if the
    numbers were comparable. Harbor records the dataset in the job config, so the
    exclusion is derived rather than guessed from a job name.
    """
    datasets = (job.get("config") or {}).get("datasets") or []
    return bool(datasets) and "path" in datasets[0]


def collect(job_names: list[str], latest: bool = True) -> dict:
    """Fold the store into (task, agent) -> [k, n].

    With `latest` (the default) only the newest release of each agent counts: a
    rate that mixes v0.7.10, v0.7.11 and v0.7.12 answers no question anyone
    asks, and it hid exactly that when this registry printed moca 16/37 on
    `regex-chess`. The newest job name (which carries a timestamp) per agent
    picks its current version; `--all-versions` folds everything instead.
    """
    rows = []
    newest: dict[str, tuple[str, str]] = {}
    local_skipped: list[str] = []
    for name in job_names:
        job = bench.load_job(JOBS, name)
        if is_local_job(job):
            local_skipped.append(name)
            continue
        for row in job["rows"]:
            agent = row["agent"]
            if agent in CALIBRATION:
                continue
            version = row.get("version") or "?"
            rows.append((row["task"] or "?", agent, version, bench.verdict(row) == "P"))
            if name > newest.get(agent, ("", ""))[0]:
                newest[agent] = (name, version)
    current = {agent: version for agent, (_, version) in newest.items()}
    acc: dict[tuple[str, str], list[int]] = {}
    versions: dict[str, set[str]] = {}
    trials = 0
    for task, agent, version, passed in rows:
        if latest and current.get(agent) not in (None, "?") and version != current[agent]:
            continue
        slot = acc.setdefault((task, agent), [0, 0])
        slot[1] += 1
        if passed:
            slot[0] += 1
        versions.setdefault(agent, set()).add(version)
        trials += 1
    return {
        "acc": acc,
        "versions": versions,
        "trials": trials,
        "current": current,
        "local_skipped": local_skipped,
    }


def classify(k: int, n: int) -> str:
    if n < MIN_ATTEMPTS:
        return "insufficient"      # includes every single draw
    if k == 0:
        return "fails"
    if k == n:
        return "passes"
    return "flaky"


def build(job_names: list[str], latest: bool = True) -> dict:
    data = collect(job_names, latest)
    task_side = bench.task_side_tasks(REPO)
    cells: dict[str, dict] = {}
    for (task, agent), (k, n) in data["acc"].items():
        lo, hi = bench.wilson(k, n)
        cells.setdefault(task, {"agents": {}})["agents"][agent] = {
            "k": k,
            "n": n,
            "rate": round(k / n, 4) if n else None,
            "ci": [round(lo, 4), round(hi, 4)],
            "class": classify(k, n),
            "versions": sorted(data["versions"].get(agent, [])),
        }
    for task, cell in cells.items():
        measured = [a for a in cell["agents"].values() if a["n"] >= MIN_ATTEMPTS]
        rates = [a["rate"] for a in measured]
        spread = round(max(rates) - min(rates), 4) if len(rates) >= 2 else None
        cell["spread"] = spread
        # A cell ranks agents only when it has been measured enough for two agents
        # AND they actually differ: a unanimous cell (spread 0) is stable but
        # carries no ordering information, which is the saturated-set problem.
        # A task-side cell can never rank agents, however wide its spread: its
        # verdict tracks the verifier's own behaviour (a leftover artifact, an
        # upstream clone), not the agent. Evidence in docs/task-side.json.
        cell["task_side"] = task in task_side
        cell["ranking"] = bool(
            len(rates) >= 2 and spread is not None and spread >= SPREAD and not cell["task_side"]
        )
        cell["measured_agents"] = len(rates)
    return {
        "generated_from": {
            "jobs": job_names,
            "trials": data["trials"],
            "latest_only": latest,
            "current_version": data["current"],
            # Local datasets (repaired/authored cells) are in the store but not in
            # this registry: their numbers are not terminal-bench numbers.
            "local_jobs_skipped": data["local_skipped"],
        },
        "min_attempts": MIN_ATTEMPTS,
        "spread": SPREAD,
        "cells": cells,
    }


def ranking_cells(registry: dict) -> list[str]:
    return sorted(t for t, c in registry["cells"].items() if c["ranking"])


def render(registry: dict) -> str:
    agents = sorted({a for c in registry["cells"].values() for a in c["agents"]})
    width = max(len(t) for t in registry["cells"]) if registry["cells"] else 10
    out = [f"{'cell':{width}} " + " ".join(f"{a:>10}" for a in agents) + "   ranking"]
    for task in sorted(registry["cells"]):
        cell = registry["cells"][task]
        row = []
        for agent in agents:
            a = cell["agents"].get(agent)
            row.append(f"{(str(a['k']) + '/' + str(a['n'])) if a else '—':>10}")
        mark = "RANK" if cell["ranking"] else ("task-side" if cell["task_side"] else "no")
        out.append(f"{task:{width}} " + " ".join(row) + f"   {mark}")
    return "\n".join(out)


def ranking_file(registry: dict) -> str:
    lines = [
        "# The cells that can rank agents, derived — never hand-edited.",
        "#",
        f"# Generated by scripts/cell_stability.py from {registry['generated_from']['trials']} trials",
        f"# in {len(registry['generated_from']['jobs'])} jobs. A cell qualifies when at least two",
        f"# agents have >={registry['min_attempts']} attempts and their measured rates differ by",
        f">= {registry['spread']:.2f} — a cell everyone passes is stable and useless for ordering,",
        "# which is why the saturated sets could never rank anyone.",
        "#",
        "# Regenerate: python3 scripts/cell_stability.py",
    ]
    cells = ranking_cells(registry)
    if not cells:
        lines.append("# (no cell currently qualifies — buy k>=3 on the discriminating cells first)")
    for task in cells:
        cell = registry["cells"][task]
        rates = ", ".join(
            f"{a} {v['k']}/{v['n']}" for a, v in sorted(cell["agents"].items()) if v["n"] >= registry["min_attempts"]
        )
        lines.append(f"#   {task}: {rates} (spread {cell['spread']:.2f})")
        lines.append(task)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", help="comma-separated job names (default: every job in results/jobs)")
    ap.add_argument("--json", default=str(REPO / "docs" / "cell-stability.json"))
    ap.add_argument("--ranking", default=str(REPO / "docs" / "tb2-ranking.txt"))
    ap.add_argument("--print", action="store_true", dest="show")
    ap.add_argument("--all-versions", action="store_true",
                    help="fold every release of an agent instead of only its newest")
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    opts = ap.parse_args(argv)

    if opts.jobs:
        names = [n.strip() for n in opts.jobs.split(",") if n.strip()]
    else:
        names = sorted(d.name for d in JOBS.iterdir() if d.is_dir()) if JOBS.is_dir() else []
    if not names:
        sys.exit("cell_stability: no jobs in results/jobs — run something first")

    registry = build(names, latest=not opts.all_versions)
    if opts.show or opts.dry_run:
        print(render(registry))
        print()
        print(f"ranking cells: {len(ranking_cells(registry))} of {len(registry['cells'])}")
    if opts.dry_run:
        return 0
    Path(opts.json).write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
    Path(opts.ranking).write_text(ranking_file(registry))
    print(
        f"cell_stability: {len(registry['cells'])} cells from {registry['generated_from']['trials']} trials "
        f"-> {opts.json}, {opts.ranking} ({len(ranking_cells(registry))} ranking-capable)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
