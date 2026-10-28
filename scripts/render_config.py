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
import re
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


def agents(profile: str) -> list[dict]:
    # The audit profile is Harbor's own oracle/nop pair: no model, no key, no tokens.
    # oracle must solve every task as specified; nop must fail every verifier.
    if profile == "audit":
        return [{"name": "oracle"}, {"name": "nop"}]
    zen = env("ZEN_MODEL", "opencode-go/deepseek-v4.1-flash")
    claude = env("CLAUDE_MODEL", "anthropic/claude-sonnet-5")
    entries: list[tuple[str, dict]] = [
        (
            "moca",
            {
                "import_path": "agents.moca:Moca",
                "model_name": zen,
                "kwargs": {
                    "version": env("MOCA_VERSION", "v0.7.11"),
                    "max_steps": env_int("MOCA_MAX_STEPS", 250),
                    # Rendered, not inherited: v0.7.2 changed moca's default
                    # permission mode to `auto`, so the protocol's yolo stance
                    # has to be visible in the recorded job config.
                    "mode": env("MOCA_MODE", "yolo"),
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
                "kwargs": {"version": env("OPENCODE_VERSION", "2.1.4")},
            },
        ),
        (
            "pi",
            {
                "name": "pi",
                "model_name": zen,
                "kwargs": {"version": env("PI_VERSION", "1.4.0")},
            },
        ),
        (
            "claude-code",
            {
                "name": "claude-code",
                "model_name": claude,
                "kwargs": {"version": env("CLAUDE_VERSION", "2.1.310")},
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


def parse_shard(raw: str | None) -> tuple[int, int] | None:
    if raw in (None, ""):
        return None
    m = re.fullmatch(r"(\d+)/(\d+)", raw.strip())
    if not m:
        sys.exit(f"render_config: SHARD={raw!r} must look like k/n (1-based, k <= n)")
    k, n = int(m.group(1)), int(m.group(2))
    if n < 1 or not 1 <= k <= n:
        sys.exit(f"render_config: SHARD={raw!r}: need n >= 1 and 1 <= k <= n")
    return k, n


def shard_slice(names: list[str], shard: tuple[int, int]) -> list[str]:
    """Contiguous ceil-sized blocks, so the shards are disjoint and their union
    is the input list — the property the report uses to stitch a run back
    together. Contiguous rather than round-robin so a shard stays a *slice* of
    the ordered list (docs/tb2-all.txt puts the cheap cells first)."""
    k, n = shard
    size = -(-len(names) // n)
    start = (k - 1) * size
    return names[start : start + size]

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
    task_file = env("TASK_FILE")
    if task_file:
        path = Path(task_file)
        if not path.is_absolute():
            path = REPO / path
        if not path.is_file():
            sys.exit(f"render_config: TASK_FILE={task_file} does not exist")
        names = [
            line.split()[0]
            for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not names:
            sys.exit(f"render_config: TASK_FILE={task_file} lists no tasks")
        dataset["task_names"] = drop_defective(names, profile)
    elif profile == "subset":
        names = env("TASK_NAMES")
        if names:
            dataset["task_names"] = drop_defective([s.strip() for s in names.split(",") if s.strip()], profile)
        else:
            dataset["n_tasks"] = env_int("N_TASKS", 20)
    # A shard is a slice of an explicit list; slicing an n_tasks dataset would
    # mean guessing which tasks Harbor picks, so refuse rather than pretend.
    shard = parse_shard(env("SHARD"))
    if shard:
        if "task_names" not in dataset:
            sys.exit("render_config: SHARD needs an explicit task list (TASK_FILE or TASK_NAMES)")
        full = dataset["task_names"]
        sliced = shard_slice(full, shard)
        if not sliced:
            sys.exit(f"render_config: SHARD={shard[0]}/{shard[1]} selects no tasks from {len(full)}")
        dataset["task_names"] = sliced
        print(
            f"render_config: shard {shard[0]}/{shard[1]} -> {len(sliced)} of {len(full)} tasks",
            file=sys.stderr,
        )
    cfg["datasets"] = [dataset]
    return cfg


WATCH_LIST = "docs/tb2-watch.txt"


def defective_cells() -> dict[str, str]:
    """Cells the audit says cannot produce an agent signal (docs/tb2-watch.txt).

    Derived from oracle/nop verdicts, not maintained by hand. Missing file = no
    opinion (a fresh clone before the first audit), never a silent allow-list.
    """
    path = REPO / WATCH_LIST
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        out[parts[0]] = parts[1] if len(parts) > 1 else "not-healthy"
    return out


def drop_defective(names: list[str], profile: str) -> list[str]:
    """Keep agent money off cells whose own reference solution fails.

    A broken cell cannot yield a pass-or-fail signal: a loss is the task's fault and
    a win is noise. Scoring one fabricates a regression, so they are dropped — loudly,
    and by name, so it is visible in the run log and in the rendered config. The audit
    profile is exempt: finding these cells is its whole job.
    """
    if profile == "audit" or os.environ.get("ALLOW_DEFECTIVE") == "1":
        return names
    bad = {n: defective_cells()[n] for n in names if n in defective_cells()}
    if not bad:
        return names
    kept = [n for n in names if n not in bad]
    detail = ", ".join(f"{n} ({c})" for n, c in sorted(bad.items()))
    print(f"render_config: dropping {len(bad)} non-measurable cell(s): {detail}", file=sys.stderr)
    print(
        f"render_config: they are on {WATCH_LIST} (docs/task-defects.md explains each) and cannot "
        "produce an agent signal; ALLOW_DEFECTIVE=1 keeps them anyway",
        file=sys.stderr,
    )
    if not kept:
        sys.exit("render_config: every requested cell is non-measurable — nothing to run")
    return kept


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
    if profile not in ("smoke", "subset", "full", "audit"):
        sys.exit(f"render_config: unknown profile {profile!r} (smoke|subset|full|audit)")
    cfg = build(profile)
    out = Path(out_arg) if out_arg else REPO / "results" / f"effective-{profile}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    main()
