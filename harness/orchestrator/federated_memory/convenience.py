"""Federated Memory convenience — descubrimiento y sync entre proyectos.

Extraccion mecanica del modulo original
``harness/orchestrator/federated_memory.py`` (sin cambios de logica
ni firmas): discover_federated_projects y sync_all_projects.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .core import FederatedMemoryStore

logger = logging.getLogger("harness.orchestrator.federated_memory")


# ---------------------------------------------------------------------------
# Convenience: auto-discover and sync across projects
# ---------------------------------------------------------------------------

def discover_federated_projects(
    base_dir: str | None = None,
) -> list[str]:
    """
    Descubre proyectos federados escaneando directorios.

    Busca archivos knowledge_*.json en el directorio federado
    y devuelve los nombres de proyectos encontrados.

    Args:
        base_dir: Directorio base (default: workspace root).

    Returns:
        Lista de nombres de proyectos federados.
    """
    if not base_dir:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    federated_dir = Path(base_dir) / ".opencode" / "federated"
    if not federated_dir.exists():
        return []

    projects = []
    for fpath in federated_dir.glob("knowledge_*.json"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "project" in data:
                projects.append(data["project"])
        except (json.JSONDecodeError, KeyError):
            continue

    return projects


def sync_all_projects(base_dir: str | None = None) -> dict[str, int]:
    """
    Sincroniza todos los proyectos federados descubiertos.

    Returns:
        Dict: {project_name: records_imported}
    """
    projects = discover_federated_projects(base_dir)
    results = {}
    for project in projects:
        try:
            store = FederatedMemoryStore(project_name=project)
            imported = store.sync()
            results[project] = imported
        except Exception as e:  # noqa: BLE001
            logger.warning("Error syncing project %s: %s", project, e)
            results[project] = -1
    return results
