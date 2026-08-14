"""Constantes del paquete ``lance_vector_store``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
Sin cambios de logica: los valores y nombres son identicos al original.
"""
from __future__ import annotations

from pathlib import Path

LANCEDB_ROOT = str(
    Path(__file__).resolve().parent.parent.parent / "db" / "lancedb"
)

# Collection name constants for external consumption
COLLECTION_PROCEDURAL_SKILLS = "procedural_skills"
COLLECTION_PROMPT_EVOLUTION_LOG = "prompt_evolution_log"
COLLECTION_SCHEDULER_LOG = "scheduler_log"
