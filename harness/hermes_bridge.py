#!/usr/bin/env python3
"""
hermes_bridge.py — Puente bidireccional AGENTIC ↔ Hermes_Memory_Proyects.

Sincroniza la cognition store (asi_cognition_store) del harness AGENTIC
con el sistema de memoria externo Hermes_Memory_Proyects.

Flujo:
  - sync_to_hermes(): Exporta entries de asi_cognition_store → Hermes syntheses/ + knowledge/
  - sync_from_hermes(): Importa entries de Hermes → asi_cognition_store

Formato de archivos en Hermes:
  syntheses/{slug}.md  →  YAML frontmatter (title, domain, tags, date) + markdown body
  knowledge/{slug}.md  →  Similar estructura

Compatibilidad: Hermes usa lancedb_data como vector store propio.

Uso:
    bridge = HermesBridge()
    bridge.sync_to_hermes()       # Exporta cognition store → archivos .md
    bridge.sync_from_hermes()     # Importa archivos .md → cognition store
    bridge.sync_all()             # Bidireccional completo
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Hermes root (external repo) — set via env var HERMES_ROOT or config
DEFAULT_HERMES_ROOT = Path(
    os.environ.get("HERMES_ROOT", "")
    or os.environ.get("HERMES_HOME", "")
    or ""
)

# Hermes subdirectories
HERMES_SYNTHESES_DIR = "syntheses"
HERMES_KNOWLEDGE_DIR = "knowledge"
HERMES_SKILLS_DIR = "skills"
HERMES_PROJECTS_DIR = "projects"
HERMES_LANCEDB_DIR = "99_Hermes_Brain/lancedb_data"

# AGENTIC collections
ASI_COLLECTION = "asi_cognition_store"
RAG_COLLECTION = "rag_chunks"


class HermesBridge:
    """
    Puente bidireccional AGENTIC ↔ Hermes_Memory_Proyects.

    Uso:
        bridge = HermesBridge()
        bridge.sync_to_hermes()       # Exporta cognition store → archivos .md
        bridge.sync_from_hermes()     # Importa archivos .md → cognition store
        bridge.sync_all()             # Bidireccional completo
    """

    def __init__(
        self,
        hermes_root: Optional[Path] = None,
        vector_store: Optional[LanceVectorStore] = None,
    ):
        self.hermes_root = Path(hermes_root or DEFAULT_HERMES_ROOT)
        self._store = vector_store or LanceVectorStore()
        self._stats: Dict[str, Any] = {
            "exported": 0,
            "imported": 0,
            "errors": 0,
        }

        if not self.hermes_root or not str(self.hermes_root):
            logger.warning(
                "Hermes root is empty. Set HERMES_ROOT or HERMES_HOME env var to enable sync."
            )
        elif not self.hermes_root.exists():
            logger.warning(
                "Hermes root not found: %s. Set HERMES_ROOT or HERMES_HOME env var.",
                self.hermes_root,
            )

    # ------------------------------------------------------------------
    # Export: AGENTIC → Hermes
    # ------------------------------------------------------------------

    def sync_to_hermes(self, max_entries: int = 50) -> Dict[str, Any]:
        """
        Export cognition entries from AGENTIC asi_cognition_store
        to Hermes syntheses/ and knowledge/ as .md files.

        Returns dict with export stats.
        """
        if not self.hermes_root.exists():
            logger.error("Cannot export: Hermes root %s not found", self.hermes_root)
            return {"error": "Hermes root not found"}

        # 1. Pull entries from LanceDB
        entries = self._get_cognition_entries(max_entries)

        # 2. Classify entries by domain/content
        syntheses, knowledge = self._classify_entries(entries)

        # 3. Write .md files
        syn_count = self._write_hermes_files(syntheses, HERMES_SYNTHESES_DIR, "synthesis")
        know_count = self._write_hermes_files(knowledge, HERMES_KNOWLEDGE_DIR, "knowledge")

        self._stats["exported"] = syn_count + know_count

        logger.info(
            "Exported %d entries to Hermes (%d syntheses, %d knowledge)",
            self._stats["exported"], syn_count, know_count,
        )
        return {
            "syntheses": syn_count,
            "knowledge": know_count,
            "total": self._stats["exported"],
        }

    def _get_cognition_entries(self, max_entries: int) -> List[Dict[str, Any]]:
        """Retrieve entries from asi_cognition_store."""
        try:
            # Use search with zero vector to get recent entries
            dummy = np.zeros(384, dtype=np.float32)
            results = self._store.search(
                ASI_COLLECTION, dummy, top_k=max_entries
            )
            return results
        except Exception as exc:
            logger.warning("Failed to get cognition entries: %s", exc)
            return []

    @staticmethod
    def _classify_entries(
        entries: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Classify entries into syntheses (insights) vs knowledge (reference)."""
        syntheses = []
        knowledge = []

        for entry in entries:
            meta = entry.get("metadata", {})
            domain = str(meta.get("domain", "")).lower()
            content = str(meta.get("content", "")).lower()

            # Heuristic: syntheses contain "learn", "insight", "conclusion"
            # knowledge contains "reference", "schema", "api", "definition"
            synthesis_keywords = ["learn", "insight", "conclusion", "summary",
                                  "finding", "result", "observation"]
            knowledge_keywords = ["reference", "schema", "api", "definition",
                                  "config", "setup", "guide", "manual"]

            syn_score = sum(1 for kw in synthesis_keywords if kw in content)
            know_score = sum(1 for kw in knowledge_keywords if kw in content)

            if syn_score >= know_score:
                syntheses.append(entry)
            else:
                knowledge.append(entry)

        # Balance: ensure both lists get entries
        if not syntheses and entries:
            syntheses = entries[:len(entries)//2]
            knowledge = entries[len(entries)//2:]
        elif not syntheses:
            syntheses = []
        elif not knowledge:
            knowledge = []

        return syntheses, knowledge

    def _write_hermes_files(
        self,
        entries: List[Dict[str, Any]],
        subdir: str,
        entry_type: str,
    ) -> int:
        """Write entries as .md files in Hermes subdirectory."""
        import yaml  # lazy import

        target_dir = self.hermes_root / subdir
        os.makedirs(str(target_dir), exist_ok=True)

        count = 0
        for entry in entries:
            meta = entry.get("metadata", {})
            title = meta.get("title", meta.get("name", f"untitled_{count}"))
            domain = meta.get("domain", "general")
            content = meta.get("content", meta.get("description", ""))
            tags = meta.get("tags", [])

            # Generate slug
            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50]
            if not slug:
                slug = f"{entry_type}_{count}"

            # Create .md with YAML frontmatter
            frontmatter = {
                "title": title,
                "type": entry_type,
                "domain": domain,
                "tags": tags if isinstance(tags, list) else [tags],
                "source": "AGENTIC",
                "date": meta.get("created_at", datetime.now(timezone.utc).isoformat()),
                "original_id": entry.get("id", ""),
            }

            md_content = (
                "---\n"
                f"{yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)}"
                "---\n\n"
                f"# {title}\n\n"
                f"{content}\n\n"
                f"---\n*Exported from AGENTIC via HermesBridge*\n"
            )

            filepath = target_dir / f"{slug}.md"
            # Avoid overwriting existing files
            if filepath.exists():
                filepath = target_dir / f"{slug}_{count}.md"

            try:
                filepath.write_text(md_content, encoding="utf-8")
                count += 1
            except Exception as exc:
                logger.error("Failed to write %s: %s", filepath, exc)

        return count

    # ------------------------------------------------------------------
    # Import: Hermes → AGENTIC
    # ------------------------------------------------------------------

    def sync_from_hermes(self, max_files: int = 50) -> Dict[str, Any]:
        """
        Import .md files from Hermes syntheses/ and knowledge/
        into AGENTIC asi_cognition_store.

        Returns dict with import stats.
        """
        if not self.hermes_root.exists():
            return {"error": "Hermes root not found"}

        imported = 0
        errors = 0

        # Read .md files from syntheses/ and knowledge/
        for subdir in (HERMES_SYNTHESES_DIR, HERMES_KNOWLEDGE_DIR):
            source_dir = self.hermes_root / subdir
            if not source_dir.exists():
                continue

            md_files = sorted(source_dir.glob("*.md"))[:max_files]

            for md_file in md_files:
                try:
                    entry = self._parse_hermes_md(md_file)
                    if entry:
                        self._store_cognition_entry(entry)
                        imported += 1
                except Exception as exc:
                    logger.error("Failed to import %s: %s", md_file, exc)
                    errors += 1

        self._stats["imported"] = imported
        self._stats["errors"] = errors

        logger.info(
            "Imported %d entries from Hermes (%d errors)",
            imported, errors,
        )
        return {"imported": imported, "errors": errors}

    @staticmethod
    def _parse_hermes_md(filepath: Path) -> Optional[Dict[str, Any]]:
        """Parse a Hermes .md file with YAML frontmatter."""
        import yaml  # lazy import

        content = filepath.read_text(encoding="utf-8")

        # Extract YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                except yaml.YAMLError:
                    frontmatter = {}
                    body = content
            else:
                frontmatter = {}
                body = content
        else:
            frontmatter = {}
            body = content

        title = frontmatter.get("title", filepath.stem)
        domain = frontmatter.get("domain", "general")
        tags = frontmatter.get("tags", [])
        entry_type = frontmatter.get("type", "knowledge")

        return {
            "title": title,
            "content": body,
            "domain": domain,
            "tags": tags if isinstance(tags, list) else [tags],
            "entry_type": entry_type,
            "source_file": str(filepath),
            "source": "Hermes_Memory_Proyects",
        }

    def _store_cognition_entry(self, entry: Dict[str, Any]) -> None:
        """Store a parsed entry into asi_cognition_store."""
        vec = self._make_embedding(entry.get("title", "") + " " + entry.get("content", ""))

        metadata = {
            "title": entry.get("title", ""),
            "content": entry.get("content", ""),
            "domain": entry.get("domain", "general"),
            "tags": entry.get("tags", []),
            "source": entry.get("source", "Hermes_Memory_Proyects"),
            "source_file": entry.get("source_file", ""),
            "entry_type": entry.get("entry_type", "knowledge"),
            "access_count": 0,
            "last_accessed": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._store.insert(ASI_COLLECTION, vec.reshape(1, -1), [metadata])
        except Exception as exc:
            logger.warning("Failed to store cognition entry: %s", exc)

    # ------------------------------------------------------------------
    # Full sync
    # ------------------------------------------------------------------

    def sync_all(self) -> Dict[str, Any]:
        """Full bidirectional sync: export then import."""
        exported = self.sync_to_hermes()
        imported = self.sync_from_hermes()

        return {
            "exported": exported,
            "imported": imported,
            "stats": dict(self._stats),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return bridge statistics."""
        return dict(self._stats)

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------

    @staticmethod
    def _make_embedding(text: str) -> np.ndarray:
        """Deterministic fallback embedding (no ML model required)."""
        dim = 384
        vec = np.zeros(dim, dtype=np.float32)
        for i, ch in enumerate(text.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec
