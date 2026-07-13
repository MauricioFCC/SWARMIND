#!/usr/bin/env python3
"""
sync_hermes.py — CLI para Hermes Bridge sync.

Uso:
    python harness/scripts/sync_hermes.py              # Bidirectional sync
    python harness/scripts/sync_hermes.py --to-hermes   # Solo export
    python harness/scripts/sync_hermes.py --from-hermes # Solo import
    python harness/scripts/sync_hermes.py --dry-run     # Mostrar que haria
    python harness/scripts/sync_hermes.py --stats       # Ver estadisticas
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from harness.hermes_bridge import DEFAULT_HERMES_ROOT, HermesBridge  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync AGENTIC cognition store with Hermes_Memory_Proyects",
    )
    parser.add_argument(
        "--to-hermes",
        action="store_true",
        help="Export AGENTIC → Hermes (syntheses + knowledge)",
    )
    parser.add_argument(
        "--from-hermes",
        action="store_true",
        help="Import Hermes → AGENTIC asi_cognition_store",
    )
    parser.add_argument(
        "--hermes-root",
        type=str,
        default=str(DEFAULT_HERMES_ROOT),
        help=f"Hermes root path (default: {DEFAULT_HERMES_ROOT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show bridge statistics",
    )

    args = parser.parse_args()

    hermes_root = Path(args.hermes_root)
    if not hermes_root.exists():
        logger.error("Hermes root not found: %s", hermes_root)
        sys.exit(1)

    bridge = HermesBridge(hermes_root=hermes_root)

    if args.stats:
        stats = bridge.get_stats()
        print("Bridge stats:", stats)
        return

    if args.dry_run:
        logger.info("DRY RUN - Hermes root: %s", hermes_root)
        logger.info("Would sync with: --to-hermes=%s --from-hermes=%s",
                     not args.from_hermes or args.to_hermes,
                     not args.to_hermes or args.from_hermes)
        return

    if args.to_hermes:
        result = bridge.sync_to_hermes()
        logger.info("Export complete: %s", result)

    if args.from_hermes:
        result = bridge.sync_from_hermes()
        logger.info("Import complete: %s", result)

    if not args.to_hermes and not args.from_hermes:
        # Full bidirectional sync
        result = bridge.sync_all()
        logger.info("Bidirectional sync complete: %s", result)


if __name__ == "__main__":
    main()
