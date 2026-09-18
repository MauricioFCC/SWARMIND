"""tool_pruner.py — Poda de herramientas por tarea (Search 9-13, ADR-0081).

WHAT: Genera allowed_tools estricto (maximo MAX_TOOLS) segun el tipo de
tarea: solo las herramientas necesarias entran al prompt del agente.
WHY: Frontera 2026 — eliminar el 80% de herramientas sube exito 80->100%,
tokens a la mitad y latencia 724s->141s (menos distraccion = mas foco).
WHERE: `task_planner` antes del `parallel_executor`; el executor solo
inyecta las permitidas.

Uso:
    pruned = prune_tools("implementa el endpoint", ["read","edit","bash","web"])
    # pruned.allowed == ("read", "edit", "bash")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.tool_pruner")

#: Maximo de herramientas por tarea (3-4, frontera).
MAX_TOOLS = 4

#: Keywords por categoria de herramienta (ES/EN, sin fragmentos ambiguos).
_TOOL_KEYWORDS: dict[str, frozenset[str]] = {
    "read": frozenset({"lee", "read", "archivo", "file", "muestra", "show"}),
    "edit": frozenset({"implementa", "implement", "edita", "edit", "crea", "create", "refactor", "fix"}),
    "bash": frozenset({"ejecuta", "run", "test", "pytest", "compila", "build", "instala"}),
    "grep": frozenset({"busca", "search", "grep", "encuentra", "find", "donde"}),
    "web": frozenset({"investiga", "research", "paper", "docs", "url", "web"}),
    "db": frozenset({"base de datos", "database", "sql", "migration", "query"}),
}


@dataclass(frozen=True)
class PrunedTools:
    """Resultado de la poda de herramientas.

    Attributes:
        allowed: Herramientas permitidas (<= MAX_TOOLS, orden de relevancia).
        pruned_count: Herramientas eliminadas del prompt.
    """

    allowed: tuple[str, ...]
    pruned_count: int


class ToolPruner:
    """Podador de herramientas por relevancia a la tarea."""

    def prune(self, task: str, available: list[str]) -> PrunedTools:
        """Poda las herramientas disponibles a las relevantes (max MAX_TOOLS).

        Args:
            task: Descripcion de la tarea (no vacia).
            available: Herramientas candidatas (orden de preferencia base).

        Returns:
            PrunedTools con allowed (<= MAX_TOOLS) y conteo podado.

        Raises:
            ValueError: Si la tarea esta vacia (WHAT+WHY+WHERE).
        """
        return prune_tools(task, available)


def prune_tools(task: str, available: list[str]) -> PrunedTools:
    """Poda funcional: score por keywords, top-MAX_TOOLS.

    Args:
        task: Descripcion de la tarea (no vacia).
        available: Herramientas candidatas.

    Returns:
        PrunedTools con las mas relevantes primero.

    Raises:
        ValueError: Si la tarea esta vacia.
    """
    if not task.strip():
        raise ValueError(
            "WHAT: tarea vacia. "
            "WHY: sin tarea no hay relevancia que puntuar. "
            "WHERE: prune_tools"
        )
    lowered = task.lower()
    scored: list[tuple[int, int, str]] = []
    for order, tool in enumerate(available):
        keywords = _TOOL_KEYWORDS.get(tool, frozenset())
        hits = sum(1 for kw in keywords if kw in lowered)
        scored.append((-hits, order, tool))
    scored.sort()
    allowed = tuple(tool for _, _, tool in scored[:MAX_TOOLS])
    pruned = max(0, len(available) - len(allowed))
    logger.debug("tool_pruner: %d -> %d tools (%s)", len(available), len(allowed), allowed)
    return PrunedTools(allowed=allowed, pruned_count=pruned)
