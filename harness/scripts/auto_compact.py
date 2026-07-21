#!/usr/bin/env python3
"""

EMBEDDING_DIM = 384
Auto-Compact — Automatic context compaction pipeline.

Inspirado en Anthropic context engineering (Sep 2025):
Cuando el contexto se acumula, comprime automaticamente
agrupando entries similares y reemplazandolas con summaries.

Uso:
    python harness/scripts/auto_compact.py                # Compactar
    python harness/scripts/auto_compact.py --dry-run      # Preview
    python harness/scripts/auto_compact.py --watch        # Modo watch (cada 4h)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.lance_vector_store import LanceVectorStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

COGNITION_COLLECTION = "asi_cognition_store"
MAX_ENTRIES_BEFORE_COMPACT = 30


def compact_cognition_store(
    store: LanceVectorStore,
    cognition: CognitionSync,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Agrupa entries por dominio, comprime grupos grandes con summary."""
    stats = {"groups_found": 0, "entries_compressed": 0}

    dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    try:
        results = store.search(COGNITION_COLLECTION, dummy, top_k=500)
    except Exception as exc:
        logger.warning("Error searching cognition store: %s", exc)
        return stats

    if not results:
        logger.info("Cognition store empty.")
        return stats

    # Parse entries
    entries: List[Dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except Exception as _exc:
                logger.warning("auto_compact: %s", _exc)
                meta = {}
        entries.append(meta)

    # Group by domain
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        domain = entry.get("domain", "general")
        groups[domain].append(entry)

    # Compact large groups
    for domain, group in sorted(groups.items()):
        if len(group) < MAX_ENTRIES_BEFORE_COMPACT:
            continue
        if domain in ("nudge.auto",):
            continue

        stats["groups_found"] += 1

        sorted_group = sorted(
            group, key=lambda e: e.get("created_at", ""), reverse=True
        )
        keep = sorted_group[:10]
        compress = sorted_group[10:]

        if dry_run:
            logger.info(
                "  [DRY-RUN] '%s': %d entries (%d compressible)",
                domain, len(group), len(compress),
            )
            continue

        # Build summary
        tags_all: set = set()
        scores = []
        snippets = []
        for entry in compress:
            content = entry.get("content", "")
            if isinstance(content, str) and content:
                snippets.append(content[:150])
            for tag in entry.get("tags", []):
                if isinstance(tag, str):
                    tags_all.add(tag)
            metrics = entry.get("metrics", {})
            if isinstance(metrics, dict):
                s = metrics.get("overall_score", 0)
                if isinstance(s, (int, float)):
                    scores.append(s)

        avg_score = sum(scores) / len(scores) if scores else 0
        summary = (
            "[COMPACTED] %d entries from '%s'\n"
            "Score: %.2f\n"
            "Tags: %s\n"
            "---\n%s"
        ) % (
            len(compress), domain, avg_score,
            ", ".join(sorted(tags_all)[:8]),
            "\n".join(snippets[:3]),
        )

        cognition.add_lesson(
            title="[COMPACTED] %s: %d entries" % (domain, len(compress)),
            content=summary,
            domain=domain,
            tags=list(tags_all | {"compacted"}),
            metrics={
                "compacted_entries": len(compress),
                "avg_score": round(avg_score, 4),
                "original_count": len(group),
                "kept_count": len(keep),
            },
        )
        stats["entries_compressed"] += len(compress)
        logger.info(
            "  '%s': %d entries compacted -> summary created",
            domain, len(compress),
        )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Auto-Compact cognition store")
    parser.add_argument("--dry-run", action="store_true", help="Preview")
    parser.add_argument("--watch", action="store_true", help="Watch mode (4h)")
    parser.add_argument("--interval", type=int, default=4, help="Hours (default: 4)")
    args = parser.parse_args()

    store = LanceVectorStore()
    cognition = CognitionSync(vector_store=store)

    if args.watch:
        logger.info("Auto-Compact watch mode (every %dh)", args.interval)
        while True:
            stats = compact_cognition_store(store, cognition, dry_run=False)
            if stats.get("entries_compressed", 0) > 0:
                logger.info("Compacted %d entries", stats["entries_compressed"])
            time.sleep(args.interval * 3600)

    stats = compact_cognition_store(store, cognition, dry_run=args.dry_run)
    msg = "Dry-run: %d groups" % stats["groups_found"] if args.dry_run else (
        "Compacted %d entries across %d groups"
        % (stats["entries_compressed"], stats["groups_found"])
    )
    logger.info(msg)


if __name__ == "__main__":
    main()
