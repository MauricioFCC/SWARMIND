"""Federated Memory store mixin — API publica de almacenamiento/consulta.

Extraccion mecanica del modulo original
``harness/orchestrator/federated_memory.py`` (sin cambios de logica
ni firmas): store_knowledge, delete_knowledge, query_knowledge,
get_knowledge, list_projects y get_stats.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .models import KnowledgeRecord, KnowledgeType

logger = logging.getLogger("harness.orchestrator.federated_memory")


class _StoreMixin:
    """Mixin con la API publica de store y query."""

    # ------------------------------------------------------------------
    # Public API - Store
    # ------------------------------------------------------------------

    def store_knowledge(
        self,
        key: str,
        value: Any,
        ktype: KnowledgeType = KnowledgeType.PATTERN,
        source_agent: str = "system",
        tags: list[str] | None = None,
        confidence: float = 1.0,
        ttl_seconds: int = 0,
    ) -> KnowledgeRecord:
        """
        Almacena un registro de conocimiento.

        Args:
            key: Clave semantica (ej. "task_planner:optimal_subtask_count").
            value: Valor serializable.
            ktype: Tipo de conocimiento.
            source_agent: Agente que genero el conocimiento.
            tags: Tags para busqueda.
            confidence: Confianza 0.0-1.0.
            ttl_seconds: TTL en segundos (0 = forever).

        Returns:
            KnowledgeRecord creado/actualizado.
        """
        record_id = f"{ktype.value}:{self._project_name}:{key}"

        with self._lock:
            existing = self._local_store.get(record_id)

            if existing:
                # Update existing
                existing.value = value
                existing.version += 1
                existing.updated_at = datetime.now(UTC).isoformat()
                existing.confidence = confidence
                existing.tags = list(set(existing.tags + (tags or [])))
                record = existing
            else:
                record = KnowledgeRecord(
                    id=record_id,
                    type=ktype,
                    source_project=self._project_name,
                    source_agent=source_agent,
                    key=key,
                    value=value,
                    tags=tags or [],
                    confidence=confidence,
                    ttl_seconds=ttl_seconds,
                )
                self._local_store[record_id] = record

        self._save_local()
        return record

    def delete_knowledge(self, key: str, ktype: KnowledgeType) -> bool:
        """Elimina un registro de conocimiento."""
        record_id = f"{ktype.value}:{self._project_name}:{key}"
        with self._lock:
            if record_id in self._local_store:
                del self._local_store[record_id]
                self._save_local()
                return True
        return False

    # ------------------------------------------------------------------
    # Public API - Query
    # ------------------------------------------------------------------

    def query_knowledge(
        self,
        key_prefix: str = "",
        ktype: KnowledgeType | None = None,
        tags: list[str] | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
        limit: int = 50,
    ) -> list[KnowledgeRecord]:
        """
        Consulta conocimiento federado.

        Args:
            key_prefix: Filtro por prefijo de key.
            ktype: Filtro por tipo de conocimiento.
            tags: Filtro por tags (AND).
            min_confidence: Confianza minima.
            include_expired: Incluir registros expirados.
            limit: Maximo de resultados.

        Returns:
            Lista de KnowledgeRecord matching.
        """
        # Force sync from disk
        self._load_local()

        results = []
        with self._lock:
            for record in self._local_store.values():
                # Filter: type
                if ktype and record.type != ktype:
                    continue

                # Filter: key prefix
                if key_prefix and not record.key.startswith(key_prefix):
                    continue

                # Filter: tags
                if tags and not all(t in record.tags for t in tags):
                    continue

                # Filter: confidence
                if record.confidence < min_confidence:
                    continue

                # Filter: expired
                if not include_expired and record.is_expired():
                    continue

                results.append(record)

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:limit]

    def get_knowledge(
        self, key: str, ktype: KnowledgeType,
    ) -> KnowledgeRecord | None:
        """Obtiene un registro especifico por key + type."""
        results = self.query_knowledge(
            key_prefix=key, ktype=ktype, include_expired=False, limit=1,
        )
        return results[0] if results else None

    def list_projects(self) -> set[str]:
        """Lista todos los proyectos que han contribuido conocimiento."""
        projects = set()
        with self._lock:
            for record in self._local_store.values():
                projects.add(record.source_project)
        return projects

    def get_stats(self) -> dict:
        """Estadisticas del store federado."""
        with self._lock:
            total = len(self._local_store)
            by_type: dict = {}
            by_project: dict = {}
            expired = 0

            for record in self._local_store.values():
                t = record.type.value if isinstance(record.type, KnowledgeType) else str(record.type)
                p = record.source_project
                by_type[t] = by_type.get(t, 0) + 1
                by_project[p] = by_project.get(p, 0) + 1
                if record.is_expired():
                    expired += 1

        return {
            "total_records": total,
            "expired_records": expired,
            "by_type": by_type,
            "by_project": by_project,
            "projects": len(by_project),
            "federated_dir": str(self._federated_dir),
        }
