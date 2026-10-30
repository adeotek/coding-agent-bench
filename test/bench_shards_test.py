#!/usr/bin/env python3
"""Contract tests for sharded runs.

Sharding exists because the 89-task set needs ~145 GB of images and this host has
~46 GB free: Harbor keeps every image for a job's lifetime, so the set has to be
measured in slices. That is only honest if the slices are disjoint, their union is
the parent set, and a stitched report *says* what it covers. Pinned here:

  * `shard_slice` is disjoint and its union is the input, for every n
  * SHARD=k/n is validated (k>n, k=0, garbage, no explicit list -> error)
  * a shard's manifest carries the *parent* list's fingerprint, because a
    subset fingerprint cannot prove two jobs measured the same cells
  * `comparable()` compares parents, so shard 1 and shard 5 are comparable
  * `set_info()` reports coverage and refuses to imply a complete set when it
    is not, and flags shards from different parents
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAILS: list[str] = []


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = load("render_config", REPO / "scripts" / "render_config.py")
bench = load("bench_report", REPO / "scripts" / "bench_report.py")
man = load("manifest", REPO / "scripts" / "manifest.py")


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def run_render(env_extra: dict[str, str], tasks: list[str], out: Path) -> subprocess.CompletedProcess:
    task_file = out.parent / "tasks.txt"
    task_file.write_text("\n".join(tasks) + "\n")
    env = {**os.environ, "TASK_FILE": str(task_file), **env_extra}
    for key in ("TASK_NAMES", "SHARD"):
        if key not in env_extra:
            env.pop(key, None)
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "render_config.py"), "subset", "-o", str(out)],
        capture_output=True, text=True, env=env,
    )


def main() -> int:
    tasks = [f"task-{i:02d}" for i in range(10)]

    # --- slicing -----------------------------------------------------------
    check("slice sizes are ceil(len/n)", [len(rc.shard_slice(tasks, (k, 3))) for k in (1, 2, 3)] == [4, 4, 2])
    for n in range(1, 8):
        parts = [rc.shard_slice(tasks, (k, n)) for k in range(1, n + 1)]
        union = [t for p in parts for t in p]
        check(f"n={n}: shards are disjoint", len(union) == len(set(union)), str(parts))
        check(f"n={n}: union is the parent list", union == tasks, str(union))
        check(f"n={n}: order is preserved", all(p == tasks[tasks.index(p[0]):][:len(p)] for p in parts if p))
    check("more shards than tasks still yields each task once",
          sorted(t for k in range(1, 13) for t in rc.shard_slice(tasks, (k, 12))) == tasks)

    # --- validation --------------------------------------------------------
    for bad in ("0/3", "4/3", "x", "2/0", "2", "1/3/4"):
        try:
            rc.parse_shard(bad)
            ok = False
        except SystemExit:
            ok = True
        check(f"SHARD={bad!r} is rejected", ok)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "eff.json"
        good = run_render({"SHARD": "2/3"}, tasks, out)
        cfg = json.loads(out.read_text()) if out.is_file() else {}
        got = ((cfg.get("datasets") or [{}])[0].get("task_names") or [])
        check("SHARD=2/3 renders the second block", good.returncode == 0 and got == tasks[4:8], f"rc={good.returncode} got={got} err={good.stderr[-200:]}")
        check("render says which shard it produced", "shard 2/3" in good.stderr, good.stderr[-200:])

        bad_shard = run_render({"SHARD": "4/3"}, tasks, out)
        check("out-of-range shard fails the render", bad_shard.returncode != 0 and "k <= n" in bad_shard.stderr, bad_shard.stderr[-200:])

        no_list = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "render_config.py"), "subset", "-o", str(out)],
            capture_output=True, text=True,
            env={**os.environ, "SHARD": "1/2", "TASK_FILE": "", "TASK_NAMES": "", "N_TASKS": "5"},
        )
        check("SHARD without an explicit task list fails", no_list.returncode != 0 and "explicit task list" in no_list.stderr, no_list.stderr[-240:])

        # --- manifest carries the parent, not just the slice ---------------
        parent = Path(tmp) / "all.txt"
        parent.write_text("# comment\n" + "\n".join(tasks) + "\n")
        cfg_path = Path(tmp) / "eff.json"
        cfg_path.write_text(json.dumps({"datasets": [{"name": "terminal-bench", "version": "2.0", "task_names": tasks[4:8]}], "agents": []}))
        mpath = Path(tmp) / "m.json"
        rc2 = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "manifest.py"), "start",
             "--config", str(cfg_path), "--job-name", "cab-subset-s2of3-20261027-000000-1",
             "--out", str(mpath), "--shard", "2/3", "--parent-tasks", str(parent)],
            capture_output=True, text=True,
        )
        m = json.loads(mpath.read_text()) if mpath.is_file() else {}
        shard = m.get("shard") or {}
        check("manifest records the shard index/count", rc2.returncode == 0 and (shard.get("index"), shard.get("count")) == (2, 3), rc2.stderr[-200:])
        check("manifest records the parent size", shard.get("parent_n_tasks") == 10, str(shard))
        check("manifest fingerprints the whole parent list",
              shard.get("parent_task_list_sha256") == man.sha256_json(sorted(tasks)), str(shard))
        check("shard's own fingerprint differs from the parent's",
              m["dataset"]["task_list_sha256"] != shard.get("parent_task_list_sha256"))

        # two different shards of the same parent must be comparable
        m2 = dict(m, job_name="cab-subset-s3of3-x", dataset={**m["dataset"], "task_list_sha256": "other"},
                  shard={**shard, "index": 3})
        c1, c2 = man.comparable(m), man.comparable(m2)
        check("comparable() keys on the parent set", c1["task_set"] == c2["task_set"] == shard["parent_task_list_sha256"], f"{c1['task_set']} vs {c2['task_set']}")
        m3 = dict(m, shard={**shard, "parent_task_list_sha256": "different"})
        check("a different parent is not comparable", man.comparable(m3)["task_set"] != c1["task_set"])

        # --- set_info coverage --------------------------------------------
        jobs_dir = Path(tmp) / "jobs"
        def write_job(name, tasks_slice, shard_meta):
            job = jobs_dir / name
            job.mkdir(parents=True)
            (job / "manifest.json").write_text(json.dumps({"dataset": {"task_list_sha256": "x"}, "shard": shard_meta, "agents": []}))
            for task in tasks_slice:
                trial = job / f"{task}__moca__t1"
                trial.mkdir()
                (trial / "result.json").write_text(json.dumps({
                    "task_name": task, "trial_name": trial.name,
                    "agent_info": {"name": "moca"}, "agent_result": {},
                    "verifier_result": {"rewards": {"reward": 1.0}},
                }))
            return {"name": name, "rows": [
                {"task": t, "agent": "moca", "reward": 1.0, "trial": f"{t}__moca__t1"} for t in tasks_slice
            ], "path": job}

        base = {"parent_task_list_sha256": "P", "parent_n_tasks": 10, "parent_tasks": "docs/all.txt"}
        j1 = write_job("cab-subset-s1of3-1", tasks[0:4], {**base, "index": 1, "count": 3})
        j2 = write_job("cab-subset-s2of3-1", tasks[4:8], {**base, "index": 2, "count": 3})
        info = bench.set_info(jobs_dir, [j1, j2])
        check("set_info counts the union", info["tasks"] == 8, str(info))
        check("set_info reports the uncovered remainder", info["uncovered"] == 2, str(info))
        check("set_info flags an incomplete set in the text", any("2 uncovered" in l for l in bench.set_lines(info)), str(bench.set_lines(info)))
        check("shard names are parsed from job names",
              bench.shard_of("cab-subset-s2of5-20261027-101010-123") == (2, 5) and bench.shard_of("cab-subset-20261027-101010-123") is None)

        j3 = write_job("cab-subset-s3of3-1", tasks[8:10], {**base, "index": 3, "count": 3})
        info = bench.set_info(jobs_dir, [j1, j2, j3])
        check("a complete set reports complete", info["uncovered"] == 0 and "complete" in " ".join(bench.set_lines(info)), str(bench.set_lines(info)))

        other = dict(base, parent_task_list_sha256="Q")
        j4 = write_job("cab-subset-s3of3-2", tasks[8:10], {**other, "index": 3, "count": 3})
        info = bench.set_info(jobs_dir, [j1, j4])
        check("shards from different parents are flagged", any("different parent" in l for l in bench.set_lines(info)), str(bench.set_lines(info)))

        unsharded = write_job("cab-subset-plain", tasks[0:4], None)
        check("an unsharded job has no set section", bench.set_lines(bench.set_info(jobs_dir, [{"name": "cab-subset-plain", "rows": unsharded["rows"]}])) == [])

    # --- attempts default: a comparison buys 3 draws, a wiring check 1 -------
    saved = {k: os.environ.pop(k, None) for k in ("N_ATTEMPTS", "TASK_NAMES", "TASK_FILE")}
    try:
        os.environ["TASK_NAMES"] = "alpha,beta"
        check("attempts: subset defaults to 3", rc.build("subset")["n_attempts"] == 3)
        check("attempts: full defaults to 3", rc.build("full")["n_attempts"] == 3)
        check("attempts: smoke stays at 1", rc.build("smoke")["n_attempts"] == 1)
        os.environ["N_ATTEMPTS"] = "4"
        check("attempts: an explicit N_ATTEMPTS wins", rc.build("subset")["n_attempts"] == 4)
        os.environ["N_ATTEMPTS"] = "1"
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc.build("subset")
        check("attempts: N_ATTEMPTS=1 on a comparison warns", "single draw" in err.getvalue(),
              err.getvalue()[:120])
        err2 = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err2):
            rc.build("smoke")
        check("attempts: smoke at 1 does not warn", "single draw" not in err2.getvalue())
    finally:
        os.environ.pop("N_ATTEMPTS", None)
        os.environ.pop("TASK_NAMES", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
