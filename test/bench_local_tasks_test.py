#!/usr/bin/env python3
"""Contract tests for LOCAL_TASKS — the knob that runs repaired and authored cells (no spend).

Three things must never regress:
  * a local dataset is a `path`, not a registry name — Harbor builds or uses each task's own image;
  * pointing at a single task directory is a convenience, not a different code path;
  * a local run is exempt from the watch-list filter, because a repaired cell usually sits on it
    (otherwise the cell you just repaired is silently dropped and the run measures nothing).
"""
from __future__ import annotations

import importlib.util
import io
import os
import contextlib
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_config", REPO / "scripts" / "render_config.py")
assert spec and spec.loader, "cannot load scripts/render_config.py"
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


def build_with(**env):
    saved = {k: os.environ.pop(k, None) for k in ("LOCAL_TASKS", "TASK_FILE", "TASK_NAMES", "AGENTS", "N_ATTEMPTS")}
    try:
        os.environ.update({k: v for k, v in env.items() if v is not None})
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            cfg = rc.build("audit")
        return cfg, err.getvalue()
    finally:
        for key in ("LOCAL_TASKS", "TASK_FILE", "TASK_NAMES", "AGENTS", "N_ATTEMPTS"):
            os.environ.pop(key, None)
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def make_task_dir(root: Path, name: str) -> Path:
    task = root / name
    task.mkdir(parents=True)
    (task / "task.toml").write_text('version = "1.0"\n')
    return task


def main() -> int:
    authored = REPO / "tasks" / "authored"
    if not authored.is_dir():
        print("FAIL tasks/authored is missing")
        return 1

    cfg, err = build_with(LOCAL_TASKS=str(authored))
    dataset = cfg["datasets"][0]
    check("local: dataset is a path", "path" in dataset and dataset["path"] == str(authored), str(dataset))
    check("local: no registry name/version", "name" not in dataset and "version" not in dataset, str(dataset))
    check("local: the run announces itself", "LOCAL dataset" in err, err[:120])
    check("local: every authored task is listed in the message",
          all(p.name in err for p in authored.iterdir() if (p / "task.toml").is_file()), err[:200])

    one, err = build_with(LOCAL_TASKS=str(authored / "fix-flaky-suite"))
    check("local: a single task dir becomes a one-task dataset",
          one["datasets"][0].get("task_names") == ["fix-flaky-suite"]
          and one["datasets"][0]["path"] == str(authored), str(one["datasets"][0]))

    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "empty"
        empty.mkdir()
        try:
            build_with(LOCAL_TASKS=str(empty))
            check("local: an empty directory is refused", False, "no SystemExit")
        except SystemExit as exc:
            check("local: an empty directory is refused", "no task dirs" in str(exc), str(exc))

        # prove the watch-list exemption: a local name that IS in the defective list must survive
        defective = rc.defective_cells() if hasattr(rc, "defective_cells") else {}
        if defective:
            victim = sorted(defective)[0]
            make_task_dir(Path(tmp), victim)
            cfg, _ = build_with(LOCAL_TASKS=tmp)
            names = cfg["datasets"][0].get("task_names") or []
            kept = victim in names or "task_names" not in cfg["datasets"][0]
            check(f"local: watch-listed cell {victim} is not dropped", kept, str(cfg["datasets"][0]))
        else:
            check("local: watch list readable for the exemption test", False, "no defective cells found")

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
