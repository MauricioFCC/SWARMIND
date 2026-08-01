#!/usr/bin/env python3
"""
dreaming_consolidate.py — CLI para Dreaming-lite (ADR-0034, Idea 3).

Consolida sesiones de memoria en un store consolidado (dedup + stale removal
+ compactación), fuera del path de latencia.

Uso:
    python harness/scripts/dreaming_consolidate.py <source> [--dest <dir>]
    python harness/scripts/dreaming_consolidate.py --demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(1, str(PROJECT_ROOT))

from harness.memory_rag.dreaming import DreamingConsolidator  # noqa: E402


def _demo() -> None:
    """Ejecuta una demostración con datos sintéticos (0 archivos reales)."""
    entries = [
        {
            "key": "api_auth",
            "content": "la API usa autenticacion jwt para usuarios del sistema",
            "reference_count": 3,
            "age_days": 5,
            "updated_at": "2026-07-30T00:00:00Z",
        },
        {
            "key": "api_auth_dup",
            "content": "la API usa autenticacion jwt para usuarios del sistema",
            "reference_count": 1,
            "age_days": 5,
            "updated_at": "2026-07-29T00:00:00Z",
        },
        {
            "key": "stale_note",
            "content": "nota antigua sin referencias que debe desaparecer",
            "reference_count": 0,
            "age_days": 400,
            "updated_at": "2025-01-01T00:00:00Z",
        },
    ]
    d = DreamingConsolidator(similarity_threshold=0.7)
    result = d.consolidate(entries)
    print("DEMO - Entradas origen:", result.source_entries)
    print("DEMO - Eliminadas:", result.removed)
    print("DEMO - Compactadas:", result.compacted)
    print("DEMO - Resultado:")
    print(json.dumps(result.entries, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidacion de memoria (Dreaming-lite, ADR-0034)",
    )
    parser.add_argument("source", nargs="?", help="Directorio con sesiones *.json")
    parser.add_argument("--dest", help="Directorio destino del store consolidado")
    parser.add_argument(
        "--demo", action="store_true", help="Ejecutar demo con datos sinteticos"
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.85,
        help="Umbral de Jaccard para dedup (default: 0.85)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=90,
        help="Edad maxima sin referencias (default: 90)",
    )
    args = parser.parse_args()

    if args.demo or args.source is None:
        _demo()
        return

    source = Path(args.source)
    if not source.is_dir():
        print(f"ERROR: directorio source no existe: {source}", file=sys.stderr)
        sys.exit(1)

    d = DreamingConsolidator(
        similarity_threshold=args.similarity,
        max_age_days=args.max_age_days,
    )
    result = d.consolidate_dir(source, args.dest)
    dest = Path(args.dest) if args.dest else source / "consolidated"
    print(f"Origen: {source}")
    print(f"Entradas: {result.source_entries}")
    print(f"Eliminadas: {result.removed}")
    print(f"Compactadas: {result.compacted}")
    print(f"Consolidadas: {len(result.entries)}")
    print(f"Escritas en: {dest}")


if __name__ == "__main__":
    main()
