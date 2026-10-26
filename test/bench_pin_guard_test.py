"""Contract test: the harbor pin guard must refuse to run against a drifted install.

Background: a bare `uv tool install harbor` (no version, no --python) landed 0.25.0
*while a 96-trial job was running* on 2026-10-26, and the next `make test` died on an
import that had moved. `bench.sh run|dry-run` therefore hard-fails when the installed
harbor version is not the pin, with `HARBOR_ALLOW_VERSION_MISMATCH=1` as the escape
hatch. This test pins that behaviour — it never launches harbor.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "scripts" / "bench.sh"


def run_dry_run(*, pin: str | None = None, allow: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("HARBOR_")}
    if pin is not None:
        env["HARBOR_VERSION"] = pin
    if allow is not None:
        env["HARBOR_ALLOW_VERSION_MISMATCH"] = allow
    # Keep the rest of the environment (PYTHONPATH, credentials) intact: dry-run
    # validates config only and spends nothing.
    return subprocess.run(
        ["bash", str(BENCH), "dry-run", "subset"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


def installed_version() -> str | None:
    harbor = shutil.which("harbor") or str(Path(os.environ.get("HOME", "~")).expanduser() / ".local/bin/harbor")
    try:
        out = subprocess.run([harbor, "--version"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    for tok in out.split():
        if tok.count(".") == 2 and tok[0].isdigit():
            return tok
    return None


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(name)

    have = installed_version()
    check("harbor is installed (setup was run)", have is not None, "harbor --version failed")

    # 1. A version that cannot be installed must abort before harbor is invoked.
    bad = run_dry_run(pin="0.0.0-does-not-exist")
    check("mismatch exit code is 1", bad.returncode == 1, f"rc={bad.returncode}")
    check("mismatch names the installed version", "is installed but the pin is" in bad.stderr, bad.stderr[-200:])
    check("mismatch prints the fix", "setup --force" in bad.stderr, bad.stderr[-200:])
    check("mismatch does not reach harbor", "Dry run OK" not in bad.stdout, bad.stdout[-200:])

    # 2. The escape hatch must warn and then proceed to a normal dry run.
    allowed = run_dry_run(pin="0.0.0-does-not-exist", allow="1")
    check("override warns", "WARN: harbor" in allowed.stderr, allowed.stderr[-200:])
    check("override proceeds", "Dry run OK" in allowed.stdout, allowed.stdout[-200:])

    # 3. The real pin must be clean: no warning, dry run OK.
    if have:
        clean = run_dry_run(pin=have)
        check("matching pin warns nothing", "WARN: harbor" not in clean.stderr, clean.stderr[-200:])
        check("matching pin dry-runs", "Dry run OK" in clean.stdout, clean.stdout[-300:])

    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
