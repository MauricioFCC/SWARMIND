"""
Agent Message Bus — "Slack para Agentes"

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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

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
        vector_store: Optional[LanceVectorStore] = None,
    ) -> None:
        """
        Args:
            vector_store: Instancia de LanceVectorStore. Por defecto crea una nueva.
        """
        self.store = vector_store or LanceVectorStore()
        self._embedding_fn = self._default_embedding

    # ------------------------------------------------------------------
    # API publica: Envio de mensajes
    # ------------------------------------------------------------------

    def post_message(
        self,
        channel: str,
        from_agent: str,
        to_agent: str,
        message: str,
        message_type: str = "notification",
        task_id: Optional[str] = None,
        iteration: int = 0,
        attachments: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
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
        """
        # Validar parametros
        self._validate_message_params(
            channel, from_agent, to_agent, message, message_type,
        )

        # Generar IDs y timestamps
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        tid = thread_id or str(uuid.uuid4())

        # Normalizar nombres de agente (sin @ duplicado)
        from_agent = self._normalize_agent(from_agent)
        to_agent = self._normalize_agent(to_agent)

        # Construir payload de metadatos
        metadata: Dict[str, Any] = {
            "id": msg_id,
            "channel": channel,
            "thread_id": tid,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message": message,
            "message_type": message_type,
            "status": "sent",
            "task_id": task_id or "",
            "iteration": iteration,
            "attachments": json.dumps(attachments or []),
            "created_at": now,
        }

        # Generar embedding a partir del contenido del mensaje
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
    # API publica: Lectura de mensajes
    # ------------------------------------------------------------------

    def poll_channel(
        self,
        channel: str,
        agent_name: str,
        since_timestamp: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
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
        filters: Dict[str, Any] = {
            "channel": channel,
            "to_agent": agent_name,
        }

        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=limit, filters=filters,
            )
        except Exception as exc:
            logger.warning("Error en poll_channel: %s", exc)
            return []

        mensajes = []
        for r in results:
            msg = self._deserialize_message(r)
            if since_timestamp and msg.get("created_at", "") < since_timestamp:
                continue
            mensajes.append(msg)

        # Ordenar por timestamp ascendente
        mensajes.sort(key=lambda m: m.get("created_at", ""))

        return mensajes

    def get_thread(self, thread_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Recupera todo el hilo de conversacion de un thread_id.

        Args:
            thread_id: ID del hilo de conversacion.
            limit: Maximo de mensajes a retornar.

        Returns:
            Lista de mensajes del hilo ordenados cronologicamente.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=limit,
                filters={"thread_id": thread_id},
            )
        except Exception as exc:
            logger.warning("Error en get_thread: %s", exc)
            return []

        mensajes = [self._deserialize_message(r) for r in results]
        mensajes.sort(key=lambda m: m.get("created_at", ""))
        return mensajes

    def get_channel_history(
        self,
        channel: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Obtiene el historial completo de un canal.

        Args:
            channel: Nombre del canal.
            limit: Maximo de mensajes a retornar.

        Returns:
            Lista de mensajes del canal ordenados cronologicamente (mas reciente primero).
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=limit,
                filters={"channel": channel},
            )
        except Exception as exc:
            logger.warning("Error en get_channel_history: %s", exc)
            return []

        mensajes = [self._deserialize_message(r) for r in results]
        mensajes.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return mensajes

    def get_message_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Recupera un mensaje individual por su ID.

        Args:
            message_id: ID del mensaje.

        Returns:
            Dict con los datos del mensaje o None si no existe.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=1,
                filters={"id": message_id},
            )
        except Exception:
            return None

        if not results:
            return None
        return self._deserialize_message(results[0])

    # ------------------------------------------------------------------
    # API publica: Actualizacion de estado
    # ------------------------------------------------------------------

    def mark_delivered(self, message_id: str) -> bool:
        """Marca un mensaje como entregado (status = ``delivered``).

        Args:
            message_id: ID del mensaje a actualizar.

        Returns:
            True si se actualizo correctamente.
        """
        try:
            count = self.store.update_records(
                _COLLECTION,
                filters={"id": message_id},
                updates={"status": "delivered"},
            )
            if count > 0:
                logger.info("Mensaje %s marcado como delivered", message_id[:8])
                return True
            logger.warning("Mensaje %s no encontrado para mark_delivered", message_id[:8])
            return False
        except Exception as exc:
            logger.warning("Error en mark_delivered: %s", exc)
            return False

    def mark_acknowledged(self, message_id: str) -> bool:
        """Marca un mensaje como confirmado (status = ``acknowledged``).

        Args:
            message_id: ID del mensaje a actualizar.

        Returns:
            True si se actualizo correctamente.
        """
        try:
            count = self.store.update_records(
                _COLLECTION,
                filters={"id": message_id},
                updates={"status": "acknowledged"},
            )
            if count > 0:
                logger.info("Mensaje %s marcado como acknowledged", message_id[:8])
                return True
            logger.warning(
                "Mensaje %s no encontrado para mark_acknowledged", message_id[:8]
            )
            return False
        except Exception as exc:
            logger.warning("Error en mark_acknowledged: %s", exc)
            return False

    # ------------------------------------------------------------------
    # API publica: Circuit Breaker
    # ------------------------------------------------------------------

    def count_iterations(self, task_id: str) -> int:
        """Cuenta el numero de mensajes de error para una tarea.

        Util para el circuit breaker: cada ``message_type: "error"``
        con el mismo ``task_id`` cuenta como un intento fallido.

        Args:
            task_id: ID de la tarea a consultar.

        Returns:
            Numero de iteraciones fallidas registradas.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=1000,
                filters={
                    "task_id": task_id,
                    "message_type": "error",
                },
            )
        except Exception:
            return 0

        return len(results)

    def check_circuit_breaker(
        self,
        task_id: str,
        max_iterations: int = 5,
    ) -> bool:
        """Verifica si el circuit breaker se ha disparado para una tarea.

        El circuit breaker se dispara cuando el numero de mensajes de error
        para una tarea alcanza o supera ``max_iterations``.

        Args:
            task_id: ID de la tarea.
            max_iterations: Maximo de iteraciones permitidas (defecto: 5).

        Returns:
            True si el circuit breaker esta abierto (se debe escalar).
        """
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
            f"🚨 ESCALACION - Task: {task_id}\n"
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

    def get_channel_list(self) -> List[str]:
        """Retorna la lista de canales con actividad.

        Returns:
            Lista de nombres de canal unicos.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=5000,
            )
        except Exception:
            return []

        canales: set = set()
        for r in results:
            meta = self._deserialize_message(r)
            ch = meta.get("channel", "")
            if ch:
                canales.add(ch)
        return sorted(canales)

    def get_tasks_with_errors(self) -> List[str]:
        """Retorna los task_id que tienen mensajes de error.

        Returns:
            Lista de task_id con errores registrados.
        """
        try:
            dummy = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
            results = self.store.search(
                _COLLECTION, dummy, top_k=5000,
                filters={"message_type": "error"},
            )
        except Exception:
            return []

        tareas: set = set()
        for r in results:
            meta = self._deserialize_message(r)
            tid = meta.get("task_id", "")
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
    def _deserialize_message(record: Dict[str, Any]) -> Dict[str, Any]:
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
        result: Dict[str, Any] = dict(meta)

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
        """Embedding por defecto: vector de frecuencia de caracteres.

        Produce un vector normalizado de dimension fija a partir de
        conteos de caracteres. No es semanticamente significativo pero
        mantiene el sistema funcional sin un modelo de embeddings externo.
        """
        vec = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
        for i, ch in enumerate(text.encode("utf-8", errors="replace")):
            idx = (i * 7 + ch) % _EMBEDDING_DIM
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec
