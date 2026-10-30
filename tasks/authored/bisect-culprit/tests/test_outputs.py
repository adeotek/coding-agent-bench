"""Verifier for the bisect task.

The expected culprit lives here rather than in the image: `/tests` is mounted only during
verification, so the agent cannot read the answer, and the history is built with fixed dates and
identities so the commit id is stable.
"""
import re
import subprocess
import sys
from pathlib import Path

APP = Path("/app/calc")
CULPRIT_SHA = "9033770a8ac09b174e76e012bdc6b134b254b54c"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def git(*args):
    return subprocess.run(["git", *args], cwd=APP, capture_output=True, text=True)


def pytest_run():
    return subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=APP, capture_output=True, text=True)


def test_suite_passes():
    result = pytest_run()
    assert result.returncode == 0, f"the suite still fails:\n{result.stdout[-2000:]}"


def test_culprit_file_has_a_full_sha():
    path = Path("/app/culprit.txt")
    assert path.exists(), "/app/culprit.txt does not exist"
    value = path.read_text().strip()
    assert HEX40.match(value), f"/app/culprit.txt must hold one full 40-character SHA, got {value!r}"


def test_culprit_is_the_right_commit():
    value = Path("/app/culprit.txt").read_text().strip()
    assert value == CULPRIT_SHA, (
        f"named {value}, but the regression was introduced by {CULPRIT_SHA} "
        f"({git('log', '-1', '--format=%s', CULPRIT_SHA).stdout.strip()!r})"
    )


def test_history_was_not_rewritten():
    log = git("log", "--format=%H", CULPRIT_SHA, "..HEAD")
    assert log.returncode == 0, f"the named commit is not in this repository's history: {log.stderr}"
    count = len([line for line in log.stdout.splitlines() if line.strip()])
    assert count <= 1, f"{count} commits sit on top of the culprit; the task allows a fix, not a new history"


def test_the_test_that_covers_the_bug_is_unchanged():
    """A fix may change the code; weakening or deleting the assertion is not a fix."""
    tests = " ".join((APP / "tests" / "test_ops.py").read_text().split())
    assert "apply_discount(200, 10) == 180" in tests, (
        "the assertion covering the regression was removed or weakened"
    )
