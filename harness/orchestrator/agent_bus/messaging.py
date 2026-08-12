"""AgentBus messaging — mixin con envio de mensajes (sync + batch + async).

Extraccion mecanica de los metodos de envio de la clase ``AgentBus`` del
modulo original ``harness/orchestrator/agent_bus.py`` (sin cambios de
logica ni firmas).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np

from .constants import _COLLECTION, _VALID_MESSAGE_TYPES, _VALID_STATUSES
from .exceptions import AgentBusError

logger = logging.getLogger(__name__)


class _MessagingMixin:
    """Mixin con los metodos publicos de envio de mensajes."""

    def post_message_batch(self, messages: list[dict[str, Any]]) -> list[str]:
        """
        Publica MULTIPLES mensajes en UNA SOLA llamada batch a LanceDB.

        Cada dict en ``messages`` debe tener las mismas keys que
        ``post_message()`` acepta como kwargs:
            channel, from_agent, to_agent, message, message_type,
            task_id, iteration, attachments, thread_id.

        Returns:
            Lista de IDs de los mensajes creados (en el mismo orden).

        Raises:
            InvalidMessageError: Si algun mensaje no es valido.
        """
        if not messages:
            return []

        vectors_list: list[np.ndarray] = []
        metadata_list: list[dict[str, Any]] = []
        msg_ids: list[str] = []

        for msg_data in messages:
            channel = msg_data.get("channel", "")
            from_agent = msg_data.get("from_agent", "")
            to_agent = msg_data.get("to_agent", "")
            message = msg_data.get("message", "")
            message_type = msg_data.get("message_type", "notification")

            self._validate_message_params(channel, from_agent, to_agent, message, message_type)

            msg_id = str(uuid.uuid4())
            msg_ids.append(msg_id)

            from_agent = self._normalize_agent(from_agent)
            to_agent = self._normalize_agent(to_agent)

            metadata = self._build_message_payload(
                channel=channel,
                from_agent=from_agent,
                to_agent=to_agent,
                message=message,
                message_type=message_type,
                task_id=msg_data.get("task_id"),
                iteration=msg_data.get("iteration", 0),
                attachments=msg_data.get("attachments"),
                thread_id=msg_data.get("thread_id"),
                msg_id=msg_id,
            )

            text_for_embedding = f"{channel} {from_agent} {to_agent} {message}"
            vectors_list.append(self._embedding_fn(text_for_embedding))
            metadata_list.append(metadata)

        if not vectors_list:
            return []

        vectors = np.array(vectors_list)
        try:
            self.store.insert(_COLLECTION, vectors, metadata_list)
            logger.info("Batch: %d mensajes publicados en %s", len(msg_ids), _COLLECTION)
        except Exception as exc:
            raise AgentBusError(
                f"Error al insertar batch de {len(msg_ids)} mensajes en {_COLLECTION}: {exc}"
            ) from exc

        return msg_ids

    def post_message(
        self,
        channel: str,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str = "notification",
        task_id: str | None = None,
        iteration: int = 0,
        attachments: list[str] | None = None,
        thread_id: str | None = None,
    ) -> str:
        """Publica un mensaje en un canal del bus de agentes.

        Args:
            channel: Nombre del canal (ej. ``"#feature-documentacion"``).
            from_agent: Agente que envia el mensaje (ej. ``"@software-engineer"``).
            to_agent: Agente destinatario (ej. ``"@quality-gate"``).
            message: Contenido del mensaje en texto plano.
            message_type: Tipo de mensaje (ver constantes de clase).
            task_id: ID de la tarea relacionada (opcional).
            iteration: Numero de intento (para circuit breaker).
            attachments: Lista de rutas a archivos adjuntos (opcional).
            thread_id: ID del hilo de conversacion. Si no se provee, se genera
                       uno nuevo (mensaje raiz del hilo).

        Returns:
            ID del mensaje creado.

        Raises:
            InvalidMessageError: Si los parametros no son validos.
            AssertionError: Si los parametros no pasan las validaciones refinement.
        """
        # Refinement type validations (fail-fast con assert)
        assert len(channel) > 0, "channel must not be empty"
        assert len(from_agent) > 0, "from_agent must not be empty"
        assert len(to_agent) > 0, "to_agent must not be empty"
        assert len(message) > 0, "message must not be empty"
        assert message_type in _VALID_MESSAGE_TYPES, (
            f"invalid message_type: {message_type!r}"
        )
        assert iteration >= 0, f"iteration must be >= 0: {iteration}"

        self._validate_message_params(channel, from_agent, to_agent, message, message_type)

        msg_id = str(uuid.uuid4())

        from_agent = self._normalize_agent(from_agent)
        to_agent = self._normalize_agent(to_agent)

        metadata = self._build_message_payload(
            channel=channel,
            from_agent=from_agent,
            to_agent=to_agent,
            message=message,
            message_type=message_type,
            task_id=task_id,
            iteration=iteration,
            attachments=attachments,
            thread_id=thread_id,
            msg_id=msg_id,
        )

        text_for_embedding = f"{channel} {from_agent} {to_agent} {message}"
        vector = self._embedding_fn(text_for_embedding).reshape(1, -1)

        try:
            self.store.insert(_COLLECTION, vector, [metadata])
            logger.info(
                "Mensaje %s publicado en %s: %s -> %s [%s]",
                msg_id[:8], channel, from_agent, to_agent, message_type,
            )
        except Exception as exc:
            raise AgentBusError(
                f"Error al insertar mensaje en {_COLLECTION}: {exc}"
            ) from exc

        return msg_id

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def post_message_async(
        self, channel: str, from_agent: str, to_agent: str,
        message: str, message_type: str = "notification",
        task_id: str | None = None,
    ) -> str:
        """Version async de post_message."""
        import asyncio
        return await asyncio.to_thread(
            self.post_message,
            channel, from_agent, to_agent, message,
            message_type, task_id=task_id,
        )

    async def poll_channel_async(
        self, channel: str, agent_name: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Version async de poll_channel."""
        import asyncio
        return await asyncio.to_thread(
            self.poll_channel, channel, agent_name, limit=limit
        )

    def update_message_status(self, message_id: str, status: str) -> bool:
        """Actualiza el estado de un mensaje.

        Reemplaza mark_delivered() y mark_acknowledged() que eran
        identicos excepto por el string 'delivered'/'acknowledged'.

        Args:
            message_id: ID del mensaje a actualizar.
            status: Nuevo estado ('delivered', 'acknowledged', etc.).

        Returns:
            True si se actualizo correctamente.
        """
        if status not in _VALID_STATUSES:
            logger.warning("Estado invalido: %s. Validos: %s", status, _VALID_STATUSES)
            return False
        try:
            count = self.store.update_records(
                _COLLECTION,
                filters={"id": message_id},
                updates={"status": status},
            )
            if count > 0:
                logger.info("Mensaje %s marcado como %s", message_id[:8], status)
                return True
            logger.warning("Mensaje %s no encontrado para %s", message_id[:8], status)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al actualizar estado %s para %s: %s", status, message_id[:8], exc)
            return False

    def mark_delivered(self, message_id: str) -> bool:
        """Marca un mensaje como entregado. Delega en update_message_status()."""
        return self.update_message_status(message_id, "delivered")

    def mark_acknowledged(self, message_id: str) -> bool:
        """Marca un mensaje como confirmado. Delega en update_message_status()."""
        return self.update_message_status(message_id, "acknowledged")

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def count_iterations(self, task_id: str) -> int:
        """Cuenta el numero de mensajes de error para una tarea."""
        results = self._search_messages(
            filters={"task_id": task_id, "message_type": "error"},
            top_k=1000,
        )
        return len(results)

    def check_circuit_breaker(
        self,
        task_id: str,
        max_iterations: int = 5,
    ) -> bool:
        """Verifica si el circuit breaker se ha disparado para una tarea."""
        count = self.count_iterations(task_id)
        is_open = count >= max_iterations
        if is_open:
            logger.warning(
                "CIRCUIT BREAKER ABIERTO para task_id=%s: %d errores (max=%d)",
                task_id, count, max_iterations,
            )
        return is_open

    def escalate(
        self,
        task_id: str,
        from_agent: str = "@sandbox",
        message: str = "",
        channel: str = "#escalations",
    ) -> str:
        """Envia un mensaje de escalacion a un canal humano.

        Args:
            task_id: ID de la tarea que se escala.
            from_agent: Agente que origina la escalacion.
            message: Mensaje descriptivo de la escalacion.
            channel: Canal de escalacion (defecto: ``#escalations``).

        Returns:
            ID del mensaje de escalacion creado.
        """
        escalation_msg = (
            f"ðŸš¨ ESCALACION - Task: {task_id}\n"
            f"El circuit breaker se ha disparado tras multiples intentos fallidos.\n"
            f"{message}\n"
            f"Se requiere intervencion humana."
        )
        return self.post_message(
            channel=channel,
            from_agent=from_agent,
            to_agent="@human",
            message=escalation_msg,
            message_type="escalation",
            task_id=task_id,
        )
