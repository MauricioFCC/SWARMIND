"""Diff de funciones >30 lineas entre HEAD y el working tree (F5)."""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent


def f5_counts() -> tuple[int, Counter[str]]:
    """Cuenta total + por-archivo de funciones >30 lineas del arbol actual."""
    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            (
                "import sys; sys.path.insert(0, 'scripts'); "
                "import check_architecture as c;"
                "[print(e) for e in c.check_function_size()]"
            ),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    counter: Counter[str] = Counter()
    total = 0
    for line in (proc.stdout or "").splitlines():
        if "lineas > 30" not in line:
            continue
        total += 1
        file_part = line.split(":", 1)[0]
        name = file_part.replace("\\", "/").split("/")[-1]
        counter[name] += 1
    return total, counter


if __name__ == "__main__":
    total, counter = f5_counts()
    print("total:", total)
    for name, n in counter.most_common(15):
        print(f"  {name}: {n}")
