#!/usr/bin/env python3
"""Contract tests for `bench_report.py compare` — the paired statistics.

The command is the only part of the toolkit that makes a *claim* about agents,
so its arithmetic is pinned here with synthetic job stores (stdlib only, no
harbor, no docker, no spend).

What must hold:
  * a task with repeats is one observation for the CI, not k observations —
    otherwise the interval shrinks by sqrt(k) and the report claims precision
    the design does not have;
  * tasks differ in difficulty, and `compare` is paired by task, so an agent
    that is better on the hard cells must show a positive delta even where both
    agents solve the easy ones;
  * `?` (no verifier verdict) never counts as a failure;
  * the exact McNemar p-value uses only the discordant cells;
  * the flip rate between two identical jobs counts cell-level verdict changes.
"""
from __future__ import annotations

import importlib.util
import json
import math
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_report", REPO / "scripts" / "bench_report.py")
assert spec and spec.loader, "cannot load scripts/bench_report.py"
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_trial(job: Path, task: str, agent: str, reward: float | None, n: int = 0) -> None:
    trial = job / f"{task}__{agent}__t{n}"
    trial.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_name": task,
        "trial_name": f"{task}__t{n}",
        "agent_info": {"name": agent},
        "agent_result": {},
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else {},
    }
    (trial / "result.json").write_text(json.dumps(payload))


