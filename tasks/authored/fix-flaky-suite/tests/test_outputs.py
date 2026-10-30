"""Verifier for the flaky-suite task.

Three things are checked, in the order that matters:
  1. the suite passes, repeatedly (15 consecutive runs);
  2. it still collects a real number of tests (no deletions, no blanket skips);
  3. it still FAILS when a known bug is injected — the anti-gaming check that separates
     "made the suite green" from "made the suite meaningless".
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path("/app/report")
CONSECUTIVE_RUNS = 15

# (label, old, new) — each must make the agent's suite fail in a pristine copy of the package.
MUTATIONS = [
    ("average-uses-two-values", "    return sum(values) / len(values)", "    return sum(values[:2]) / 2"),
    ("median-returns-minimum", "    ordered = sorted(values)", "    return min(values) if values else None\n    ordered = sorted(values)"),
    ("summarize-off-by-one", "f\"{label}: {counts[label]}\"" , "f\"{label}: {counts[label] + 1}\""),
]


def pytest_run(cwd, *args, extra_env=None):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/root", "PYTHONDONTWRITEBYTECODE": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, "-m", "pytest", *args], cwd=cwd, capture_output=True, text=True, env=env)


def test_suite_passes_repeatedly():
    failures = []
    for run in range(1, CONSECUTIVE_RUNS + 1):
        result = pytest_run(APP, "-q")
        if result.returncode != 0:
            failures.append(f"run {run}:\n{result.stdout[-1500:]}")
            if len(failures) >= 3:
                break
    assert not failures, "the suite is still not reliable:\n\n" + "\n\n".join(failures)


def test_suite_still_collects_real_tests():
    result = pytest_run(APP, "--collect-only", "-q")
    assert result.returncode == 0, f"collection failed:\n{result.stdout}\n{result.stderr}"
    collected = [line for line in result.stdout.splitlines() if "::" in line]
    assert len(collected) >= 6, f"only {len(collected)} tests collected (was 7): {collected}"

    sources = list((APP / "tests").rglob("test_*.py"))
    assert sources, "no test files left under tests/"
    text = "\n".join(p.read_text() for p in sources)
    for marker in ("pytest.mark.skip", "pytest.mark.xfail", "pytest.skip("):
        assert marker not in text, f"{marker} found: skipping tests is not a fix"


def test_suite_still_catches_injected_bugs():
    missed = []
    for label, old, new in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "report"
            shutil.copytree(APP, copy)
            target = copy / "stats.py"
            source = target.read_text()
            if old not in source:
                missed.append(f"{label}: could not inject the bug (stats.py changed shape:\n{source[:400]})")
                continue
            target.write_text(source.replace(old, new, 1))
            result = pytest_run(copy, "-q")
            if result.returncode == 0:
                missed.append(f"{label}: the suite passed with the bug injected")
    assert not missed, "the suite no longer catches regressions:\n- " + "\n- ".join(missed)
