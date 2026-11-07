"""Library of adopted harnesses (Harness2-inspired)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .components import HarnessTree


class HarnessLibrary:
    """Persistent library of adopted harnesses + lessons."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "index.json"

    def _load_index(self) -> list[dict[str, Any]]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
        return []

    def _save_index(self, items: list[dict[str, Any]]) -> None:
        self._index_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def adopt(self, harness_id: str, tree: HarnessTree, *, notes: str = "") -> None:
        items = self._load_index()
        items.append({"id": harness_id, "tree": tree.to_dict(), "notes": notes})
        self._save_index(items)
        (self.base_dir / (f"{harness_id}.json")).write_text(
            json.dumps(tree.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, harness_id: str) -> HarnessTree | None:
        p = self.base_dir / (f"{harness_id}.json")
        if not p.exists():
            return None
        try:
            return HarnessTree.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return None

    def list_ids(self) -> list[str]:
        return [e.get("id", "") for e in self._load_index()]

    def lessons(self) -> list[str]:
        items = self._load_index()
        return [e.get("notes", "") for e in items if e.get("notes")]
