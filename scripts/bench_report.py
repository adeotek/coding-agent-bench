#!/usr/bin/env python3
"""Read the Harbor job store and print the tables the two bench reports are made of.

`results/jobs/<job>/<trial>/result.json` is the ground truth for every number in
`docs/moca-bench-report.md` and `docs/agents-bench-report.md` — never the prose of
an earlier report. This script is the mechanical half of the update procedure:
re-derive, paste, then write the diagnosis by hand.

Usage
-----
  scripts/bench_report.py runs                 one line per job
  scripts/bench_report.py summary <job>...     per-agent efficiency for jobs
  scripts/bench_report.py matrix <job>...      task x job pass matrix
  scripts/bench_report.py steps <job>...       per-trial step/tool accounting
  scripts/bench_report.py compare <job>...     paired per-task deltas, bootstrap CI, McNemar
  scripts/bench_report.py credit <job>...      partial credit from verifier ctrf.json
  scripts/bench_report.py export <job>...      summary.json per job (trials + manifest + aggregates)
  scripts/bench_report.py report <job>...      generated markdown (leaderboard, matrix, verdicts)
  scripts/bench_report.py diff <job> <task>    per-agent behaviour diff for one cell
  scripts/bench_report.py audit <job>...       oracle/nop task-quality audit
  scripts/bench_report.py json <job>...        raw rows (for ad-hoc analysis)

Rewards are read from `verifier_result.rewards.reward` (a dict — reading
`verifier_result.reward` yields None for every trial). A trial is PASS at
reward >= 1, FAIL at 0.0, and `?` when the verifier produced no verdict at all
(a verifier exception), which must never be folded into "fail".

`compare` is the only command that makes a *claim*: it pairs agents by task (every
agent runs the same cells), bootstraps over tasks — never over trials, because
repeats inside one task are correlated — and runs an exact McNemar test on the
discordant cells. A delta whose CI straddles zero is not a finding.

`steps` reads the agent-side transcript, not result.json: moca's
`agent/moca-session.jsonl` (one record per assistant turn, each with its own
`usage`) and the other agents' `agent/trajectory.json` (ATIF, one step per
turn, per-step `metrics`). Both are counted as *turns* — one model response
plus its tool calls — so the numbers are comparable; a step is not a tool call.

"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds(start: str | None, end: str | None) -> float | None:
    a, b = parse_ts(start), parse_ts(end)
    return (b - a).total_seconds() if a and b else None


def trial_rows(job_dir: Path) -> list[dict]:
    rows = []
    for trial_dir in sorted(job_dir.iterdir()):
        result = trial_dir / "result.json"
        if not trial_dir.is_dir() or not result.exists():
            continue
        try:
            data = json.loads(result.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        info = data.get("agent_info") or {}
        agent_result = data.get("agent_result") or {}
        rewards = (data.get("verifier_result") or {}).get("rewards") or {}
        execution = data.get("agent_execution") or {}
        rows.append(
            {
                "task": data.get("task_name"),
                "trial": data.get("trial_name"),
                "agent": info.get("name") or "?",
                "version": info.get("version"),
                "model": (info.get("model_info") or {}).get("name"),
                "reward": rewards.get("reward") if isinstance(rewards, dict) else None,
                "exception": (data.get("exception_info") or {}).get("exception_type"),
                "input_tokens": agent_result.get("n_input_tokens") or 0,
                "cache_tokens": agent_result.get("n_cache_tokens") or 0,
                "output_tokens": agent_result.get("n_output_tokens") or 0,
                "cost_usd": agent_result.get("cost_usd") or 0.0,
                "agent_seconds": seconds(execution.get("started_at"), execution.get("finished_at")),
                "trial_seconds": seconds(data.get("started_at"), data.get("finished_at")),
            }
        )
    return rows


def load_job(jobs_dir: Path, name: str) -> dict:
    job_dir = jobs_dir / name
    if not job_dir.is_dir():
        sys.exit(f"bench_report: no such job: {job_dir}")
    config = {}
    if (job_dir / "config.json").exists():
        config = json.loads((job_dir / "config.json").read_text())
    datasets = config.get("datasets") or []
    tasks = datasets[0].get("task_names") if datasets else None
    return {
        "name": name,
        "config": config,
        "n_tasks": len(tasks) if tasks else (datasets[0].get("n_tasks") if datasets else None),
        "rows": trial_rows(job_dir),
    }


def job_list(jobs_dir: Path) -> list[dict]:
    return [load_job(jobs_dir, d.name) for d in sorted(jobs_dir.iterdir()) if d.is_dir()]


def verdict(row: dict) -> str:
    reward = row["reward"]
    if reward is None:
        return "?"
    return "P" if reward >= 1 else "F"


def agents_label(job: dict) -> str:
    parts = []
    for agent in job["config"].get("agents") or []:
        version = (agent.get("kwargs") or {}).get("version") or "?"
        parts.append(f"{agent.get('name') or agent.get('import_path', '?').split(':')[-1]}@{version}")
    return ",".join(parts)


def cmd_runs(jobs_dir: Path, _args: list[str]) -> None:
    print("| job | agents | attempts | tasks | trials | pass | fail | no verdict | spend |")
    print("|---|---|---|---|---|---|---|---|---|")
    for job in job_list(jobs_dir):
        rows = job["rows"]
        if not rows:
            continue
        passed = sum(1 for r in rows if verdict(r) == "P")
        failed = sum(1 for r in rows if verdict(r) == "F")
        unknown = sum(1 for r in rows if verdict(r) == "?")
        spend = sum(r["cost_usd"] for r in rows)
        # Older job configs record `n_tasks` instead of the explicit `task_names`,
        # so fall back to the distinct tasks actually present in the trials.
        n_tasks = job["n_tasks"] or len({r["task"] for r in rows}) or "?"
        print(
            f"| `{job['name']}` | {agents_label(job)} | {job['config'].get('n_attempts', 1)} "
            f"| {n_tasks} | {len(rows)} | {passed} | {failed} | {unknown} "
            f"| ${spend:.4f} |"
        )


def cmd_summary(jobs_dir: Path, args: list[str]) -> None:
    for name in args:
        job = load_job(jobs_dir, name)
        print(f"\n### {name} — {agents_label(job)}\n")
        print("| agent | solved | cost | $/solved | input tokens | tok/solved | median agent run | median trial |")
        print("|---|---|---|---|---|---|---|---|")
        agents = sorted({r["agent"] for r in job["rows"]})
        for agent in agents:
            rows = [r for r in job["rows"] if r["agent"] == agent]
            passed = sum(1 for r in rows if verdict(r) == "P")
            cost = sum(r["cost_usd"] for r in rows)
            tokens = sum(r["input_tokens"] for r in rows)
            agent_s = [r["agent_seconds"] for r in rows if r["agent_seconds"]]
            trial_s = [r["trial_seconds"] for r in rows if r["trial_seconds"]]
            per_solved = f"${cost / passed:.4f}" if passed else "—"
            tok_solved = f"{tokens / passed / 1e6:.2f} M" if passed else "—"
            med_agent = f"{statistics.median(agent_s):.0f}s" if agent_s else "—"
            med_trial = f"{statistics.median(trial_s):.0f}s" if trial_s else "—"
            print(
                f"| {agent} | {passed}/{len(rows)} | ${cost:.4f} | {per_solved} "
                f"| {tokens / 1e6:.2f} M | {tok_solved} | {med_agent} | {med_trial} |"
            )


def cmd_matrix(jobs_dir: Path, args: list[str]) -> None:
    jobs = [load_job(jobs_dir, name) for name in args]
    tasks = sorted({r["task"] for job in jobs for r in job["rows"]})
    # A fixed, stated agent order. Trial directories are named task__<random>, so
    # iterating them in path order produced letters whose agent order changed per
    # task — unreadable, and easy to misreport (claude-code's db-wal loss read as
    # a pi loss). Letters are now grouped by agent, alphabetically, with attempts
    # in trial order inside a group; a missing agent shows as a dot.
    agents = sorted({r["agent"] for job in jobs for r in job["rows"]})
    columns = [f"{job['name']}" for job in jobs]
    print("| task | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    for task in tasks:
        cells = []
        for job in jobs:
            rows = [r for r in job["rows"] if r["task"] == task]
            if not rows:
                cells.append("—")
                continue
            by_agent: dict[str, list[str]] = {}
            for r in sorted(rows, key=lambda r: (r["agent"], r["trial"] or "")):
                by_agent.setdefault(r["agent"], []).append(verdict(r))
            cells.append(
                " ".join(
                    "".join(by_agent[a]) if a in by_agent else "·" for a in agents
                )
            )
        print(f"| {task} | " + " | ".join(cells) + " |")
    print()
    print("letters are grouped by agent, in this order: " + " · ".join(agents) +
          " (attempts in trial order inside a group; `·` = no trial for that agent)")


def _short_exc(name: str | None) -> str:
    if not name:
        return "—"
    return {
        "NonZeroAgentExitCodeError": "exit3",
        "VerifierTimeoutError": "v-timeout",
        "ApiRateLimitError": "rate-limit",
        "AgentTimeoutError": "a-timeout",
    }.get(name, name)


def _moca_steps(path: Path) -> dict | None:
    """Turn accounting from moca's session JSONL (one assistant message = one turn)."""
    turns = tools = 0
    input_tokens = output_tokens = 0
    cost = 0.0
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = rec.get("type")
        if kind == "tool_use":
            tools += 1
        elif kind == "message":
            message = rec.get("message") or {}
            if message.get("role") != "assistant":
                continue
            turns += 1
            usage = rec.get("usage") or {}
            input_tokens += int(usage.get("input") or 0) + int(usage.get("cacheRead") or 0)
            output_tokens += int(usage.get("output") or 0)
            cost += float(rec.get("cost") or 0.0)
    if not turns:
        return None
    return {
        "turns": turns,
        "tools": tools,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }


