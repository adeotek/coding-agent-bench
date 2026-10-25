#!/usr/bin/env python3
"""Unit tests for `bench_report.py steps` — the two transcript parsers.

Runs on stdlib only (no harbor, no docker, no spend). Fixtures are synthetic and
mirror the record shapes the real files have:

  moca   agent/moca-session.jsonl  one line per event; assistant turns are
                                   `type: message` with `message.role: assistant`
                                   and per-turn `usage`/`cost`
  others agent/trajectory.json     ATIF: `steps[]` with `source: agent` and a
                                   `metrics` block per step, plus `final_metrics`

The point of the test is the contract the reports rely on: a *turn* is one model
response (plus its tool calls), never a tool call, and the token totals must come
out the same whether they are read per step or from the final metrics.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench_report", REPO / "scripts" / "bench_report.py")
assert spec and spec.loader, "cannot load scripts/bench_report.py"
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def _moca_session(path: Path) -> None:
    records = [
        {"id": "s", "type": "session", "session": {"model": "opencode-go/deepseek-v4.1-flash"}},
        {"id": "u", "type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}},
        {"id": "a1", "type": "message", "parentId": "u",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
         "usage": {"input": 100, "output": 50, "cacheRead": 900, "cacheWrite": 0}, "cost": 0.001},
        {"id": "t1", "type": "tool_use", "toolUse": {"call": {"name": "shell", "input": {}}}},
        {"id": "r1", "type": "tool_result", "toolResult": {}},
        {"id": "a2", "type": "message", "parentId": "r1",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
         "usage": {"input": 200, "output": 25, "cacheRead": 800, "cacheWrite": 0}, "cost": 0.002},
        {"id": "t2", "type": "tool_use", "toolUse": {"call": {"name": "shell", "input": {}}}},
        {"id": "t3", "type": "tool_use", "toolUse": {"call": {"name": "read", "input": {}}}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _atif(path: Path) -> None:
    data = {
        "schema_version": "ATIF-v1.7",
        "agent": {"name": "pi", "version": "1.4.0"},
        "steps": [
            {"step_id": 1, "source": "user", "message": "go"},
            {"step_id": 2, "source": "agent", "message": "",
             "tool_calls": [{"tool_call_id": "c1", "function_name": "bash", "arguments": {}}],
             "metrics": {"prompt_tokens": 1000, "completion_tokens": 10, "cost_usd": 0.0005}},
            {"step_id": 3, "source": "agent", "message": "",
             "tool_calls": [],
             "metrics": {"prompt_tokens": 500, "completion_tokens": 5, "cost_usd": 0.0005}},
        ],
        "final_metrics": {"total_prompt_tokens": 1500, "total_completion_tokens": 15,
                          "total_cost_usd": 0.001, "total_steps": 3},
    }
    path.write_text(json.dumps(data))


def main() -> int:
    failures: list[str] = []

    def check(label: str, got, want) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  {'ok  ' if got == want else 'FAIL'} {label}: {got!r}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        moca_path, atif_path = tmp / "moca-session.jsonl", tmp / "trajectory.json"
        _moca_session(moca_path)
        _atif(atif_path)

        print("moca session →")
        moca = bench._moca_steps(moca_path)
        check("turns (assistant messages, not tool calls)", moca["turns"], 2)
        check("tools", moca["tools"], 3)
        check("input tokens (input + cacheRead)", moca["input_tokens"], 2000)
        check("output tokens", moca["output_tokens"], 75)
        check("cost", round(moca["cost"], 6), 0.003)

        print("ATIF trajectory →")
        atif = bench._atif_steps(atif_path)
        check("turns (source: agent)", atif["turns"], 2)
        check("tools", atif["tools"], 1)
        check("input tokens", atif["input_tokens"], 1500)
        check("output tokens", atif["output_tokens"], 15)
        check("cost", round(atif["cost"], 6), 0.001)

        print("cap resolution →")
        caps = {"Moca": 250, "OpenCodeV2": 200}
        check("moca resolves to its cap", bench._cap_for("moca", caps), 250)
        check("opencode resolves by prefix", bench._cap_for("opencode", caps), 200)
        check("unknown agent has no cap", bench._cap_for("pi", caps), None)

        print("missing transcript →")
        check("absent session", bench._moca_steps(tmp / "nope.jsonl"), None)

    if failures:
        print("\nFAILED:\n  " + "\n  ".join(failures))
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
