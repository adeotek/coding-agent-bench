#!/usr/bin/env python3
"""Contract tests for the oracle/nop audit classifier.

The audit decides which tasks are *tasks at all*, so its classification is the
difference between "moca cannot do this" and "this cell is broken". Pinned here:

  * oracle pass + nop fail  -> healthy
  * oracle fail             -> broken-task (unsolvable as specified)
  * nop pass                -> vacuous (verifier satisfiable by doing nothing)
  * either side no-verdict  -> no-verdict, never folded into healthy or broken
  * one side missing        -> unknown, so an incomplete audit cannot masquerade
                               as a clean one
"""
from __future__ import annotations

import importlib.util
import io
import json
import contextlib
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_report", REPO / "scripts" / "bench_report.py")
assert spec and spec.loader
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def row(agent: str, reward: float | None, exception: str | None = None) -> dict:
    return {
        "task": "t",
        "trial": f"t__{agent}",
        "agent": agent,
        "version": None,
        "model": None,
        "reward": reward,
        "exception": exception,
        "input_tokens": 0,
        "cache_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "agent_seconds": 0.0,
        "trial_seconds": 0.0,
    }


def write_job(root: Path, name: str, spec_rows: list[tuple[str, str, float | None, str | None]]) -> None:
    job = root / name
    job.mkdir(parents=True)
    (job / "config.json").write_text(json.dumps({"datasets": [{"task_names": sorted({r[0] for r in spec_rows})}]}))
    for task, agent, reward, exc in spec_rows:
        trial = job / f"{task}__{agent}"
        trial.mkdir()
        (trial / "result.json").write_text(
            json.dumps(
                {
                    "task_name": task,
                    "trial_name": trial.name,
                    "agent_info": {"name": agent},
                    "agent_result": {},
                    "verifier_result": {"rewards": {"reward": reward}} if reward is not None else {},
                    "exception_info": {"exception_type": exc} if exc else {},
                }
            )
        )


def main() -> int:
    # Pure classification first.
    check("oracle P + nop F = healthy", bench.audit_classify(row("oracle", 1.0), row("nop", 0.0)) == "healthy")
    check("oracle F = broken-task", bench.audit_classify(row("oracle", 0.0), row("nop", 0.0)) == "broken-task")
    check("nop P = vacuous", bench.audit_classify(row("oracle", 1.0), row("nop", 1.0)) == "vacuous")
    check("both P... = vacuous (not healthy)", bench.audit_classify(row("oracle", 1.0), row("nop", 1.0)) == "vacuous")
    check("oracle F + nop P = both-broken", bench.audit_classify(row("oracle", 0.0), row("nop", 1.0)) == "both-broken")
    check("no verdict wins over pass", bench.audit_classify(row("oracle", 1.0), row("nop", None)) == "no-verdict")
    check("missing nop = unknown", bench.audit_classify(row("oracle", 1.0), None) == "unknown")
    check("missing oracle = unknown", bench.audit_classify(None, row("nop", 0.0)) == "unknown")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_job(
            root,
            "cab-audit-1",
            [
                ("good", "oracle", 1.0, None),
                ("good", "nop", 0.0, None),
                ("unsolvable", "oracle", 0.0, "AgentTimeoutError"),
                ("unsolvable", "nop", 0.0, None),
                ("vacuous", "oracle", 1.0, None),
                ("vacuous", "nop", 1.0, None),
                ("flaky", "oracle", None, "VerifierTimeoutError"),
                ("flaky", "nop", 0.0, None),
                ("half", "oracle", 1.0, None),
            ],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.cmd_audit(root, ["cab-audit-1"])
        out = buf.getvalue()
        check("audit reports the healthy count", "| healthy | 1 |" in out, out[:400])
        check("audit names the broken task", "`unsolvable`" in out and "broken-task" in out, out[:600])
        check("audit names the vacuous task", "`vacuous`" in out and "vacuous |" in out, out[:600])
        check("audit flags no-verdict with its exception", "`flaky`" in out and "VerifierTimeoutError" in out, out[:800])
        check("audit flags an incomplete task", "`half`" in out and "unknown" in out, out[:800])

        jpath = root / "audit.json"
        with contextlib.redirect_stdout(io.StringIO()):
            bench.cmd_audit(root, ["cab-audit-1", f"--out={jpath}"])
        payload = json.loads(jpath.read_text())
        check("json counts add up", sum(payload["counts"].values()) == payload["tasks"], str(payload["counts"]))
        check("json lists only the healthy task as healthy", payload["healthy"] == ["good"], str(payload["healthy"]))
        check("json findings carry the exception", any(f["oracle_exception"] == "AgentTimeoutError" for f in payload["findings"]), str(payload["findings"]))

    if FAILS:
        print(f"\n{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