def _atif_steps(path: Path) -> dict | None:
    """Turn accounting from an ATIF trajectory (one `source: agent` step = one turn)."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    steps = [s for s in (data.get("steps") or []) if s.get("source") == "agent"]
    if not steps:
        return None
    final = data.get("final_metrics") or {}
    metrics = [s.get("metrics") or {} for s in steps]

    def total(key: str) -> int:
        return int(sum(int(m.get(key) or 0) for m in metrics))

    input_tokens = int(final.get("total_prompt_tokens") or total("prompt_tokens"))
    return {
        "turns": len(steps),
        "tools": sum(len(s.get("tool_calls") or []) for s in steps),
        "input_tokens": input_tokens,
        "output_tokens": int(final.get("total_completion_tokens") or total("completion_tokens")),
        "cost": float(final.get("total_cost_usd") or sum(float(m.get("cost_usd") or 0) for m in metrics)),
    }


def step_row(trial_dir: Path, row: dict) -> dict | None:
    agent_dir = trial_dir / "agent"
    stats = None
    if (agent_dir / "moca-session.jsonl").exists():
        stats = _moca_steps(agent_dir / "moca-session.jsonl")
    elif (agent_dir / "trajectory.json").exists():
        stats = _atif_steps(agent_dir / "trajectory.json")
    if stats is None:
        return None
    stats.update(
        task=row["task"],
        trial=row["trial"],
        agent=row["agent"],
        reward=row["reward"],
        exception=row["exception"],
        agent_seconds=row["agent_seconds"],
        cost_usd=row["cost_usd"],
    )
    return stats


def _cap_for(agent: str, caps: dict[str, int]) -> int | None:
    """Resolve an agent's step cap. Custom agents are labelled by their class
    (`agents.moca:Moca` -> `Moca`) while result.json carries the registry name
    (`moca`), so match exactly first, then by prefix.
    """
    for label, cap in caps.items():
        if agent.lower() == label.lower():
            return cap
    for label, cap in caps.items():
        if label.lower().startswith(agent.lower()) or agent.lower().startswith(label.lower()):
            return cap
    return None


def cmd_steps(jobs_dir: Path, args: list[str]) -> None:
    for name in args:
        job_dir = jobs_dir / name
        job = load_job(jobs_dir, name)
        caps = {}
        for agent in job["config"].get("agents") or []:
            label = agent.get("name") or agent.get("import_path", "?").split(":")[-1]
            max_steps = (agent.get("kwargs") or {}).get("max_steps")
            if max_steps:
                caps[label] = int(max_steps)
        rows = []
        for trial_dir in sorted(job_dir.iterdir()):
            if not trial_dir.is_dir():
                continue
            matches = [r for r in job["rows"] if r["trial"] == trial_dir.name]
            if not matches:
                continue
            stats = step_row(trial_dir, matches[0])
            if stats:
                rows.append(stats)
        print(f"\n### {name} — steps per trial ({len(rows)} with a transcript)\n")
        if not rows:
            print("no transcripts found (moca-session.jsonl / trajectory.json)\n")
            continue
        print("| task | agent | turns | tools | in tokens | out tokens | tok/turn | cost | agent s | verdict | exception |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: (r["agent"], r["task"] or "")):
            tok_turn = f"{r['input_tokens'] / r['turns'] / 1000:.1f} K" if r["turns"] else "—"
            cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] else "—"
            secs = f"{r['agent_seconds']:.0f}" if r["agent_seconds"] else "—"
            print(
                f"| {r['task']} | {r['agent']} | {r['turns']} | {r['tools']} "
                f"| {r['input_tokens'] / 1000:.0f} K | {r['output_tokens'] / 1000:.1f} K "
                f"| {tok_turn} | {cost} | {secs} | {verdict(r)} | {_short_exc(r['exception'])} |"
            )
        print("\n| agent | trials | median turns | p90 turns | max turns | cap | median tools | at cap |")
        print("|---|---|---|---|---|---|---|---|")
        for agent in sorted({r["agent"] for r in rows}):
            agent_rows = [r for r in rows if r["agent"] == agent]
            turns = [r["turns"] for r in agent_rows]
            tools = [r["tools"] for r in agent_rows]
            cap = _cap_for(agent, caps)
            at_cap = sum(1 for t in turns if cap and t >= 0.9 * cap)
            p90 = sorted(turns)[min(len(turns) - 1, int(round(0.9 * (len(turns) - 1))))]
            print(
                f"| {agent} | {len(agent_rows)} | {statistics.median(turns):.0f} | {p90} "
                f"| {max(turns)} | {cap or '—'} | {statistics.median(tools):.0f} "
                f"| {at_cap if cap else '—'} |"
            )
        slow = [r for r in rows if verdict(r) == "F"]
        if slow:
            print("\nfailed trials, by turns spent:")
            for r in sorted(slow, key=lambda r: -r["turns"]):
                print(f"- {r['task']} / {r['agent']}: {r['turns']} turns, "
                      f"{r['tools']} tools, {r['input_tokens'] / 1e6:.2f} M in, "
                      f"{_short_exc(r['exception'])}")
        print()


# --- compare: paired per-task statistics -------------------------------------
#
# Everything below is deliberately stdlib and deterministic: a fixed seed means
# the same job store always produces the same CI, so a report line can be
# re-derived by anyone who has the results directory.


def task_outcomes(jobs: list[dict]) -> dict[str, dict[str, list[float]]]:
    """task -> agent -> [1.0 pass, 0.0 fail, None no-verdict] over every trial."""
    out: dict[str, dict[str, list[float | None]]] = {}
    for job in jobs:
        for row in job["rows"]:
            v = verdict(row)
            value = None if v == "?" else (1.0 if v == "P" else 0.0)
            out.setdefault(row["task"], {}).setdefault(row["agent"], []).append(value)
    return out


def task_rate(values: list[float | None]) -> float | None:
    scored = [v for v in values if v is not None]
    return sum(scored) / len(scored) if scored else None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _percentile(sorted_xs: list[float], q: float) -> float:
    if not sorted_xs:
        return 0.0
    pos = q * (len(sorted_xs) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def cluster_bootstrap(values: list[float], iters: int, seed: int) -> tuple[float, float]:
    """95 % CI for the mean of per-task values, resampling TASKS with replacement.

    Resampling trials instead would shrink the interval by a factor of sqrt(k)
    and claim precision the design does not have: repeats inside one task share
    the task's difficulty.
    """
    import random

    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iters):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (_percentile(means, 0.025), _percentile(means, 0.975))


def mcnemar_exact(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar p-value (binomial on the discordant cells)."""
    from math import comb

    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def agent_scores(outcomes: dict[str, dict[str, list[float | None]]]) -> dict[str, dict]:
    agents = sorted({a for per_task in outcomes.values() for a in per_task})
    scores = {}
    for agent in agents:
        rates = [r for r in (task_rate(per_task.get(agent) or []) for per_task in outcomes.values()) if r is not None]
        no_verdict = sum(
            1
            for per_task in outcomes.values()
            for v in (per_task.get(agent) or [])
            if v is None
        )
        scores[agent] = {"tasks": len(rates), "score": _mean(rates), "rates": rates, "no_verdict": no_verdict}
    return scores


