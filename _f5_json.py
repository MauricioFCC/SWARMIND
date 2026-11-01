"""F5 count + lista por-archivo (via check_function_size real)."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter

CODE = (
    "import sys; sys.path.insert(0, 'scripts'); "
    "import check_architecture as c; "
    "import json; "
    "print(json.dumps(c.check_function_size()))"
)

proc = subprocess.run(
    [sys.executable, "-X", "utf8", "-c", CODE],
    capture_output=True,
    text=True,
    timeout=600,
)
findings = json.loads(proc.stdout)
counter = Counter()
for finding in findings:
    marker = "SWARMIND\\"
    tail = finding.split(marker, 1)[1]
    name = tail.replace("\\", "/").split("/")[-1]
    counter[name] += 1
print("total:", len(findings))
for name, n in counter.most_common(18):
    print(f"  {name}: {n}")
