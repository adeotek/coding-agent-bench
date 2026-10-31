#!/usr/bin/env python3
"""Contract tests for the instrument-honesty layer (no spend, stdlib only).

Three rules came out of the 2026-10-30 noise-bar run and are pinned here,
because each of them exists to stop a specific mistake this repo has made:

  * `scripts/cell_stability.py` classifies a (cell, agent) pair from its measured
    k/n, refuses to call anything under three attempts evidence, excludes
    Harbor's `nop`/`oracle` calibration columns, folds only the newest release of
    each agent by default, and never lets a task-side cell be "ranking";
  * `bench_report.py matrix` refuses a job measured at one attempt — a letter
    from a single draw is how four cell-level claims got written — and prints
    `k/n` with a Wilson interval when it does run;
  * `wilson` keeps a real width at 0/n and n/n, where the normal approximation
    collapses to a point and would turn 3/3 into certainty.

Run: python3 test/bench_cell_stability_test.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_report", REPO / "scripts" / "bench_report.py")
assert spec and spec.loader, "cannot load scripts/bench_report.py"
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

spec2 = importlib.util.spec_from_file_location("cell_stability", REPO / "scripts" / "cell_stability.py")
assert spec2 and spec2.loader, "cannot load scripts/cell_stability.py"
stab = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(stab)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_trial(job: Path, task: str, agent: str, reward: float | None, version: str, n: int) -> None:
    trial = job / f"{task}__{n:02d}"
    trial.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_name": task,
        "trial_name": f"{task}__{n:02d}",
        "agent_info": {"name": agent, "version": version},
        "agent_result": {},
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else {},
    }
    (trial / "result.json").write_text(json.dumps(payload))


def make_job(root: Path, name: str, rows: list[tuple[str, str, float | None, str]],
             local_path: str | None = None) -> Path:
    job = root / name
    job.mkdir(parents=True)
    dataset = {"task_names": sorted({r[0] for r in rows})}
    if local_path:
        # a local dataset records `path` instead of a registry name+version
        dataset = {"path": local_path, "task_names": dataset["task_names"]}
    (job / "config.json").write_text(json.dumps({"agents": [{"name": "x"}], "datasets": [dataset]}))
    for i, (task, agent, reward, version) in enumerate(rows):
        write_trial(job, task, agent, reward, version, i)
    return job


def main() -> int:
    # --- Wilson keeps width where the normal approximation collapses --------
    lo, hi = bench.wilson(3, 3)
    check("wilson: 3/3 is not certainty", lo > 0.2 and hi == 1.0, f"{lo:.2f}-{hi:.2f}")
    lo0, hi0 = bench.wilson(0, 3)
    check("wilson: 0/3 still has an upper bound", lo0 == 0.0 and hi0 > 0.5, f"{lo0:.2f}-{hi0:.2f}")
    check("wilson: empty cell is the whole line", bench.wilson(0, 0) == (0.0, 1.0))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- matrix refuses a single-draw job ---------------------------------
        one = make_job(root, "cab-subset-20260101-000000-1",
                       [("alpha", "moca", 1.0, "v1"), ("beta", "moca", 0.0, "v1")])
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = bench.cmd_matrix(root, [one.name])
        check("matrix refuses an n=1 job", rc == 2, f"rc={rc}")
        check("matrix refusal names the cells", "single-draw" in err.getvalue(), err.getvalue()[:120])
        check("matrix refusal prints no letters", buf.getvalue() == "")
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = bench.cmd_matrix(root, [one.name, "--allow-n1"])
        check("matrix --allow-n1 prints rates", rc == 0 and "1/1" in buf.getvalue(), buf.getvalue()[:120])

        # --- stability: classes, calibration, versions, ranking --------------
        # moca v0.7.12: alpha 3/3 (passes), beta 1/3 (flaky), gamma 0/3 (fails)
        rows = []
        for task, rewards in {
            "alpha": [1.0, 1.0, 1.0],
            "beta": [1.0, 0.0, 0.0],
            "gamma": [0.0, 0.0, 0.0],
            "delta": [1.0, 1.0, 1.0],
        }.items():
            rows += [(task, "moca", r, "v0.7.12") for r in rewards]
        # opencode: alpha 3/3 (no spread), beta 3/3 (spread 2/3 vs moca), delta 0/3
        rows += [("alpha", "opencode", r, "2.0") for r in (1.0, 1.0, 1.0)]
        rows += [("beta", "opencode", r, "2.0") for r in (1.0, 1.0, 1.0)]
        rows += [("delta", "opencode", r, "2.0") for r in (0.0, 0.0, 0.0)]
        # calibration agents must never appear
        rows += [("alpha", "nop", 0.0, "0"), ("alpha", "oracle", 1.0, "0")]
        # an older moca release on `beta` that would poison the rate if folded
        rows += [("beta", "moca", 0.0, "v0.7.10") for _ in range(4)]
        make_job(root, "cab-subset-20260102-000000-2", rows)

        # The registry resolves its own copy of the reporting module (importlib
        # gives each loader its own module object), so patch stably via stab.
        old_root = stab.JOBS
        setattr(stab, "JOBS", root)
        reg = stab.build(["cab-subset-20260102-000000-2"])

        cells = reg["cells"]
        check("stability: 3/3 is a pass", cells["alpha"]["agents"]["moca"]["class"] == "passes")
        check("stability: 0/3 is a fail", cells["gamma"]["agents"]["moca"]["class"] == "fails")
        check("stability: 1/3 is flaky", cells["beta"]["agents"]["moca"]["class"] == "flaky")
        check("stability: calibration agents excluded", "nop" not in cells["alpha"]["agents"])
        check("stability: only the newest release is folded",
              cells["beta"]["agents"]["moca"]["n"] == 3,
              f"n={cells['beta']['agents']['moca']['n']}")
        check("stability: unanimous cell does not rank", cells["alpha"]["ranking"] is False,
              f"spread={cells['alpha']['spread']}")
        check("stability: a split cell ranks", cells["beta"]["ranking"] is True,
              f"spread={cells['beta']['spread']}")
        check("stability: a wide-but-unanimous cell still ranks by spread",
              cells["delta"]["ranking"] is True, f"spread={cells['delta']['spread']}")

        # a task-side cell can never rank, however wide its spread
        old_side = stab.bench.task_side_tasks
        setattr(stab.bench, "task_side_tasks", lambda _r: {"beta": "test"})
        try:
            reg2 = stab.build(["cab-subset-20260102-000000-2"])
        finally:
            setattr(stab.bench, "task_side_tasks", old_side)
        check("stability: task-side cells are never ranking",
              reg2["cells"]["beta"]["ranking"] is False and reg2["cells"]["beta"]["task_side"] is True)

        # --- local datasets stay out of the terminal-bench registry ----------
        # A repaired or authored cell is local-only by policy; the same cell name
        # can also exist upstream, so the exclusion has to key off the job's own
        # dataset config, not off the name.
        make_job(root, "cab-subset-20260103-000000-3",
                 [("alpha", "moca", 0.0, "v9"), ("alpha", "moca", 0.0, "v9"),
                  ("alpha", "opencode", 1.0, "v9"), ("alpha", "opencode", 1.0, "v9"),
                  ("alpha", "opencode", 1.0, "v9")],
                 local_path="/repo/tasks/authored")
        local_reg = stab.build(["cab-subset-20260103-000000-3"])
        check("stability: a local job contributes no cells",
              local_reg["cells"] == {}, str(sorted(local_reg["cells"]))[:120])
        check("stability: a local job is recorded as skipped",
              local_reg["generated_from"]["local_jobs_skipped"] == ["cab-subset-20260103-000000-3"],
              str(local_reg["generated_from"]["local_jobs_skipped"]))
        mixed = stab.build(["cab-subset-20260102-000000-2", "cab-subset-20260103-000000-3"])
        check("stability: a local job cannot move a registry rate",
              mixed["cells"]["alpha"]["agents"]["moca"]["n"] == 3,
              f"n={mixed['cells']['alpha']['agents']['moca']['n']}")
        check("stability: the local job is named in the mixed registry",
              "cab-subset-20260103-000000-3" in mixed["generated_from"]["local_jobs_skipped"])

        setattr(stab, "JOBS", old_root)

        listing = stab.ranking_file(reg)
        check("ranking file lists the ranking cell and not the others",
              "\nbeta\n" in listing and "\nalpha\n" not in listing, listing[-160:])

    print()
    print("PASS" if not FAILS else f"FAIL: {len(FAILS)} — {', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
