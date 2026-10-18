#!/usr/bin/env python3
"""Exercise agents.moca.run_command against a mock moca binary.

The session transcript is what carries moca's token/cost accounting, and
Harbor kills the agent phase on a timeout (900 s) or a cancel — so the copy at
the end of the run line never executes on exactly the runs whose metrics
matter most. `run_command()` therefore starts a background mirror that
refreshes the copy every few seconds while the run is in flight.

Run it with the Harbor tool environment (the adapter imports harbor):

    PYTHONPATH=$PWD "$(uv tool dir)/harbor/bin/python" test/moca_run_command_test.py

Cases:
  A killed   — SIGTERM mid-run: the mirror must still leave a parseable copy.
  B clean    — exit 0: the final copy is authoritative, exit code propagates.
  C exit 3   — moca's step-budget exit still propagates, copy intact.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from agents.moca import run_command  # noqa: E402


def make_repo(tmp: Path, entries: int, exit_code: int) -> None:
    """A fake HOME with a mock `moca` that appends one session entry per second."""
    home = tmp / "home"
    bin_dir = tmp / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    (home / ".local/share/moca/sessions").mkdir(parents=True)
    bin_dir.mkdir()
    mock = bin_dir / "moca"
    mock.write_text(
        "#!/bin/sh\n"
        's="$HOME/.local/share/moca/sessions/sess.jsonl"\n'
        f"i=0\nwhile [ $i -lt {entries} ]; do\n"
        '  printf \'{"usage":{"input":1000,"output":10,"cacheRead":500},"cost":0.002}\\n\' >> "$s"\n'
        "  i=$((i+1)); sleep 1\n"
        "done\n"
        f"exit {exit_code}\n"
    )
    mock.chmod(0o755)


def run(tmp: Path, timeout_s: int | None) -> tuple[int, Path]:
    logs = tmp / "logs"
    logs.mkdir(exist_ok=True)
    session_copy = logs / "moca-session.jsonl"
    cmd = run_command("do the thing", "--mode yolo", str(logs / "moca.txt"), str(session_copy))
    env = dict(os.environ, HOME=str(tmp / "home"), PATH=f"{tmp}/bin:" + os.environ["PATH"])
    if timeout_s:
        proc = subprocess.run(["timeout", "-s", "TERM", str(timeout_s), "sh", "-c", cmd], env=env)
    else:
        proc = subprocess.run(["sh", "-c", cmd], env=env)
    return proc.returncode, session_copy


def entries(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a copy caught mid-append leaves a partial line
    return out


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        make_repo(tmp, entries=40, exit_code=0)
        rc, copy = run(tmp, timeout_s=8)
        got = entries(copy)
        print(f"A killed : rc={rc} entries={len(got)} (mirror copy, >=1 expected)")
        ok &= rc == 124 and len(got) >= 1

        shutil.rmtree(tmp / "home")
        make_repo(tmp, entries=3, exit_code=0)
        rc, copy = run(tmp, timeout_s=None)
        got = entries(copy)
        print(f"B clean  : rc={rc} entries={len(got)} (3 expected)")
        ok &= rc == 0 and len(got) == 3

        shutil.rmtree(tmp / "home")
        make_repo(tmp, entries=2, exit_code=3)
        rc, copy = run(tmp, timeout_s=None)
        got = entries(copy)
        print(f"C exit 3 : rc={rc} entries={len(got)} (2 expected)")
        ok &= rc == 3 and len(got) == 2

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
