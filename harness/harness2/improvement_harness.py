"""Improvement harness: persistent lessons + adopted harnesses (Harness2-inspired)."""

from __future__ import annotations

import json
from pathlib import Path

from .components import HarnessTree
from .library import HarnessLibrary


class ImprovementHarness:
    """Persistent improvement harness updated with adopted harnesses + lessons."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.library = HarnessLibrary(self.base_dir / "library")
        self._lessons_path = self.base_dir / "lessons.jsonl"

    def lessons(self) -> list[str]:
        out: list[str] = []
        if self._lessons_path.exists():
            for line in self._lessons_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("lesson"):
                        out.append(str(obj["lesson"]))
                except json.JSONDecodeError:
                    continue
        out.extend(self.library.lessons())
        return out

    def update(self, harness_id: str, tree: HarnessTree, *, lesson: str = "") -> None:
        self.library.adopt(harness_id, tree, notes=lesson)
        if lesson:
            with self._lessons_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"harness_id": harness_id, "lesson": lesson}, ensure_ascii=False) + "\n")

    def guidance(self) -> str:
        ls = self.lessons()
        if not ls:
            return ""
        return "Lessons:\n" + "\n".join("- " + l for l in ls[-20:])