def pairwise(outcomes: dict[str, dict[str, list[float | None]]], agents: list[str], iters: int, seed: int) -> list[dict]:
    pairs = []
    for i, a in enumerate(agents):
        for b in agents[i + 1 :]:
            deltas, a_only, b_only = [], 0, 0
            for per_task in outcomes.values():
                ra, rb = task_rate(per_task.get(a) or []), task_rate(per_task.get(b) or [])
                if ra is None or rb is None:
                    continue
                deltas.append(ra - rb)
                if ra >= 0.5 and rb < 0.5:
                    a_only += 1
                elif rb >= 0.5 and ra < 0.5:
                    b_only += 1
            lo, hi = cluster_bootstrap(deltas, iters, seed)
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "n": len(deltas),
                    "delta": _mean(deltas),
                    "lo": lo,
                    "hi": hi,
                    "a_only": a_only,
                    "b_only": b_only,
                    "p": mcnemar_exact(a_only, b_only),
                }
            )
    return pairs


def flip_rate(jobs: list[dict]) -> dict:
    """How often the same (task, agent) changes verdict between otherwise identical jobs."""
    seen: dict[tuple[str, str], list[str]] = {}
    for job in jobs:
        for row in job["rows"]:
            seen.setdefault((row["task"], row["agent"]), []).append(verdict(row))
    cells = {k: v for k, v in seen.items() if len(v) > 1}
    flips = {k: v for k, v in cells.items() if len(set(v)) > 1}
    return {"cells": len(cells), "flips": len(flips), "detail": flips}


