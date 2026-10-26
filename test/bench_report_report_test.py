#!/usr/bin/env python3
"""Contract tests for the reporting layer: partial credit, manifest, export, report, diff.

These four commands are what a future reader trusts instead of the prose in
`docs/*-report.md`, so their arithmetic and their honesty rules are pinned here:

  * partial credit counts passed tests, excludes skipped ones, and survives a
    missing or corrupt ctrf.json by returning None (never by inventing a score);
  * a manifest records the toolchain and refuses to call two jobs comparable when
    agents, knobs or the task list differ — and says so when a manifest is absent;
  * `export` aggregates what the trials say, including no-verdict trials, without
    silently scoring them;
  * `report` excludes task-side cells from the scores but says which ones and why;
  * `diff` names the failing test, which is the whole point of the command.
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
assert spec and spec.loader
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

mspec = importlib.util.spec_from_file_location("cab_manifest", REPO / "scripts" / "manifest.py")
assert mspec and mspec.loader
manifest_mod = importlib.util.module_from_spec(mspec)
mspec.loader.exec_module(manifest_mod)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_trial(job: Path, task: str, agent: str, reward: float | None, tests: list[str] | None = None) -> Path:
    trial = job / f"{task}__{agent}"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text(
        json.dumps(
            {
                "task_name": task,
                "trial_name": trial.name,
                "agent_info": {"name": agent},
                "agent_result": {"n_input_tokens": 1000, "n_output_tokens": 100, "cost_usd": 0.01},
                "verifier_result": {"rewards": {"reward": reward}} if reward is not None else {},
            }
        )
    )
    if tests is not None:
        (trial / "verifier").mkdir()
        ctrf = {
            "results": {
                "tool": {"name": "pytest"},
                "summary": {"tests": len(tests), "passed": tests.count("passed"), "failed": tests.count("failed")},
                "tests": [{"name": f"test_outputs.py::t{i}", "status": s} for i, s in enumerate(tests)],
            }
        }
        (trial / "verifier" / "ctrf.json").write_text(json.dumps(ctrf))
    return trial


def make_job(root: Path, name: str, rows: list[tuple[str, str, float | None, list[str] | None]]) -> Path:
    job = root / name
    job.mkdir(parents=True)
    (job / "config.json").write_text(json.dumps({"agents": [], "datasets": [{"name": "terminal-bench", "version": "2.0", "task_names": sorted({r[0] for r in rows})}], "n_attempts": 1}))
    for task, agent, reward, tests in rows:
        write_trial(job, task, agent, reward, tests)
    return job


def capture(fn, *args) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job = make_job(
            root,
            "job-1",
            [
                ("t-easy", "moca", 1.0, ["passed", "passed"]),
                ("t-easy", "pi", 1.0, ["passed", "passed"]),
                ("t-hard", "moca", 0.0, ["passed", "failed", "failed", "skipped"]),
                ("t-hard", "pi", 0.0, ["failed", "failed", "failed"]),
                ("t-none", "moca", None, None),
                ("t-none", "pi", 1.0, ["passed"]),
            ],
        )

        # --- partial credit --------------------------------------------------
        c = bench.credit_of(root, "job-1", "t-hard__moca")
        check("credit counts passed", c and c["passed"] == 1, str(c))
        check("credit excludes skipped from the denominator", c and c["total"] == 3, str(c))
        check("credit names the failing tests", c and len(c["failed"]) == 2, str(c))
        check("credit fraction", abs(bench.credit_fraction(c) - 1 / 3) < 1e-9, str(bench.credit_fraction(c)))
        check("missing ctrf -> None", bench.credit_of(root, "job-1", "t-none__moca") is None)
        (root / "job-1" / "t-hard__pi" / "verifier" / "ctrf.json").write_text("{not json")
        check("corrupt ctrf -> None", bench.credit_of(root, "job-1", "t-hard__pi") is None)

        credit_out = capture(bench.cmd_credit, root, ["job-1"])
        check("credit table names the agents", "moca" in credit_out and "pi" in credit_out, credit_out[:200])

        # --- task-side registry ----------------------------------------------
        repo = root / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "task-side.json").write_text(json.dumps({"tasks": {"t-hard": {"why": "verifier greps a log line"}}}))
        check("task-side registry read", list(bench.task_side_tasks(repo)) == ["t-hard"], str(bench.task_side_tasks(repo)))
        check("task-side absent -> empty", bench.task_side_tasks(root / "nowhere") == {})

        # --- export -----------------------------------------------------------
        jobs = [bench.load_job(root, "job-1")]
        credits = bench.credit_map(root, jobs)
        summary = bench.export_job(root, jobs[0], credits, bench.task_side_tasks(repo))
        moca = summary["by_agent"]["moca"]
        check("export counts no-verdict separately", moca["no_verdict"] == 1, str(moca))
        check("export scores only verdicts", moca["tasks"] == 2 and moca["passes"] == 1, str(moca))
        check("export marks task-side trials", moca["task_side"] == 1, str(moca))
        check("export carries tokens", moca["input_tokens"] > 0, str(moca))
        check("export trial has credit", any(t["credit"] is not None for t in summary["trials"]), "no credit in trials")
        out = capture(bench.cmd_export, root, ["job-1"])
        check("export writes summary.json", (root / "job-1" / "summary.json").is_file(), out)

        # --- manifest ---------------------------------------------------------
        cfg = root / "cfg.json"
        cfg.write_text(json.dumps({"agents": [{"import_path": "agents.moca:Moca", "model_name": "m", "kwargs": {"version": "v1"}}], "datasets": [{"name": "terminal-bench", "version": "2.0", "task_names": ["t-easy", "t-hard"]}], "n_attempts": 1, "n_concurrent_trials": 2}))
        mpath = root / "manifest.json"
        manifest_mod.main(["start", "--config", str(cfg), "--job-name", "job-1", "--out", str(mpath), "--harbor-version", "0.25.0", "--harbor-python", "3.14.8", "--knob", "MOCA_MODE=yolo"])
        m = json.loads(mpath.read_text())
        check("manifest records harbor version", m["harbor"]["version"] == "0.25.0", str(m["harbor"]))
        check("manifest records agents + model", m["agents"][0]["id"] == "agents.moca:Moca", str(m["agents"]))
        check("manifest fingerprints the task list", m["dataset"]["task_list_sha256"], str(m["dataset"]))
        check("manifest records knobs", m["knobs"].get("MOCA_MODE") == "yolo", str(m["knobs"]))
        manifest_mod.main(["finish", "--manifest", str(mpath), "--job-dir", str(root / "job-1"), "--exit-code", "3"])
        m = json.loads(mpath.read_text())
        check("finish records the exit code", m["harbor_exit_code"] == 3, str(m["harbor_exit_code"]))
        check("finish counts trials per agent", m["trials"]["by_agent"] == {"moca": 3, "pi": 3}, str(m["trials"]))
        check("finish copies into the job dir", (root / "job-1" / "manifest.json").is_file())

        # --- manifest_warnings ------------------------------------------------
        check("no warning when manifests agree", bench.manifest_warnings(root, jobs) == [], str(bench.manifest_warnings(root, jobs)))
        other = make_job(root, "job-2", [("t-easy", "moca", 1.0, ["passed"])])
        w = bench.manifest_warnings(root, [bench.load_job(root, "job-1"), bench.load_job(root, "job-2")])
        check("warns when a job has no manifest", any("no manifest" in x for x in w), str(w))
        m2 = dict(m)
        m2["agents"] = [{"id": "agents.moca:Moca", "model": "different", "version": "v1"}]
        (root / "job-2" / "manifest.json").write_text(json.dumps(m2))
        w = bench.manifest_warnings(root, [bench.load_job(root, "job-1"), bench.load_job(root, "job-2")])
        check("warns when agents differ", any("agents differ" in x for x in w), str(w))

        # --- report -----------------------------------------------------------
        registry = str(repo / "docs" / "task-side.json")
        report = capture(bench.cmd_report, root, ["job-1", f"--task-side={registry}"])
        check("report excludes task-side cells", "t-hard" in report and "Excluded" in report, report[:300])
        check("report has a leaderboard", "Leaderboard" in report and "credit" in report, report[:300])
        check("report has paired comparisons", "Paired comparisons" in report and "undecided" in report, report[:400])
        with_side = capture(bench.cmd_report, root, ["job-1", "--include-task-side", f"--task-side={registry}"])
        check("--include-task-side keeps them", "Excluded" not in with_side, with_side[:200])

        # --- diff -------------------------------------------------------------
        diff = capture(bench.cmd_diff, root, ["job-1", "t-none"])
        check("diff lists both agents", "moca" in diff and "pi" in diff, diff[:300])
        check("diff shows the verdict marks", "| P |" in diff and "| ? |" in diff, diff[:300])
        diff_hard = capture(bench.cmd_diff, root, ["job-1", "t-hard"])
        check("diff names failing tests", "test_outputs.py::t" in diff_hard, diff_hard[:400])

    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
