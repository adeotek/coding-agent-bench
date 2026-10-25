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
  scripts/bench_report.py json <job>...        raw rows (for ad-hoc analysis)

Rewards are read from `verifier_result.rewards.reward` (a dict — reading
`verifier_result.reward` yields None for every trial). A trial is PASS at
reward >= 1, FAIL at 0.0, and `?` when the verifier produced no verdict at all
(a verifier exception), which must never be folded into "fail".

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
from datetime import datetime
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
            f"| `{job['name']}` | {agents_label(job)} | {job['config'].get('n_attempts', '?')} "
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


def cmd_json(jobs_dir: Path, args: list[str]) -> None:
    print(json.dumps([load_job(jobs_dir, name) for name in args], indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs-dir", default=str(REPO / "results" / "jobs"))
    parser.add_argument("command", choices=("runs", "summary", "matrix", "steps", "json"))
    parser.add_argument("jobs", nargs="*", help="job names (all commands except `runs`)")
    opts = parser.parse_args()
    jobs_dir = Path(opts.jobs_dir)
    if not jobs_dir.is_dir():
        sys.exit(f"bench_report: no job store at {jobs_dir}")
    if opts.command == "runs":
        cmd_runs(jobs_dir, opts.jobs)
    else:
        if not opts.jobs:
            sys.exit(f"bench_report: `{opts.command}` needs at least one job name")
        {"summary": cmd_summary, "matrix": cmd_matrix, "steps": cmd_steps,
         "json": cmd_json}[opts.command](jobs_dir, opts.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
