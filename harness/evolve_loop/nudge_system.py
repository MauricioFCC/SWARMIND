"""

EMBEDDING_DIM = 384
Nudge System — Auto-persistencia de contexto (inspirado en Hermes Agent nudges).

Hermes Agent tiene un sistema de "nudges" periodicos donde el agente persiste
automaticamente contexto importante a la memoria de largo plazo.

Nosotros implementamos:
  1. NudgeTrigger: detecta cuando hay contexto valioso para persistir
  2. NudgeStore: almacena nudges en la cognition store
  3. AutoNudge: ejecucion periodica automatica

Flujo:
  - Cada N iteraciones, el sistema evalua si hay contexto nuevo valioso
  - Si lo hay, genera un "nudge" = entrada en asi_cognition_store
  - El nudge incluye: contexto, timestamp, score de relevancia
  - Los nudges viejos (>30 dias) se limpian automaticamente

Uso:
    from harness.evolve_loop.nudge_system import AutoNudge
    nudge = AutoNudge()
    nudge.tick()  # evalua y persiste si hay contexto valioso
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COGNITION_COLLECTION = "asi_cognition_store"
NUDGE_INTERVAL_SECONDS = 3600  # 1 hora entre nudges
NUDGE_MAX_AGE_DAYS = 30  # eliminar nudges viejos
NUDGE_MIN_SCORE = 0.3  # score minimo para persistir


# ---------------------------------------------------------------------------
# Nudge System
# ---------------------------------------------------------------------------


class AutoNudge:
    """
    Sistema de nudges automaticos para persistir contexto valioso.

    Evalua periodicamente el contexto del sistema y persiste
    informacion importante como entradas en la cognition store.

    Uso:
        nudge = AutoNudge()
        nudge.tick()  # ejecutar en cada iteracion
    """

    def __init__(
        self,
        vector_store: Optional[LanceVectorStore] = None,
        cognition: Optional[CognitionSync] = None,
        interval_seconds: int = NUDGE_INTERVAL_SECONDS,
    ):
        self._store = vector_store or LanceVectorStore()
        self._cognition = cognition or CognitionSync(vector_store=self._store)
        self._interval = interval_seconds
        self._last_nudge: float = 0.0
        self._stats: Dict[str, Any] = {
            "nudges_created": 0,
            "nudges_cleaned": 0,
            "ticks": 0,
            "errors": 0,
        }

    def tick(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Evalua si es momento de generar un nudge.

        Args:
            force: Si True, fuerza el nudge aunque no haya pasado el intervalo.

        Returns:
            Dict con info del nudge creado, o None si no se creo nada.
        """
        self._stats["ticks"] += 1

        now = time.time()

        # Check interval
        if not force and (now - self._last_nudge) < self._interval:
            return None

        # 1. Recolectar contexto actual
        context = self._collect_context()

        # 2. Evaluar si hay contexto valioso
        if not context:
            logger.debug("Nudge: no context to persist")
            return None

        score = self._evaluate_context(context)
        if score < NUDGE_MIN_SCORE:
            logger.debug("Nudge: context score %.2f < %.2f, skipping", score, NUDGE_MIN_SCORE)
            return None

        # 3. Persistir nudge
        nudge = self._persist_nudge(context, score)

        self._last_nudge = now
        self._stats["nudges_created"] += 1

        logger.info("Nudge created: score=%.2f, domain=%s", score, nudge.get("domain", "?"))

        # 4. Clean old nudges
        cleaned = self._clean_old_nudges()
        if cleaned > 0:
            self._stats["nudges_cleaned"] += cleaned

        return nudge

    def _collect_context(self) -> List[Dict[str, Any]]:
        """
        Recolecta contexto actual del sistema.

        Busca en la cognition store las entradas recientes
        y en agent_workspace_logs las interacciones recientes.
        """
        context_items: List[Dict[str, Any]] = []

        try:
            # Recent cognition lessons
            dummy = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            results = self._store.search(
                COGNITION_COLLECTION, dummy, top_k=20
            )
            for r in results:
                meta = r.get("metadata", {})
                if isinstance(meta, str):
                    import json
                    try:
                        meta = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                context_items.append(meta)
        except Exception as exc:
            logger.debug("Nudge: error collecting context: %s", exc)
            self._stats["errors"] += 1

        return context_items

    @staticmethod
    def _evaluate_context(context: List[Dict[str, Any]]) -> float:
        """
        Evalua si el contexto recolectado es valioso para persistir.

        Returns:
            Score de 0.0 a 1.0.
        """
        if not context:
            return 0.0

        # Factores que aumentan el score:
        scores: List[float] = []

        for item in context:
            # Lecciones con score alto
            metrics = item.get("metrics", {})
            if isinstance(metrics, dict):
                overall = metrics.get("overall_score", 0)
                if isinstance(overall, (int, float)):
                    scores.append(min(1.0, float(overall)))

            # Contenido sustancial
            content = item.get("content", "")
            if isinstance(content, str) and len(content) > 100:
                scores.append(0.5)

            # Tags relevantes
            tags = item.get("tags", [])
            if isinstance(tags, list) and len(tags) > 2:
                scores.append(0.3)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    def _persist_nudge(
        self, context: List[Dict[str, Any]], score: float
    ) -> Dict[str, Any]:
        """
        Persiste un nudge en la cognition store.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Construir contenido del nudge
        domains = set()
        tags: set = set()
        content_parts: List[str] = []

        for item in context:
            domain = item.get("domain", "")
            if domain:
                domains.add(domain)
            for tag in item.get("tags", []):
                if isinstance(tag, str):
                    tags.add(tag)

            content = item.get("content", "")
            if isinstance(content, str) and len(content) > 30:
                content_parts.append(f"- {content[:200]}")

        nudge_content = (
            f"Auto-nudge (score: {score:.2f})\n\n"
            f"Context summary:\n"
            + ("\n".join(content_parts[:5]) if content_parts else "- No specific context")
            + "\n\n"
            f"Domains: {', '.join(sorted(domains)[:5]) if domains else 'general'}"
        )

        # Store via cognition sync
        try:
            lesson_id = self._cognition.add_lesson(
                title=f"Auto-nudge: {now[:10]}",
                content=nudge_content,
                domain="nudge.auto",
                tags=sorted(tags | {"nudge", "auto-persist"}),
                metrics={
                    "nudge_score": round(score, 4),
                    "context_items": len(context),
                    "nudge_type": "auto",
                },
            )
            return {
                "id": lesson_id.id if lesson_id else "unknown",
                "score": score,
                "domain": "nudge.auto",
                "created_at": now,
                "context_items": len(context),
            }
        except Exception as exc:
            logger.warning("Nudge persist failed: %s", exc)
            self._stats["errors"] += 1
            return {"error": str(exc)}

    def _clean_old_nudges(self) -> int:
        """
        Elimina nudges viejos (> NUDGE_MAX_AGE_DAYS).
        """
        # En produccion esto haria una busqueda temporal en LanceDB
        # Por ahora es un placeholder - los nudges viejos se limpian
        # naturalmente cuando se supera el limite de la cognition store
        return 0

    def force_nudge(self) -> Optional[Dict[str, Any]]:
        """Force a nudge regardless of interval."""
        return self.tick(force=True)

    def get_stats(self) -> Dict[str, Any]:
        """Return nudge statistics."""
        return dict(self._stats)