def manifest_warnings(jobs_dir: Path, jobs: list[dict]) -> list[str]:
    """Flag comparisons that mix toolchains, knobs or task sets.

    A job without a manifest cannot be checked at all — say so rather than assume
    it matched.
    """
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("cab_manifest", Path(__file__).with_name("manifest.py"))
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return []
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seen: dict[str, dict | None] = {}
    for job in jobs:
        path = jobs_dir / job["name"] / "manifest.json"
        seen[job["name"]] = json.loads(path.read_text()) if path.is_file() else None
    missing = [n for n, m in seen.items() if m is None]
    warnings = []
    if missing:
        warnings.append(f"no manifest for {', '.join(missing)} — toolchain unverified, comparison unchecked")
    present = {n: mod.comparable(m) for n, m in seen.items() if m}
    if len(present) > 1:
        names = list(present)
        base = present[names[0]]
        for other in names[1:]:
            for key in base:
                if present[other].get(key) != base.get(key):
                    warnings.append(f"{key} differs: {names[0]}={base.get(key)!r} vs {other}={present[other].get(key)!r}")
    return warnings

def cmd_compare(jobs_dir: Path, args: list[str]) -> None:
    names, iters, seed, as_json = [], 10000, 0, False
    for arg in args:
        if arg == "--json":
            as_json = True
        elif arg.startswith("--iters="):
            iters = int(arg.split("=", 1)[1])
        elif arg.startswith("--seed="):
            seed = int(arg.split("=", 1)[1])
        else:
            names.append(arg)
    if not names:
        sys.exit("usage: bench_report.py compare <job>... [--json] [--iters=N] [--seed=N]")

    jobs = [load_job(jobs_dir, n) for n in names]
    outcomes = task_outcomes(jobs)
    scores = agent_scores(outcomes)
    agents = sorted(scores, key=lambda a: -scores[a]["score"])
    pairs = pairwise(outcomes, agents, iters, seed)
    flips = flip_rate(jobs) if len(jobs) > 1 else None

    total_attempts = sum(len(v) for pt in outcomes.values() for v in pt.values())
    cells = sum(len(pt) for pt in outcomes.values())

    if as_json:
        print(
            json.dumps(
                {
                    "jobs": names,
                    "tasks": len(outcomes),
                    "attempts_per_task": total_attempts / cells if cells else 0,
                    "scores": {a: {"tasks": s["tasks"], "score": s["score"], "no_verdict": s["no_verdict"]} for a, s in scores.items()},
                    "pairs": pairs,
                    "flips": {"cells": flips["cells"], "flips": flips["flips"]} if flips else None,
                    "manifest_warnings": manifest_warnings(jobs_dir, jobs),
                },
                indent=1,
            )
        )
        return

    warn = manifest_warnings(jobs_dir, jobs)
    print(f"### paired comparison — {len(jobs)} job(s), {len(outcomes)} tasks, {cells} cells, {total_attempts} trials (iters={iters}, seed={seed})")
    if warn:
        print()
        for w in warn:
            print(f"> **WARNING** {w}")
    print()
    print("| agent | tasks | score | 95 % CI (task bootstrap) | no verdict |")
    print("|---|---|---|---|---|")
    for a in agents:
        s = scores[a]
        lo, hi = cluster_bootstrap(s["rates"], iters, seed)
        print(f"| {a} | {s['tasks']} | {s['score'] * 100:.1f} % | {lo * 100:.1f}–{hi * 100:.1f} % | {s['no_verdict']} |")
    print()
    print("| pair | Δ (pts) | 95 % CI | discordant (> / <) | McNemar p |")
    print("|---|---|---|---|---|")
    for p in pairs:
        # A CI that contains 0 is not a finding, whatever the point estimate says.
        mark = "excludes 0" if (p["lo"] > 0 or p["hi"] < 0) else "includes 0"
        print(
            f"| {p['a']} − {p['b']} | {p['delta'] * 100:+.1f} pts · {mark} "
            f"| {p['lo'] * 100:+.2f} … {p['hi'] * 100:+.2f} | {p['a_only']} / {p['b_only']} | {p['p']:.3f} |"
        )
    if flips:
        pct = 100 * flips["flips"] / flips["cells"] if flips["cells"] else 0.0
        print()
        print(f"**flip rate:** {flips['flips']} of {flips['cells']} cells ({pct:.1f} %) changed verdict between identical jobs")
        for (task, agent), vs in sorted(flips["detail"].items()):
            print(f"- `{task}` · {agent}: {' → '.join(vs)}")
    print()

