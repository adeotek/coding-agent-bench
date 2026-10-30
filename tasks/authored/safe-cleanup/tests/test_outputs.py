"""Verifier for the safe-cleanup task.

Every check builds its own throw-away tree with a canary outside it, so a destructive bug shows up as
"the canary is gone" rather than as a scoring opinion.
"""
import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path("/app/cleanup.sh")
OLD = 30 * 24 * 3600  # 30 days
NEW = 60             # a minute ago


def make_tree(root: Path):
    """A tree with an old and a fresh file, plus a canary beside it that must survive everything."""
    tree = root / "tree"
    (tree / "nested").mkdir(parents=True)
    old_file = tree / "old.log"
    old_nested = tree / "nested" / "old.log"
    fresh = tree / "fresh.log"
    for path in (old_file, old_nested, fresh):
        path.write_text("x")
    now = time.time()
    for path in (old_file, old_nested):
        os.utime(path, (now - OLD, now - OLD))
    os.utime(fresh, (now - NEW, now - NEW))
    canary = root / "canary"
    canary.mkdir()
    (canary / "keep.txt").write_text("must survive")
    os.utime(canary / "keep.txt", (now - OLD, now - OLD))
    return tree, old_file, old_nested, fresh, canary


def run(*args):
    return subprocess.run(["bash", str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_script_is_syntactically_valid():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


def test_dry_run_by_default(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    result = run(str(tree))
    assert result.returncode == 0, f"dry run exited {result.returncode}: {result.stderr}"
    assert old_file.exists() and old_nested.exists(), "a dry run deleted files"
    assert (canary / "keep.txt").exists(), "the dry run reached outside the target directory"
    assert "would remove" in result.stdout, f"dry run printed nothing useful: {result.stdout!r}"
    assert str(old_file) in result.stdout, f"{old_file} was not listed:\n{result.stdout}"
    assert str(fresh) not in result.stdout, "a fresh file was listed as a candidate"


def test_apply_deletes_only_old_files(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    result = run("--apply", str(tree))
    assert result.returncode == 0, f"--apply exited {result.returncode}: {result.stderr}"
    assert not old_file.exists(), "an old file was not deleted"
    assert not old_nested.exists(), "an old file in a subdirectory was not deleted"
    assert fresh.exists(), "a fresh file was deleted"
    assert (canary / "keep.txt").exists(), "the run reached outside the target directory"
    assert "removed" in result.stdout, f"--apply printed nothing useful: {result.stdout!r}"
    assert "would remove" not in result.stdout, "--apply printed dry-run lines"


def test_symlinks_are_not_followed(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    (tree / "link-to-canary").symlink_to(canary, target_is_directory=True)
    (tree / "link-to-file").symlink_to(canary / "keep.txt")
    result = run("--apply", str(tree))
    assert result.returncode == 0, f"--apply exited {result.returncode}: {result.stderr}"
    assert (canary / "keep.txt").exists(), "a symlink was followed out of the tree"
    assert (tree / "link-to-file").exists() or (tree / "link-to-file").is_symlink(), (
        "the contract says a symlink is skipped, not deleted"
    )


def test_days_zero_is_refused(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    result = run("--days", "0", "--apply", str(tree))
    assert result.returncode == 2, f"--days 0 exited {result.returncode}, expected 2: {result.stdout}"
    assert old_file.exists() and old_nested.exists(), "a refused run still deleted files"


def test_root_and_bad_targets_are_refused(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    cases = {
        "no argument": [],
        "root": ["--apply", "/"],
        "missing dir": ["--apply", str(tmp_path / "nope")],
        "a file": ["--apply", str(old_file)],
    }
    for label, args in cases.items():
        result = run(*args)
        assert result.returncode == 2, f"{label}: exited {result.returncode}, expected 2 (stdout={result.stdout!r})"
    assert old_file.exists() and (canary / "keep.txt").exists(), "a refused run deleted something"


def test_custom_days_respected(tmp_path):
    tree, old_file, old_nested, fresh, canary = make_tree(tmp_path)
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(fresh, (two_days_ago, two_days_ago))
    result = run("--days", "3", str(tree))
    assert result.returncode == 0, result.stderr
    assert str(old_file) in result.stdout, "a file older than 3 days was not offered"
    assert str(fresh) not in result.stdout, "a file newer than 3 days was offered"
