"""trace_viewer.py — Export + replay determinista de trazas (ADR-0079, OMA).

WHAT: Exporta decisiones de agentes a `trace.jsonl` (1 dict por linea) y
las re-ejecuta con un player inyectado, sin LLM: replay offline para
auditoria y debugging determinista.
WHY: Open Multi-Agent (6.8k estrellas): el run debe ser dato inspeccionable
y re-ejecutable; el replay sin modelo aisla regresiones de logica vs
varianza del modelo.
WHERE: Tras `behavioral_tracer` / sesiones del orquestador; `replay` en CI
para verificar que una traza dorada sigue pasando.

Uso:
    path = export_trace(decisions, Path("runs/trace.jsonl"))
    results = replay_trace(path, player_fn)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("harness.orchestrator.trace_viewer")


def export_trace(decisions: list[dict], path: Path) -> Path:
    """Exporta decisiones a trace.jsonl (1 JSON por linea).

    Args:
        decisions: Lista de dicts serializables (agent/action/task_id...).
        path: Destino (se crea su directorio padre si falta).

    Returns:
        La misma ruta (para encadenar con replay).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False) + "\n")
    logger.info("trace_viewer: %d decisiones -> %s", len(decisions), path)
    return path


def replay_trace(
    path: Path, player: Callable[[dict], str]
) -> list[str]:
    """Re-ejecuta una traza con el player inyectado (determinista, sin LLM).

    Args:
        path: trace.jsonl a re-ejecutar.
        player: Callable (decision) -> resultado (puro, sin modelo).

    Returns:
        Resultados en el mismo orden de la traza.

    Raises:
        FileNotFoundError: Si la traza no existe (WHAT+WHY+WHERE).
        ValueError: Si una linea no es JSON valido.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"WHAT: traza no encontrada: {path}. "
            "WHY: el replay necesita una traza exportada. "
            "WHERE: replay_trace"
        )
    results: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            decision = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"WHAT: linea {lineno} no es JSON valido en {path}. "
                f"WHY: la traza debe ser 1 dict por linea ({exc}). "
                "WHERE: replay_trace"
            ) from exc
        results.append(player(decision))
    logger.info("trace_viewer: replay de %d decisiones desde %s", len(results), path)
    return results
