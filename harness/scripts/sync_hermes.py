#!/usr/bin/env python3
"""
sync_hermes.py — CLI para Hermes Bridge sync (propagacion de conocimiento).

Propaga conocimiento entre Swarmind y Hermes_Memory_Proyects:

    Swarmind .opencode/federated/*.json  <->  Hermes knowledge/Swarmind_bridge/
    Swarmind .opencode/skills/*          ->  Hermes skills/Swarmind_bridge/

Uso:
    python harness/scripts/sync_hermes.py              # Sync bidireccional
    python harness/scripts/sync_hermes.py --to-hermes   # Solo export
    python harness/scripts/sync_hermes.py --from-hermes # Solo import
    python harness/scripts/sync_hermes.py --dry-run     # Mostrar que haria
    python harness/scripts/sync_hermes.py --stats       # Ver estadisticas
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(1, str(PROJECT_ROOT))

# Script standalone: sys.path debe configurarse antes de importar el paquete.
from harness.memory_rag.hermes_bridge import HermesBridge  # noqa: E402

# Hermes root por defecto: implementacion canonica (Documents\Hermes_Memory_Proyects).
DEFAULT_HERMES_ROOT = Path.home() / "Documents" / "Hermes_Memory_Proyects"

# Directorio de memoria federada de Swarmind.
SWARMIND_FEDERATED = PROJECT_ROOT / ".opencode" / "federated"
SWARMIND_SKILLS = PROJECT_ROOT / ".opencode" / "skills"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _load_federated_records() -> list[dict]:
    """Carga los registros de la memoria federada de Swarmind.

    Returns:
        Lista de registros con clave/valor leidos de los JSON federated.
    """
    records: list[dict] = []
    if not SWARMIND_FEDERATED.exists():
        return records
    for fpath in sorted(SWARMIND_FEDERATED.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            items = data.get("records", [data] if isinstance(data, dict) else [])
            for record in items:
                if isinstance(record, dict) and record:
                    records.append(record)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "WHAT: no se pudo leer %s. WHY: %s. "
                "WHERE: _load_federated_records() en sync_hermes.py.",
                fpath.name,
                exc,
            )
    logger.info("Federated records cargados: %d", len(records))
    return records


def _write_hermes_knowledge_to_federated(bridge: HermesBridge) -> int:
    """Importa el conocimiento de Hermes hacia la memoria federada de Swarmind.

    Args:
        bridge: HermesBridge con hermes_path resuelto.

    Returns:
        Cantidad de registros importados.
    """
    if not SWARMIND_FEDERATED.exists():
        SWARMIND_FEDERATED.mkdir(parents=True, exist_ok=True)
    records = bridge.sync_from_hermes(pattern="*.json")
    count = 0
    for record in records:
        key = record.get("key", record.get("id", f"hermes_{count}"))
        safe_name = key.replace(":", "_").replace("/", "_").replace(" ", "_")
        out_path = SWARMIND_FEDERATED / f"hermes_{safe_name}.json"
        out_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        count += 1
    logger.info("Hermes -> Swarmind: %d registros importados", count)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Swarmind cognition store with shared_memory",
    )
    parser.add_argument(
        "--to-hermes",
        action="store_true",
        help="Export Swarmind -> Hermes (federated + skills)",
    )
    parser.add_argument(
        "--from-hermes",
        action="store_true",
        help="Import Hermes -> Swarmind (knowledge)",
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

    bridge = HermesBridge(hermes_path=str(hermes_root), auto_import=False)

    if args.stats:
        stats = bridge.get_status()
        print("Bridge status:", json.dumps(stats, indent=2, ensure_ascii=False))
        return

    if args.dry_run:
        logger.info("DRY RUN - Hermes root: %s", hermes_root)
        logger.info("Swarmind federated: %s", SWARMIND_FEDERATED)
        logger.info("Swarmind skills: %s", SWARMIND_SKILLS)
        return

    if not bridge.available:
        logger.error("Bridge not available for %s", hermes_root)
        sys.exit(1)

    if args.to_hermes:
        records = _load_federated_records()
        synced = bridge.sync_to_hermes(records)
        skills = bridge.sync_skills_to_hermes(str(SWARMIND_SKILLS))
        logger.info("Export complete: %d registros, %d skills", synced, skills)

    if args.from_hermes:
        imported = _write_hermes_knowledge_to_federated(bridge)
        logger.info("Import complete: %d registros", imported)

    if not args.to_hermes and not args.from_hermes:
        # Sync bidireccional completo.
        records = _load_federated_records()
        synced = bridge.sync_to_hermes(records)
        skills = bridge.sync_skills_to_hermes(str(SWARMIND_SKILLS))
        imported = _write_hermes_knowledge_to_federated(bridge)
        logger.info(
            "Bidirectional sync complete: %d->Hermes, %d skills, %d<-Hermes",
            synced,
            skills,
            imported,
        )


if __name__ == "__main__":
    main()