# --- partial credit, export, report, diff ------------------------------------
#
# Binary reward is what Harbor records, but the verifier already wrote ctrf.json
# with every test's status. On the 24-task set that is 82 tests, so partial credit
# resolves ~3.4x finer than pass/fail (1.22 pts/test vs 4.2 pts/task). It is a
# secondary metric, not a replacement: a task is still solved or not.


def trial_dir(jobs_dir: Path, job: str, trial: str) -> Path:
    return jobs_dir / job / trial


def credit_of(jobs_dir: Path, job: str, trial: str) -> dict | None:
    """{passed, total, skipped, failed:[names]} from the verifier's ctrf.json."""
    path = trial_dir(jobs_dir, job, trial) / "verifier" / "ctrf.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    results = data.get("results") or {}
    tests = results.get("tests") or []
    if not tests:
        return None
    passed = sum(1 for t in tests if t.get("status") == "passed")
    skipped = sum(1 for t in tests if t.get("status") in ("skipped", "pending"))
    failed = [t.get("name") for t in tests if t.get("status") == "failed"]
    return {"passed": passed, "total": len(tests) - skipped, "skipped": skipped, "failed": failed}


def credit_map(jobs_dir: Path, jobs: list[dict]) -> dict[tuple[str, str], dict | None]:
    out: dict[tuple[str, str], dict | None] = {}
    for job in jobs:
        for row in job["rows"]:
            out[(job["name"], row["trial"])] = credit_of(jobs_dir, job["name"], row["trial"])
    return out


def credit_fraction(credit: dict | None) -> float | None:
    if not credit or not credit["total"]:
        return None
    return credit["passed"] / credit["total"]


def task_side_tasks(repo: Path) -> dict[str, str]:
    """Tasks with a *demonstrated verifier defect* — excluded from scores, kept in the set.

    `repo` may be the repository root or the JSON file itself; the registry lives
    at docs/task-side.json and every entry there must cite its evidence.
    """
    path = repo if repo.suffix == ".json" else repo / "docs" / "task-side.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return {k: (v.get("why") if isinstance(v, dict) else str(v)) for k, v in (data.get("tasks") or {}).items()}


def cmd_credit(jobs_dir: Path, args: list[str]) -> None:
    jobs = [load_job(jobs_dir, n) for n in args if not n.startswith("--")]
    credits = credit_map(jobs_dir, jobs)
    print(f"### partial credit — {', '.join(j['name'] for j in jobs)}")
    print()
    print("| agent | trials | tests | passed | credit | binary |")
    print("|---|---|---|---|---|---|")
    per_agent: dict[str, dict] = {}
    for job in jobs:
        for row in job["rows"]:
            c = credits.get((job["name"], row["trial"]))
            a = per_agent.setdefault(row["agent"], {"trials": 0, "tests": 0, "passed": 0, "binary": 0, "scored": 0})
            a["trials"] += 1
            if c:
                a["tests"] += c["total"]
                a["passed"] += c["passed"]
            v = verdict(row)
            if v != "?":
                a["scored"] += 1
                a["binary"] += 1 if v == "P" else 0
    for agent, a in sorted(per_agent.items(), key=lambda kv: -(kv[1]["passed"] / kv[1]["tests"] if kv[1]["tests"] else 0)):
        credit = 100 * a["passed"] / a["tests"] if a["tests"] else 0.0
        binary = 100 * a["binary"] / a["scored"] if a["scored"] else 0.0
        print(f"| {agent} | {a['trials']} | {a['tests']} | {a['passed']} | {credit:.1f} % | {binary:.1f} % |")
    print()