def make_job(root: Path, name: str, spec_rows: list[tuple[str, str, float | None]]) -> Path:
    job = root / name
    job.mkdir(parents=True)
    (job / "config.json").write_text(json.dumps({"agents": [{"name": "a"}], "datasets": [{"task_names": []}]}))
    seen: dict[tuple[str, str], int] = {}
    for task, agent, reward in spec_rows:
        key = (task, agent)
        n = seen.get(key, 0)
        seen[key] = n + 1
        write_trial(job, task, agent, reward, n)
    return job


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Two tasks on which moca is perfect and pi is wrong, and one task both
        # solve. Paired by task, the delta must be +2/3 -> +66.7 points, and the
        # CI must be computed over 3 tasks (not over 3 + 6 trials).
        jobs = [
            make_job(
                root,
                "job-a",
                [
                    ("easy", "moca", 1.0),
                    ("easy", "pi", 1.0),
                    ("hard-1", "moca", 1.0),
                    ("hard-1", "pi", 0.0),
                    ("hard-2", "moca", 1.0),
                    ("hard-2", "pi", 0.0),
                ],
            )
        ]
        outcomes = bench.task_outcomes([bench.load_job(root, "job-a")])
        scores = bench.agent_scores(outcomes)
        check("score = mean over tasks", math.isclose(scores["moca"]["score"], 1.0), str(scores["moca"]))
        check("score counts tasks, not trials", scores["moca"]["tasks"] == 3, str(scores["moca"]))
        check("pi scores 1/3", math.isclose(scores["pi"]["score"], 1 / 3), str(scores["pi"]))

        pairs = bench.pairwise(outcomes, ["moca", "pi"], iters=500, seed=0)
        p = pairs[0]
        check("paired delta = +66.7 pts", math.isclose(p["delta"], 2 / 3), str(p["delta"]))
        check("discordant cells counted", (p["a_only"], p["b_only"]) == (2, 0), str((p["a_only"], p["b_only"])))
        check("McNemar p = 0.5 for 2/0", math.isclose(p["p"], 0.5), str(p["p"]))
        # Three tasks cannot support a claim: resampling three cells can draw the
        # one task both agents solve three times, so the interval must include 0.
        check("CI includes 0 at n=3 (too few tasks to claim anything)", p["lo"] <= 0, str((p["lo"], p["hi"])))

        # The same effect with enough tasks must exclude 0.
        wide = make_job(
            root,
            "job-wide",
            [(f"h{i}", "moca", 1.0) for i in range(12)] + [(f"h{i}", "pi", 0.0) for i in range(12)],
        )
        wide_out = bench.task_outcomes([bench.load_job(root, "job-wide")])
        wide_pair = bench.pairwise(wide_out, ["moca", "pi"], iters=500, seed=0)[0]
        check("CI excludes 0 at n=12 unanimous", wide_pair["lo"] > 0, str((wide_pair["lo"], wide_pair["hi"])))
        check("McNemar p < 0.001 at 12/0", wide_pair["p"] < 0.001, str(wide_pair["p"]))

        # A repeat inside one task must NOT narrow the CI: same task-level rates,
        # six trials instead of one, identical interval.
        many = make_job(
            root,
            "job-repeat",
            [("easy", "moca", 1.0), ("easy", "pi", 1.0)]
            + [("hard-1", "moca", 1.0)] * 3 + [("hard-1", "pi", 0.0)] * 3
            + [("hard-2", "moca", 1.0)] * 3 + [("hard-2", "pi", 0.0)] * 3,
        )
        many_out = bench.task_outcomes([bench.load_job(root, "job-repeat")])
        many_pair = bench.pairwise(many_out, ["moca", "pi"], iters=500, seed=0)[0]
        check(
            "repeats do not narrow the CI (same tasks)",
            math.isclose(many_pair["lo"], p["lo"]) and math.isclose(many_pair["hi"], p["hi"]),
            f"{many_pair['lo']:.4f},{many_pair['hi']:.4f} vs {p['lo']:.4f},{p['hi']:.4f}",
        )
        check("repeat delta unchanged", math.isclose(many_pair["delta"], 2 / 3), str(many_pair["delta"]))

        # `?` is not a failure: a task with no verdict is skipped, not scored 0.
        nv = make_job(
            root,
            "job-nv",
            [("t1", "moca", 1.0), ("t1", "pi", 1.0), ("t2", "moca", None), ("t2", "pi", 0.0)],
        )
        nv_out = bench.task_outcomes([bench.load_job(root, "job-nv")])
        nv_scores = bench.agent_scores(nv_out)
        check("no-verdict skipped for the agent that had it", nv_scores["moca"]["tasks"] == 1, str(nv_scores["moca"]))
        check("no-verdict counted separately", nv_scores["moca"]["no_verdict"] == 1, str(nv_scores["moca"]))
        check("other agent keeps its task", nv_scores["pi"]["tasks"] == 2, str(nv_scores["pi"]))

        # Flip rate: two identical jobs, one cell differs -> 1 flip of the cells
        # that appear in both.
        make_job(root, "flip-a", [("t1", "moca", 1.0), ("t2", "moca", 1.0)])
        make_job(root, "flip-b", [("t1", "moca", 1.0), ("t2", "moca", 0.0)])
        flips = bench.flip_rate([bench.load_job(root, "flip-a"), bench.load_job(root, "flip-b")])
        check("flip cells counted", flips["cells"] == 2, str(flips["cells"]))
        check("flips detected", flips["flips"] == 1, str(flips))

        # McNemar exact values worth pinning: symmetric 3/3 -> 1.0, 5/0 -> 0.0625.
        check("McNemar 3/3 = 1.0", math.isclose(bench.mcnemar_exact(3, 3), 1.0), str(bench.mcnemar_exact(3, 3)))
        check("McNemar 5/0 = 0.0625", math.isclose(bench.mcnemar_exact(5, 0), 0.0625), str(bench.mcnemar_exact(5, 0)))
        check("McNemar 0/0 = 1.0", bench.mcnemar_exact(0, 0) == 1.0)

        # The JSON path must be machine-readable and complete.
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.cmd_compare(root, ["job-a", "--json", "--iters=200"])
        data = json.loads(buf.getvalue())
        check("json has scores and pairs", set(data) >= {"jobs", "tasks", "scores", "pairs"}, str(sorted(data)))
        check("json attempts_per_task", math.isclose(data["attempts_per_task"], 1.0), str(data.get("attempts_per_task")))

    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
