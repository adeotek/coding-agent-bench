#!/usr/bin/env python3
"""Render the effective Harbor JobConfig for a benchmark profile.

Profiles
--------
smoke   the hello-world task, all agents (pipeline + auth check)
subset  terminal-bench@2.0, first N_TASKS tasks (cheap iteration)
full    terminal-bench@2.0, all tasks

Configuration is read from environment variables with defaults (see
.env.example); results/effective-<profile>.json is written and its path is
printed to stdout. Diagnostics go to stderr so callers can capture the path.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"render_config: {name}={raw!r} is not an integer")


def agents(_profile: str) -> list[dict]:
    zen = env("ZEN_MODEL", "opencode-go/glm-5.3-flash")
    claude = env("CLAUDE_MODEL", "anthropic/claude-sonnet-5")
    entries: list[tuple[str, dict]] = [
        (
            "moca",
            {
                "import_path": "agents.moca:Moca",
                "model_name": zen,
                "kwargs": {
                    "version": env("MOCA_VERSION", "v0.6.5"),
                    "max_steps": env_int("MOCA_MAX_STEPS", 100),
                },
            },
        ),
        (
            "opencode",
            {
                # OpenCode v2 renamed the npm package (opencode-ai →
                # @opencode/cli) and moved --model onto `run` — Harbor 0.24.0's
                # built-in opencode agent only drives v1. The subclass fixes
                # install + the run command and inherits everything else.
                "import_path": "agents.opencode_v2:OpenCodeV2",
                "model_name": zen,
                "kwargs": {"version": env("OPENCODE_VERSION", "2.0.30")},
            },
        ),
        (
            "pi",
            {
                "name": "pi",
                "model_name": zen,
                "kwargs": {"version": env("PI_VERSION", "1.3.0")},
            },
        ),
        (
            "claude-code",
            {
                "name": "claude-code",
                "model_name": claude,
                "kwargs": {"version": env("CLAUDE_VERSION", "2.1.301")},
            },
        ),
    ]
    selected = env("AGENTS")
    if selected:
        wanted = [s.strip() for s in selected.split(",") if s.strip()]
        unknown = [w for w in wanted if w not in {k for k, _ in entries}]
        if unknown:
            sys.exit(f"render_config: unknown AGENTS entries: {', '.join(unknown)}")
        entries = [(k, v) for k, v in entries if k in wanted]
    return [v for _, v in entries]


def build(profile: str) -> dict:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    cfg: dict = {
        "job_name": f"cab-{profile}-{stamp}",
        "jobs_dir": env("JOBS_DIR", "results/jobs"),
        "n_attempts": env_int("N_ATTEMPTS", 1),
        "n_concurrent_trials": env_int("N_CONCURRENT", 2),
        "environment": {"type": "docker"},
        "agents": agents(profile),
    }
    if profile == "smoke":
        cfg["tasks"] = [{"name": "hello-world/hello-world"}]
        return cfg
    dataset: dict = {
        "name": env("TB_DATASET", "terminal-bench"),
        "version": env("TB_VERSION", "2.0"),
    }
    if profile == "subset":
        names = env("TASK_NAMES")
        if names:
            dataset["task_names"] = [s.strip() for s in names.split(",") if s.strip()]
        else:
            dataset["n_tasks"] = env_int("N_TASKS", 20)
    cfg["datasets"] = [dataset]
    return cfg


def main() -> None:
    argv = sys.argv[1:]
    out_arg = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 >= len(argv):
            sys.exit("render_config: -o needs a path")
        out_arg = argv[i + 1]
        del argv[i : i + 2]
    profile = argv[0] if argv else "subset"
    if profile not in ("smoke", "subset", "full"):
        sys.exit(f"render_config: unknown profile {profile!r} (smoke|subset|full)")
    cfg = build(profile)
    out = Path(out_arg) if out_arg else REPO / "results" / f"effective-{profile}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    main()