def export_job(jobs_dir: Path, job: dict, credits: dict, task_side: dict[str, str]) -> dict:
    manifest_path = jobs_dir / job["name"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None
    trials = []
    for row in job["rows"]:
        c = credits.get((job["name"], row["trial"]))
        trials.append(
            {
                "task": row["task"],
                "trial": row["trial"],
                "agent": row["agent"],
                "agent_version": row.get("version"),
                "model": row.get("model"),
                "verdict": verdict(row),
                "reward": row["reward"],
                "credit": credit_fraction(c),
                "tests": c,
                "task_side": row["task"] in task_side,
                "exception": row.get("exception"),
                "tokens": {
                    "input": row.get("input_tokens"),
                    "cache": row.get("cache_tokens"),
                    "output": row.get("output_tokens"),
                },
                "cost_usd": row.get("cost_usd"),
                "seconds": {"agent": row.get("agent_seconds"), "trial": row.get("trial_seconds")},
            }
        )
    by_agent: dict[str, dict] = {}
    for t in trials:
        a = by_agent.setdefault(
            t["agent"],
            {"trials": 0, "tasks": 0, "passes": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
             "credit_sum": 0.0, "credit_n": 0, "no_verdict": 0, "task_side": 0},
        )
        a["trials"] += 1
        if t["verdict"] == "?":
            a["no_verdict"] += 1
        else:
            a["tasks"] += 1
            a["passes"] += 1 if t["verdict"] == "P" else 0
        if t["task_side"]:
            a["task_side"] += 1
        a["cost_usd"] += t["cost_usd"] or 0.0
        a["input_tokens"] += t["tokens"]["input"] or 0
        a["output_tokens"] += t["tokens"]["output"] or 0
        if t["credit"] is not None:
            a["credit_sum"] += t["credit"]
            a["credit_n"] += 1
    for a in by_agent.values():
        a["score"] = a["passes"] / a["tasks"] if a["tasks"] else None
        a["credit"] = a["credit_sum"] / a["credit_n"] if a["credit_n"] else None
    return {
        "schema": 1,
        "job": job["name"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": str(REPO),
        "manifest": manifest,
        "config": job["config"],
        "task_side": sorted(task_side),
        "trials": trials,
        "by_agent": by_agent,
    }


def cmd_export(jobs_dir: Path, args: list[str]) -> None:
    names = [a for a in args if not a.startswith("--")]
    registry = next((a.split("=", 1)[1] for a in args if a.startswith("--task-side=")), REPO / "docs" / "task-side.json")
    task_side = task_side_tasks(Path(registry))
    jobs = [load_job(jobs_dir, n) for n in names]
    credits = credit_map(jobs_dir, jobs)
    for job in jobs:
        summary = export_job(jobs_dir, job, credits, task_side)
        out = jobs_dir / job["name"] / "summary.json"
        out.write_text(json.dumps(summary, indent=1) + "\n")
        print(f"summary: {out} ({len(summary['trials'])} trials)")


def _fmt_money(x: float | None) -> str:
    return "—" if x is None else f"${x:.4f}"


def _cost_stats(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return (0.0, 0.0, 0.0)
    s = sorted(values)
    p = lambda q: s[min(len(s) - 1, int(q * len(s)))]
    return (sum(s) / len(s), p(0.5), p(0.9))


def cmd_report(jobs_dir: Path, args: list[str]) -> None:
    include_task_side = "--include-task-side" in args
    out_path = next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), None)
    names = [a for a in args if not a.startswith("--")]
    registry = next((a.split("=", 1)[1] for a in args if a.startswith("--task-side=")), REPO / "docs" / "task-side.json")
    task_side = {} if include_task_side else task_side_tasks(Path(registry))
    jobs = [load_job(jobs_dir, n) for n in names]
    for job in jobs:
        if task_side:
            job["rows"] = [r for r in job["rows"] if r["task"] not in task_side]
    credits = credit_map(jobs_dir, jobs)
    outcomes = task_outcomes(jobs)
    scores = agent_scores(outcomes)
    agents = sorted(scores, key=lambda a: -scores[a]["score"])

    lines: list[str] = []
    add = lines.append
    add("<!-- generated by scripts/bench_report.py report — do not edit by hand -->")
    add("")
    add(f"# Bench run report — {', '.join(n for n in names)}")
    add("")
    for job in jobs:
        m = json.loads((jobs_dir / job["name"] / "manifest.json").read_text()) if (jobs_dir / job["name"] / "manifest.json").is_file() else None
        add(f"## `{job['name']}`")
        add("")
        if m:
            agents_desc = ", ".join(f"{a['id']}@{a.get('version') or '?'} ({a.get('model')})" for a in m.get("agents") or [])
            add(f"- **toolchain**: harbor {m['harbor']['version']} on python {m['harbor']['python']}, repo {(m.get('repo') or {}).get('short')}"
                f"{' (dirty)' if (m.get('repo') or {}).get('dirty') else ''}")
            add(f"- **agents**: {agents_desc}")
            add(f"- **dataset**: {m['dataset']['name']} {m['dataset']['version']}, {m['dataset']['n_tasks']} tasks, "
                f"{m['config'].get('n_attempts')} attempt(s), {m['config'].get('n_concurrent_trials')} concurrent")
            if m.get("duration_s"):
                add(f"- **wall clock**: {m['duration_s'] / 3600:.2f} h; trials recorded: {(m.get('trials') or {}).get('total')}")
        else:
            add("- **manifest**: absent (job predates manifests) — toolchain unverified")
        add("")

    add("## Leaderboard")
    add("")
    add("| agent | tasks | score | 95 % CI | credit | $/task | $ p50 / p90 | $/solved | no verdict |")
    add("|---|---|---|---|---|---|---|---|---|")
    for a in agents:
        s = scores[a]
        lo, hi = cluster_bootstrap(s["rates"], 10000, 0)
        costs, credits_list = [], []
        for job in jobs:
            for row in job["rows"]:
                if row["agent"] != a:
                    continue
                costs.append(row.get("cost_usd") or 0.0)
                cf = credit_fraction(credits.get((job["name"], row["trial"])))
                if cf is not None:
                    credits_list.append(cf)
        mean_cost, p50, p90 = _cost_stats(costs)
        spent = sum(costs)
        solved = sum(1 for job in jobs for row in job["rows"] if row["agent"] == a and verdict(row) == "P")
        per_solved = spent / solved if solved else None
        credit_pct = f"{100 * sum(credits_list) / len(credits_list):.1f} %" if credits_list else "—"
        add(
            f"| {a} | {s['tasks']} | {s['score'] * 100:.1f} % | {lo * 100:.1f}–{hi * 100:.1f} % | {credit_pct} "
            f"| {_fmt_money(mean_cost)} | {_fmt_money(p50)} / {_fmt_money(p90)} | {_fmt_money(per_solved)} | {s['no_verdict']} |"
        )
    add("")

    add("## Per task")
    add("")
    header = "| task | " + " | ".join(agents) + " |"
    add(header)
    add("|---" * (len(agents) + 1) + "|")
    for task in sorted(outcomes):
        cells = []
        for a in agents:
            vals = outcomes[task].get(a) or []
            if not vals:
                cells.append("·")
            else:
                marks = "".join("✅" if v == 1.0 else ("⏱" if v is None else "❌") for v in vals)
                cells.append(marks)
        add(f"| `{task}` | " + " | ".join(cells) + " |")
    add("")

    pairs = pairwise(outcomes, agents, 10000, 0)
    add("## Paired comparisons")
    add("")
    add("| pair | Δ | 95 % CI | discordant (> / <) | McNemar p | verdict |")
    add("|---|---|---|---|---|---|")
    for p in pairs:
        excludes = p["lo"] > 0 or p["hi"] < 0
        claim = "better" if (excludes and p["delta"] > 0) else ("worse" if (excludes and p["delta"] < 0) else "undecided")
        add(
            f"| {p['a']} − {p['b']} | {p['delta'] * 100:+.1f} pts | {p['lo'] * 100:+.2f} … {p['hi'] * 100:+.2f} "
            f"| {p['a_only']} / {p['b_only']} | {p['p']:.3f} | **{claim}** |"
        )
    add("")
    if len(jobs) > 1:
        flips = flip_rate(jobs)
        pct = 100 * flips["flips"] / flips["cells"] if flips["cells"] else 0.0
        add(f"**Flip rate:** {flips['flips']} of {flips['cells']} cells ({pct:.1f} %) changed verdict between jobs.")
        add("")
    if task_side:
        add("## Excluded (task-side defects)")
        add("")
        for task, why in sorted(task_side.items()):
            add(f"- `{task}` — {why}")
        add("")
    text = "\n".join(lines) + "\n"
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"report: {path} ({len(lines)} lines)")
    else:
        print(text)


