"""Feedback scorer — escribe efectividad de skill/agente en colecciones de valor.

WHAT: Puntua la efectividad de una skill y de un agente tras un run, en las
colecciones LanceDB ``skill_effectiveness`` y ``agent_performance``.
WHY: esas colecciones de valor estaban cableadas en produccion pero vacias
(0 escrituras): el harness acumulaba cache de retrieval (99.7% del disco) y
no experiencia que mejorar las decisiones. Cerrar ese ciclo convierte
"memoria" en "mejores decisiones" (Item 1, docs/specs/memory-optimality.md).
WHERE: ``AgentDispatcher.record_skill_outcome`` (hook post-run existente).

Contratos 1-6. DI: recibe el vector store inyectado (backend ``memory`` en
tests, sin ``lancedb``). Degradacion suave: nunca lanza hacia el caller.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np

from harness.common import fallback_embedding

logger = logging.getLogger("harness.evolve_loop.feedback_scorer")

#: Colecciones de valor que alimentan el enrutamiento/decision (constantes
#: propias para no acoplarnos a constants.py de lance_vector_store).
COLLECTION_AGENT_PERFORMANCE = "agent_performance"
COLLECTION_SKILL_EFFECTIVENESS = "skill_effectiveness"

#: Dimension del embedding de fila: son registros tabulares, no texto; una
#: dim reducida basta para que ``insert`` (que exige un vector) sea barato.
#: Publica para que los consumidores (tests, ``run_report``) usen la misma
#: dimension en sus vectores de consulta (evita mismatch de matmul).
ROW_EMBED_DIM = 128


def _row_embedding(text: str) -> np.ndarray:
    """Embedding determinista 2D para insertar una fila.

    Args:
        text: Texto identificador de la fila (clave de similitud).

    Returns:
        Vector numpy de forma ``(1, ROW_EMBED_DIM)``.
    """
    return fallback_embedding(text, dim=ROW_EMBED_DIM).reshape(1, -1)


def _ensure_collection(store: Any, name: str) -> bool:
    """Crea la coleccion si no existe (idempotente).

    Args:
        store: Vector store inyectado.
        name: Nombre de la coleccion.

    Returns:
        True si la coleccion quedo disponible.
    """
    try:
        if name not in store.list_collections():
            store.create_collection(name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "feedback_scorer: WHAT: no se pudo crear coleccion '%s': %s. "
            "WHY: store no disponible. WHERE: _ensure_collection", name, exc,
        )
        return False


def _write_row(store: Any, collection: str, metadata: dict[str, Any]) -> bool:
    """Inserta una fila de feedback en una coleccion de valor.

    Args:
        store: Vector store inyectado.
        collection: Coleccion destino.
        metadata: Metadatos de la fila (serializables).

    Returns:
        True si la fila se escribio.
    """
    if not _ensure_collection(store, collection):
        return False
    key = str(next(iter(metadata.values())))
    try:
        store.insert(collection, _row_embedding(key), [metadata])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "feedback_scorer: WHAT: no se pudo escribir en '%s': %s. "
            "WHY: fallo de IO/store. WHERE: _write_row", collection, exc,
        )
        return False


def score_outcome(
    store: Any,
    skill_name: str | None,
    *,
    success: bool,
    agent_role: str | None = None,
    metrics: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
) -> bool:
    """Puntua un outcome en las colecciones de valor (best-effort).

    Escribe en ``skill_effectiveness`` si hay ``skill_name`` y en
    ``agent_performance`` si hay ``agent_role``. Con ``store is None`` es
    no-op (devuelve ``False``). Nunca lanza hacia el caller.

    Args:
        store: Vector store inyectado (``None`` => no-op).
        skill_name: Nombre de la skill usada (``None`` => no escribe skill).
        success: True si la trayectoria fue correcta.
        agent_role: Rol del agente (``None`` => no escribe performance).
        metrics: Metricas adicionales serializadas a JSON.
        state_snapshot: Snapshot del estado restaurado para credit assignment
            (frontier: arXiv:2604.09459 — restored-state comparison).

    Returns:
        True si al menos una fila se escribio.
    """
    if store is None:
        return False
    ts = datetime.now(UTC).isoformat()
    written = False
    snap_json = json.dumps(state_snapshot or {}, ensure_ascii=False)
    if skill_name:
        written = _write_row(store, COLLECTION_SKILL_EFFECTIVENESS, {
            "skill_name": skill_name, "success": success, "ts": ts,
            "state_snapshot": snap_json,
        }) or written
    if agent_role:
        written = _write_row(store, COLLECTION_AGENT_PERFORMANCE, {
            "agent_role": agent_role, "success": success, "ts": ts,
            "metrics": json.dumps(metrics or {}, ensure_ascii=False),
            "state_snapshot": snap_json,
        }) or written
    return written


def run_report(store: Any) -> dict[str, int]:
    """Cuenta filas por coleccion de valor (alimenta el health-check).

    Args:
        store: Vector store inyectado.

    Returns:
        Dict coleccion -> numero de filas (0 si no se pudo contar).
    """
    report: dict[str, int] = {}
    vec = fallback_embedding("report", dim=ROW_EMBED_DIM)
    for coll in (COLLECTION_SKILL_EFFECTIVENESS, COLLECTION_AGENT_PERFORMANCE):
        try:
            report[coll] = len(store.search(coll, vec, top_k=10_000))
        except Exception as exc:  # noqa: BLE001
            logger.debug("feedback_scorer: no se pudo contar '%s': %s", coll, exc)
            report[coll] = 0
    return report
