#!/usr/bin/env python3
"""Contract tests for the run-list derivation and the render-time guard.

The audit only pays for itself if its verdicts change what gets run. Pinned here:

  * a cell whose oracle fails is NOT measurable, and is not in the run list
  * a host-limited cell is not measurable either, but keeps its own class
  * the watch list is exact complement, with the class attached
  * render_config drops non-measurable cells for measured profiles, loudly,
    keeps them for the audit profile, and refuses to render an empty run
  * ALLOW_DEFECTIVE=1 is the only way to keep them
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bench = load("bench_report", "scripts/bench_report.py")
render = load("render_config", "scripts/render_config.py")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_trial(job: Path, task: str, agent: str, reward: float) -> None:
    trial = job / f"{task}__{agent}"
    trial.mkdir(parents=True)
    (trial / "result.json").write_text(
        json.dumps(
            {
                "task_name": task,
                "trial_name": trial.name,
                "agent_info": {"name": agent},
                "agent_result": {},
                "verifier_result": {"rewards": {"reward": reward}},
            }
        )
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job = root / "cab-audit-1"
        job.mkdir()
        (job / "config.json").write_text(json.dumps({"datasets": [{"task_names": []}]}))
        # healthy x2, broken x1, host-limited x1 (oracle fails, but the host cannot run it)
        for task, oracle, nop in (
            ("alpha-ok", 1.0, 0.0),
            ("beta-ok", 1.0, 0.0),
            ("gamma-broken", 0.0, 0.0),
            ("delta-kvm", 0.0, 0.0),
        ):
            write_trial(job, task, "oracle", oracle)
            write_trial(job, task, "nop", nop)
        limits = root / "host-limits.json"
        limits.write_text(json.dumps({"tasks": {"delta-kvm": {"why": "no /dev/kvm"}}}))

        # --- run list -------------------------------------------------------
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.cmd_runlist(root, ["cab-audit-1", f"--host-limits={limits}"])
        out = buf.getvalue()
        body = [l for l in out.splitlines() if l and not l.startswith("#")]
        check("run list holds only oracle-green cells", body == ["alpha-ok", "beta-ok"], str(body))
        check("run list is sorted and one task per line", body == sorted(body) and all(" " not in l for l in body))
        check("run list states what was left out", "1 broken" in out and "1 host-limited" in out, out.splitlines()[0])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.cmd_runlist(root, ["cab-audit-1", f"--host-limits={limits}", "--watch"])
        watch = buf.getvalue()
        check("watch list is the complement", "gamma-broken" in watch and "delta-kvm" in watch and "alpha-ok" not in watch, watch)
        check("watch list carries the class", "gamma-broken\tbroken-task" in watch and "delta-kvm\thost-limited" in watch, watch)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.cmd_runlist(root, ["cab-audit-1", f"--host-limits={limits}", "--json"])
        payload = json.loads(buf.getvalue())
        check("json run list", payload["measurable"] == ["alpha-ok", "beta-ok"], str(payload))
        check("json watch list", payload["watch"] == {"gamma-broken": "broken-task", "delta-kvm": "host-limited"}, str(payload))

        out_file = root / "measurable.txt"
        with contextlib.redirect_stdout(io.StringIO()):
            bench.cmd_runlist(root, ["cab-audit-1", f"--host-limits={limits}", f"--out={out_file}"])
        check("--out writes a comment header then names", out_file.read_text().startswith("#") and "alpha-ok" in out_file.read_text())

        # --- render guard ---------------------------------------------------
        watch_file = REPO / "docs" / "tb2-watch.txt"
        saved = watch_file.read_text()
        try:
            watch_file.write_text("# test\n#\ngamma-broken\tbroken-task\ndelta-kvm\thost-limited\n")
            os.environ.pop("ALLOW_DEFECTIVE", None)
            check("guard: non-measurable cells are dropped, order kept",
                  render.drop_defective(["alpha-ok", "gamma-broken", "beta-ok", "delta-kvm"], "subset") == ["alpha-ok", "beta-ok"])
            check("guard: healthy cells untouched", render.drop_defective(["alpha-ok", "beta-ok"], "subset") == ["alpha-ok", "beta-ok"])
            check("guard: the audit profile is exempt", render.drop_defective(["gamma-broken"], "audit") == ["gamma-broken"])
            os.environ["ALLOW_DEFECTIVE"] = "1"
            check("guard: ALLOW_DEFECTIVE=1 keeps them", render.drop_defective(["gamma-broken"], "subset") == ["gamma-broken"])
            os.environ.pop("ALLOW_DEFECTIVE", None)
            try:
                render.drop_defective(["gamma-broken"], "subset"); emptied = False
            except SystemExit:
                emptied = True
            check("guard: a run with nothing measurable is refused, not launched empty", emptied)
            watch_file.write_text("")
            check("guard: no watch file = no opinion", render.drop_defective(["gamma-broken"], "subset") == ["gamma-broken"])
            check("guard: a missing registry is not an allow-list", render.defective_cells() == {})
            watch_file.unlink()
            check("guard: an absent file is likewise silent", render.defective_cells() == {})
        finally:
            watch_file.write_text(saved)
    print()
    if FAILS:
        print(f"FAIL ({len(FAILS)}): " + ", ".join(FAILS))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