def cmd_diff(jobs_dir: Path, args: list[str]) -> None:
    names = [a for a in args if not a.startswith("--")]
    if len(names) < 2:
        sys.exit("usage: bench_report.py diff <job> <task>")
    job_name, task = names[0], names[1]
    job = load_job(jobs_dir, job_name)
    rows = [r for r in job["rows"] if r["task"] == task]
    if not rows:
        sys.exit(f"bench_report: no trials for {task} in {job_name}")
    credits = credit_map(jobs_dir, [job])
    print(f"### {task} — {job_name}")
    print()
    print("| agent | verdict | tests | failing | exception | in tok | out tok | cost | agent s |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: r["agent"]):
        c = credits.get((job_name, row["trial"])) or {}
        tests = f"{c.get('passed', '—')}/{c.get('total', '—')}" if c else "—"
        failing = ", ".join((c.get("failed") or [])[:3]) or "—"
        print(
            f"| {row['agent']} | {verdict(row)} | {tests} | {failing} | {row.get('exception') or '—'} "
            f"| {row.get('input_tokens') or 0} | {row.get('output_tokens') or 0} | {_fmt_money(row.get('cost_usd'))} "
            f"| {row.get('agent_seconds') or 0:.0f} |"
        )
    print()

# --- audit: is every task a task? -------------------------------------------
#
# `oracle` must pass (the reference solution works as specified) and `nop` must
# fail (doing nothing cannot satisfy the verifier). Anything else is a task-side
# finding, and the distinction matters:
#   oracle fails  -> broken task or broken reference solution
#   nop passes    -> vacuous verifier
#   no verdict    -> the trial never produced one; an infrastructure fact, not a
#                    task quality verdict, so it is reported separately.


def audit_rows(jobs: list[dict]) -> dict[str, dict[str, dict]]:
    """task -> agent -> row, from audit jobs only."""
    out: dict[str, dict[str, dict]] = {}
    for job in jobs:
        for row in job["rows"]:
            out.setdefault(row["task"], {})[row["agent"]] = row
    return out


def audit_classify(row_oracle: dict | None, row_nop: dict | None) -> str:
    o = verdict(row_oracle) if row_oracle else "-"
    n = verdict(row_nop) if row_nop else "-"
    if o == "?" or n == "?":
        return "no-verdict"
    if o == "P" and n == "F":
        return "healthy"
    if o == "F" and n == "P":
        return "both-broken"      # can't solve it as written, and doing nothing passes
    if o == "F":
        return "broken-task"      # oracle cannot satisfy the verifier
    if n == "P":
        return "vacuous"          # no work needed to pass
    return "unknown"


def cmd_audit(jobs_dir: Path, args: list[str]) -> None:
    names = [a for a in args if not a.startswith("--")]
    as_json = "--json" in args
    out_path = next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), None)
    if not names:
        sys.exit("usage: bench_report.py audit <job>... [--json] [--out=path]")
    jobs = [load_job(jobs_dir, n) for n in names]
    tasks = audit_rows(jobs)
    findings = []
    counts: dict[str, int] = {}
    for task in sorted(tasks):
        rows = tasks[task]
        cls = audit_classify(rows.get("oracle"), rows.get("nop"))
        counts[cls] = counts.get(cls, 0) + 1
        if cls != "healthy":
            findings.append(
                {
                    "task": task,
                    "class": cls,
                    "oracle": verdict(rows["oracle"]) if "oracle" in rows else "-",
                    "nop": verdict(rows["nop"]) if "nop" in rows else "-",
                    "oracle_exception": (rows.get("oracle") or {}).get("exception"),
                    "nop_exception": (rows.get("nop") or {}).get("exception"),
                }
            )
    payload = {
        "jobs": names,
        "tasks": len(tasks),
        "counts": counts,
        "findings": findings,
        "healthy": sorted(t for t in tasks if audit_classify(tasks[t].get("oracle"), tasks[t].get("nop")) == "healthy"),
    }
    if as_json:
        print(json.dumps(payload, indent=1))
        return

    print(f"### oracle/nop audit — {len(tasks)} tasks from {len(jobs)} job(s)")
    print()
    print("| class | tasks | meaning |")
    print("|---|---|---|")
    meanings = {
        "healthy": "oracle passes, nop fails — a real task",
        "broken-task": "oracle fails — unsolvable as specified, or its reference solution is",
        "vacuous": "nop passes — the verifier is satisfiable by doing nothing",
        "both-broken": "oracle fails AND nop passes — the worst case",
        "no-verdict": "a trial produced no verdict — infrastructure, inspect the exception",
        "unknown": "only one side ran — the audit is incomplete",
    }
    for cls in ("healthy", "broken-task", "vacuous", "both-broken", "no-verdict", "unknown"):
        if counts.get(cls):
            print(f"| {cls} | {counts[cls]} | {meanings[cls]} |")
    print()
    if findings:
        print("| task | class | oracle | nop | oracle exception | nop exception |")
        print("|---|---|---|---|---|---|")
        for f in findings:
            print(
                f"| `{f['task']}` | {f['class']} | {f['oracle']} | {f['nop']} "
                f"| {f['oracle_exception'] or '—'} | {f['nop_exception'] or '—'} |"
            )
        print()
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=1) + "\n")
        print(f"audit: {path}")

