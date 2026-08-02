"""
Agent Message Bus â€” "Slack para Agentes"

Implementa un bus de mensajes asincrono entre agentes usando LanceVectorStore
como backend. Cada mensaje se almacena en la coleccion ``agent_workspace_logs``
con metadatos de canal, hilo, emisor, destinatario y estado.

Tipos de mensaje:
    - request:   Solicitud de accion/informacion
    - response:  Respuesta a una solicitud
    - error:     Notificacion de fallo
    - notification: Informacion general
    - escalation:  Escalacion a humano (circuit breaker)

Estados del mensaje:
    - sent:         Enviado, no entregado
    - delivered:    Entregado al destinatario
    - acknowledged: Confirmado por el destinatario
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from harness.common import EMPTY_VECTOR, fallback_embedding
from harness.memory_rag.lance_vector_store import LanceVectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_COLLECTION = "agent_workspace_logs"
_EMBEDDING_DIM = 384

_VALID_MESSAGE_TYPES = frozenset({
    "request", "response", "error", "notification", "escalation",
})
_VALID_STATUSES = frozenset({"sent", "delivered", "acknowledged"})


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class AgentBusError(Exception):
    """Error base del AgentBus."""


class InvalidMessageError(AgentBusError):
    """El mensaje no cumple con el esquema requerido."""


# ---------------------------------------------------------------------------
# AgentBus
# ---------------------------------------------------------------------------


class AgentBus:
    """Bus de mensajes asincrono entre agentes (patron Slack).

    Proporciona canales tematicos, hilos de conversacion, menciones a agentes,
    tracking de estado de entrega y contador de iteraciones para circuit breaker.

    Uso tipico::

        bus = AgentBus()

        # Enviar mensaje
        msg_id = bus.post_message(
            channel="#feature-documentacion",
            from_agent="@software-engineer",
            to_agent="@quality-gate",
            message="Tests unitarios completados. Revisando cobertura...",
            message_type="notification",
            task_id="abc123",
        )

        # Poll de mensajes no leidos
        mensajes = bus.poll_channel("#feature-documentacion", "@quality-gate")

        # Marcar como entregado
        bus.mark_delivered(msg_id)
    """

    COLLECTION = _COLLECTION

    def __init__(
        self,
        vector_store: LanceVectorStore | None = None,
    ) -> None:
        """
        Args:
            vector_store: Instancia de LanceVectorStore. Por defecto crea una nueva.
        """
        self.store = vector_store or LanceVectorStore()
        self._embedding_fn = fallback_embedding

    # ------------------------------------------------------------------
    # Internal: shared payload builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_message_payload(
        channel: str,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str = "notification",
        task_id: str | None = None,
        iteration: int = 0,
        attachments: list[str] | None = None,
        thread_id: str | None = None,
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Construye el payload de metadata para un mensaje.

        Extraido de post_message() y post_message_batch() para eliminar
        la duplicacion del dict de metadatos (~15 lineas identicas).
        """
        return {
            "id": msg_id or str(uuid.uuid4()),
            "channel": channel,
            "thread_id": thread_id or str(uuid.uuid4()),
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message": message,
            "message_type": message_type,
            "status": "sent",
            "task_id": task_id or "",
            "iteration": iteration,
            "attachments": json.dumps(attachments or []),
            "created_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # API publica: Envio de mensajes
    # ------------------------------------------------------------------

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
    # Internal: shared search helper
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # API publica: Lectura de mensajes
    # ------------------------------------------------------------------

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
    # API publica: Actualizacion de estado
    # ------------------------------------------------------------------

    def update_message_status(self, message_id: str, status: str) -> bool:
        """
        Actualiza el estado de un mensaje.

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
    # API publica: Circuit Breaker
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

    # ------------------------------------------------------------------
    # Metodos de utilidad
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

    # ------------------------------------------------------------------
    # Metodos internos
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_message_params(
        channel: str,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str,
    ) -> None:
        """Valida los parametros de un mensaje antes de insertarlo."""
        if not channel or not channel.startswith("#"):
            raise InvalidMessageError(
                f"El canal debe empezar con '#': {channel!r}"
            )
        if not from_agent:
            raise InvalidMessageError("from_agent es requerido")
        if not to_agent:
            raise InvalidMessageError("to_agent es requerido")
        if not message or not message.strip():
            raise InvalidMessageError("El mensaje no puede estar vacio")
        if message_type not in _VALID_MESSAGE_TYPES:
            raise InvalidMessageError(
                f"Tipo de mensaje invalido: {message_type!r}. "
                f"Validos: {sorted(_VALID_MESSAGE_TYPES)}"
            )

    @staticmethod
    def _normalize_agent(agent: str) -> str:
        """Normaliza el nombre de un agente: asegura prefijo @."""
        agent = agent.strip()
        if not agent.startswith("@"):
            agent = f"@{agent}"
        return agent

    @staticmethod
    def _deserialize_message(record: dict[str, Any]) -> dict[str, Any]:
        """Convierte un registro del store en un dict de mensaje legible.

        Los registros de LanceVectorStore devuelven ``metadata`` como un dict
        (o string JSON) y los campos individuales como atributos top-level.
        Esta funcion unifica ambos.
        """
        meta = record.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # Combinar: metadata tiene los campos originales,
        # top-level puede tener campos actualizados (ej. status)
        result: dict[str, Any] = dict(meta)

        # Los campos top-level sobreescriben metadata
        for key in ("id", "channel", "thread_id", "from_agent", "to_agent",
                     "message", "message_type", "status", "task_id",
                     "created_at"):
            val = record.get(key)
            if val is not None:
                result[key] = val

        # Deserializar attachments si es string JSON
        att = result.get("attachments")
        if isinstance(att, str):
            try:
                result["attachments"] = json.loads(att)
            except (json.JSONDecodeError, TypeError):
                result["attachments"] = []

        # Asegurar tipo de iteracion
        result["iteration"] = int(result.get("iteration", 0))

        return result

    @staticmethod
    def _default_embedding(text: str) -> np.ndarray:
        """Embedding por defecto. Delega en harness.common.fallback_embedding."""
        return fallback_embedding(text)

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


# ---------------------------------------------------------------------------
# AsyncAgentBus â€” version asincrona para PaCoRe (ADR-0017)
# ---------------------------------------------------------------------------


class AsyncAgentBus:
    """
    AgentBus asincrono con asyncio.Queue para coordinacion PaCoRe.

    Permite post/consume de mensajes sin bloqueo, con timeout y cancelacion.
    Cada canal tiene su propia cola asincrona.

    Reference:
        PaCoRe (Parallel Coordination + RL message-passing) â€” ADR-0017
        MPAC95: 95% overhead reduction, 4.8x speedup
    """

    def __init__(self, loop=None):
        import asyncio
        self._queues: dict[str, asyncio.Queue] = {}
        self._loop = loop or asyncio.get_event_loop()
        self._lock = asyncio.Lock()

    async def post_message(self, channel: str, message: Any) -> None:
        """
        Publicar mensaje en un canal (non-blocking).

        Args:
            channel: Nombre del canal.
            message: Mensaje a publicar.

        Raises:
            AssertionError: Si los parametros no pasan las validaciones refinement.
        """
        # Refinement type validations
        assert isinstance(channel, str) and len(channel) > 0, (
            "channel must be a non-empty string"
        )
        async with self._lock:
            if channel not in self._queues:
                import asyncio
                self._queues[channel] = asyncio.Queue()
        await self._queues[channel].put(message)

    async def consume(self, channel: str, timeout: float = 30.0) -> Any:
        """
        Consumir mensaje de un canal con timeout.

        Args:
            channel: Nombre del canal.
            timeout: Timeout en segundos.

        Returns:
            Mensaje del canal.

        Raises:
            AssertionError: Si los parametros no pasan las validaciones refinement.
            asyncio.TimeoutError: Si no hay mensaje dentro del timeout.
        """
        # Refinement type validations
        assert isinstance(channel, str) and len(channel) > 0, (
            "channel must be a non-empty string"
        )
        assert isinstance(timeout, (int, float)) and timeout > 0, (
            f"timeout must be > 0: {timeout}"
        )
        async with self._lock:
            if channel not in self._queues:
                import asyncio
                self._queues[channel] = asyncio.Queue()
        import asyncio
        return await asyncio.wait_for(
            self._queues[channel].get(), timeout=timeout
        )

    def get_queue_size(self, channel: str) -> int:
        """Tamanio actual de la cola de un canal."""
        q = self._queues.get(channel)
        return q.qsize() if q else 0
