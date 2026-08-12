"""AgentBus core â€” clase base ``AgentBus``.

Contiene el estado, payload builder y helpers estaticos. Los metodos de
envio viven en ``_MessagingMixin`` (messaging.py), lectura en
``_ReadingMixin`` (reading.py) y estados en ``_StatusMixin`` (status.py).

Extraccion mecanica del modulo original
``harness/orchestrator/agent_bus.py`` (sin cambios de logica ni firmas).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from harness.common import fallback_embedding
from harness.memory_rag.lance_vector_store import LanceVectorStore

from .constants import _COLLECTION, _VALID_MESSAGE_TYPES
from .exceptions import InvalidMessageError
from .messaging import _MessagingMixin
from .reading import _ReadingMixin

logger = logging.getLogger(__name__)


class AgentBus(_MessagingMixin, _ReadingMixin):
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
    # Metodos de utilidad
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