def cmd_json(jobs_dir: Path, args: list[str]) -> None:
    print(json.dumps([load_job(jobs_dir, name) for name in args], indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs-dir", default=str(REPO / "results" / "jobs"))
    parser.add_argument("command", choices=("runs", "summary", "matrix", "steps", "compare", "credit", "export", "report", "diff", "audit", "json"))
    parser.add_argument("jobs", nargs="*", help="job names (all commands except `runs`)")
    parser.add_argument("--json", action="store_true", help="compare: machine-readable output")
    parser.add_argument("--out", help="report: write to this path instead of stdout")
    parser.add_argument("--include-task-side", action="store_true", help="report/export: keep known task-side cells")
    parser.add_argument("--iters", type=int, default=10000, help="compare: bootstrap iterations (default 10000)")
    parser.add_argument("--seed", type=int, default=0, help="compare: bootstrap seed (default 0)")
    opts = parser.parse_args()
    jobs_dir = Path(opts.jobs_dir)
    if not jobs_dir.is_dir():
        sys.exit(f"bench_report: no job store at {jobs_dir}")
    if opts.command == "runs":
        cmd_runs(jobs_dir, opts.jobs)
    else:
        if not opts.jobs:
            sys.exit(f"bench_report: `{opts.command}` needs at least one job name")
        passthrough = []
        if opts.out:
            passthrough.append(f"--out={opts.out}")
        if opts.include_task_side:
            passthrough.append("--include-task-side")
        if opts.command == "compare":
            extra = [f"--iters={opts.iters}", f"--seed={opts.seed}"] + (["--json"] if opts.json else [])
            cmd_compare(jobs_dir, opts.jobs + extra)
        elif opts.command == "report":
            cmd_report(jobs_dir, opts.jobs + passthrough)
        elif opts.command in {"credit", "export", "diff", "audit"}:
            {"credit": cmd_credit, "export": cmd_export, "diff": cmd_diff, "audit": cmd_audit}[opts.command](
                jobs_dir, opts.jobs + passthrough
            )
        else:
            {"summary": cmd_summary, "matrix": cmd_matrix, "steps": cmd_steps,
             "json": cmd_json}[opts.command](jobs_dir, opts.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
