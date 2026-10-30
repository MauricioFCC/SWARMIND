from __future__ import annotations

import subprocess
import sys

run = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "harness", "scripts", "--statistics"],
    capture_output=True, text=True, check=False,
)
print("rc", run.returncode)
print("\n".join((run.stdout or "").strip().splitlines()[:20]))
run2 = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "harness", "scripts"],
    capture_output=True, text=True, check=False,
)
print("\n".join((run2.stdout or "").strip().splitlines()[:8]))
