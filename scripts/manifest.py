#!/usr/bin/env python3
"""Run manifest: what exactly produced a job directory.

The job store records trials, and `config.json` records the requested config, but
neither records the *toolchain*: Harbor's version, the interpreter it ran under,
the commit of this repo, or the knobs that were set in the launching shell. That
gap is how 0.25.0 landed during a 96-trial job and nobody noticed until an import
broke — and it is why two jobs cannot be compared unless you can prove what they
ran.

`start` is written by `bench.sh run` before Harbor is launched (so it survives a
crash), `finish` enriches it afterwards with duration, exit code, per-agent trial
counts and image digests, and copies it into the job directory as `manifest.json`.

Usage:
  manifest.py start  --config <rendered.json> --job-name <name> --out <path>
                     [--harbor-version V] [--harbor-python V] [--knob K=V ...]
  manifest.py finish --manifest <path> --job-dir <dir> --exit-code <n>
                     [--finished-at ISO]

Everything is best-effort: a manifest that cannot collect a fact records null and
says why in `notes`, because losing the manifest must never lose the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Keys that describe the *experiment*. Two jobs may only be compared when these
# agree; the config hash and job name deliberately are not here.
COMPARABLE_KEYS = (
    "harbor.version",
    "harbor.python",
    "repo.commit",
    "dataset.version",
    "dataset.task_list_sha256",
    "agents",
    "knobs",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_json(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def repo_state(repo: Path) -> dict:
    commit = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    status = run(["git", "-C", str(repo), "status", "--porcelain"])
    branch = run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "commit": commit,
        "short": commit[:7] if commit else None,
        "branch": branch,
        "dirty": None if status is None else bool(status.strip()),
    }


def agents_of(config: dict) -> list[dict]:
    out = []
    for a in config.get("agents") or []:
        ident = a.get("import_path") or a.get("name")
        out.append(
            {
                "id": ident,
                "model": a.get("model_name"),
                "version": (a.get("kwargs") or {}).get("version"),
                "kwargs": a.get("kwargs") or {},
            }
        )
    return out


def dataset_of(config: dict) -> dict:
    ds = (config.get("datasets") or [{}])[0]
    tasks = list(ds.get("task_names") or [])
    return {
        "name": ds.get("name"),
        "version": ds.get("version"),
        "n_tasks": len(tasks),
        "task_list_sha256": sha256_json(sorted(tasks)) if tasks else None,
    }


def trial_counts(job_dir: Path) -> dict:
    """Trials per agent, read back from result.json rather than assumed."""
    by_agent: dict[str, int] = {}
    total = 0
    if not job_dir.is_dir():
        return {"total": 0, "by_agent": by_agent}
    for trial in sorted(job_dir.iterdir()):
        rp = trial / "result.json"
        if not rp.is_file():
            continue
        total += 1
        try:
            agent = (json.loads(rp.read_text()).get("agent_info") or {}).get("name") or "unknown"
        except Exception:
            agent = "unknown"
        by_agent[agent] = by_agent.get(agent, 0) + 1
    return {"total": total, "by_agent": by_agent}


def image_digests(job_dir: Path) -> dict:
    """Repo digests for the images this job actually used, when docker still has them.

    Best-effort by design: images get pruned, and a missing digest is a null, not
    a failure. The point is to make "same sandbox" checkable months later.

    `docker images --filter reference=*<task>*` does NOT match partially-qualified
    names, so this lists images once and matches task names in Python.
    """
    digests: dict[str, str | None] = {}
    if not job_dir.is_dir() or run(["docker", "version", "--format", "{{.Server.Version}}"]) is None:
        return {}
    listing = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]) or ""
    available = [line.strip() for line in listing.splitlines() if line.strip()]
    tasks = []
    for trial in sorted(job_dir.iterdir()):
        rp = trial / "result.json"
        if not rp.is_file():
            continue
        try:
            task = json.loads(rp.read_text()).get("task_name") or trial.name.split("__")[0]
        except Exception:
            task = trial.name.split("__")[0]
        if task not in tasks:
            tasks.append(task)
    for task in tasks:
        ref = next((r for r in available if f"/{task}:" in r or f":{task}" in r), None)
        digests[task] = run(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", ref]) if ref else None
    return digests


def cmd_start(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    repo = Path(__file__).resolve().parent.parent
    knobs = {}
    for pair in args.knob or []:
        k, _, v = pair.partition("=")
        knobs[k] = v
    manifest = {
        "job_name": args.job_name,
        "schema": 1,
        "started_at": args.started_at or now(),
        "finished_at": None,
        "duration_s": None,
        "harbor_exit_code": None,
        "harbor": {"version": args.harbor_version, "python": args.harbor_python},
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cpus": os.cpu_count(),
        },
        "repo": repo_state(repo),
        "config": {
            "path": str(config_path),
            "sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "n_attempts": config.get("n_attempts"),
            "n_concurrent_trials": config.get("n_concurrent_trials"),
        },
        "dataset": dataset_of(config),
        "agents": agents_of(config),
        "knobs": knobs,
        "trials": None,
        "images": None,
        "notes": [],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest: {out}")
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    manifest = json.loads(path.read_text())
    job_dir = Path(args.job_dir)
    manifest["finished_at"] = args.finished_at or now()
    manifest["harbor_exit_code"] = args.exit_code
    try:
        started = datetime.fromisoformat(manifest["started_at"])
        finished = datetime.fromisoformat(manifest["finished_at"])
        manifest["duration_s"] = round((finished - started).total_seconds(), 1)
    except Exception:
        manifest["notes"].append("duration unavailable")
    manifest["trials"] = trial_counts(job_dir)
    images = image_digests(job_dir)
    manifest["images"] = images or None
    if not images:
        manifest["notes"].append("image digests unavailable (docker missing or images pruned)")
    missing = [k for k, v in {"harbor.version": manifest["harbor"]["version"],
                              "harbor.python": manifest["harbor"]["python"],
                              "repo.commit": manifest["repo"]["commit"]}.items() if not v]
    if missing:
        manifest["notes"].append(f"missing: {', '.join(missing)}")
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    if job_dir.is_dir():
        (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        print(f"manifest: {job_dir / 'manifest.json'}")
    else:
        print(f"manifest: {path} (job dir {job_dir} absent — run may have failed before creating it)")
    return 0


def comparable(manifest: dict) -> dict:
    """The subset of a manifest that must match for two jobs to be comparable."""
    return {
        "harbor.version": (manifest.get("harbor") or {}).get("version"),
        "harbor.python": (manifest.get("harbor") or {}).get("python"),
        "repo.commit": (manifest.get("repo") or {}).get("commit"),
        "dataset.version": (manifest.get("dataset") or {}).get("version"),
        "dataset.task_list_sha256": (manifest.get("dataset") or {}).get("task_list_sha256"),
        "agents": manifest.get("agents"),
        "knobs": manifest.get("knobs"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--config", required=True)
    start.add_argument("--job-name", required=True)
    start.add_argument("--out", required=True)
    start.add_argument("--harbor-version")
    start.add_argument("--harbor-python")
    start.add_argument("--knob", action="append", default=[])
    start.add_argument("--started-at")
    start.set_defaults(func=cmd_start)

    finish = sub.add_parser("finish")
    finish.add_argument("--manifest", required=True)
    finish.add_argument("--job-dir", required=True)
    finish.add_argument("--exit-code", type=int, required=True)
    finish.add_argument("--finished-at")
    finish.set_defaults(func=cmd_finish)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
