"""AgentBus reading — mixin con lectura de mensajes.

Extraccion mecanica de los metodos de lectura de la clase ``AgentBus``
del modulo original ``harness/orchestrator/agent_bus.py`` (sin cambios
de logica ni firmas).
"""

from __future__ import annotations

import logging
from typing import Any

from harness.common import EMPTY_VECTOR

from .constants import _COLLECTION

logger = logging.getLogger(__name__)


class _ReadingMixin:
    """Mixin con los metodos publicos de lectura de mensajes."""

    def _search_messages(
        self,
        filters: dict[str, Any] | None = None,
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Busca mensajes en el store con filtros.

        Reemplaza 7 repeticiones del mismo patron try/except/search en:
            poll_channel, get_thread, get_channel_history,
            get_message_by_id, count_iterations, get_channel_list,
            get_tasks_with_errors
        """
        try:
            results = self.store.search(
                _COLLECTION, EMPTY_VECTOR, top_k=top_k, filters=filters or {},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error en busqueda de mensajes: %s", exc)
            return []
        return [self._deserialize_message(r) for r in results]

    def poll_channel(
        self,
        channel: str,
        agent_name: str,
        since_timestamp: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Busca mensajes no leidos para un agente en un canal.

        Args:
            channel: Nombre del canal.
            agent_name: Nombre del agente destinatario.
            since_timestamp: Solo mensajes posteriores a este timestamp ISO.
            limit: Maximo de mensajes a retornar.

        Returns:
            Lista de dicts con los datos de cada mensaje.
        """
        agent_name = self._normalize_agent(agent_name)

        # Buscar mensajes dirigidos al agente O a @all (broadcasts)
        results = self._search_messages(
            filters={"channel": channel, "to_agent": agent_name},
            top_k=limit,
        )
        # Incluir mensajes @all que no sean duplicados de los que ya recibio
        all_messages = self._search_messages(
            filters={"channel": channel, "to_agent": "@all"},
            top_k=limit,
        )
        seen_ids = {m.get("id") for m in results}
        for m in all_messages:
            if m.get("id") not in seen_ids:
                results.append(m)
                seen_ids.add(m.get("id"))

        if since_timestamp:
            results = [m for m in results if m.get("created_at", "") >= since_timestamp]

        results.sort(key=lambda m: m.get("created_at", ""))
        return results

    def get_thread(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Recupera todo el hilo de conversacion de un thread_id."""
        results = self._search_messages(
            filters={"thread_id": thread_id},
            top_k=limit,
        )
        results.sort(key=lambda m: m.get("created_at", ""))
        return results

    def get_channel_history(
        self,
        channel: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Obtiene el historial completo de un canal."""
        results = self._search_messages(
            filters={"channel": channel},
            top_k=limit,
        )
        results.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return results

    def get_message_by_id(self, message_id: str) -> dict[str, Any] | None:
        """Recupera un mensaje individual por su ID."""
        results = self._search_messages(
            filters={"id": message_id},
            top_k=1,
        )
        return results[0] if results else None

    # ------------------------------------------------------------------
    # Listados derivados
    # ------------------------------------------------------------------

    def get_channel_list(self) -> list[str]:
        """Retorna la lista de canales con actividad."""
        results = self._search_messages(top_k=5000)
        canales: set = set()
        for m in results:
            ch = m.get("channel", "")
            if ch:
                canales.add(ch)
        return sorted(canales)

    def get_tasks_with_errors(self) -> list[str]:
        """Retorna los task_id que tienen mensajes de error."""
        results = self._search_messages(
            filters={"message_type": "error"},
            top_k=5000,
        )
        tareas: set = set()
        for m in results:
            tid = m.get("task_id", "")
            if tid:
                tareas.add(tid)
        return sorted(tareas)
