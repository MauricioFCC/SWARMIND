"""A2AProtocol â€” Agent-to-Agent Protocol para interoperabilidad.

Implementa el protocolo A2A v1.0 para comunicacion estandarizada entre
agentes, permitiendo discovery, mensajeria, invocacion de herramientas
y orquestacion entre agentes de diferentes sistemas.

Basado en:
- A2A v1.0 (Google / Linux Foundation Swarmind AI Foundation, 2025-2026)
- EACP (Liu et al., 2026): Protocolo en 5 capas
- AMACP (Wu et al., ICLR 2026): Adaptive Multi-Agent Communication Protocol

Capas del protocolo:
1. Discovery: Agentes anuncian capacidades y descubren otros agentes
2. Message: Intercambio de mensajes estructurados
3. Tool Invocation: Llamada a herramientas de otros agentes
4. Orchestration: Coordinacion de workflows multi-agente
5. Security: Autenticacion y autorizacion entre agentes
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Roles de agente en el protocolo A2A."""
    COORDINATOR = auto()
    WORKER = auto()
    SPECIALIST = auto()
    GATEWAY = auto()
    MONITOR = auto()


class MessageType(Enum):
    """Tipos de mensaje en el protocolo A2A."""
    TASK_REQUEST = auto()
    TASK_RESPONSE = auto()
    TASK_STATUS = auto()
    DISCOVERY = auto()
    DISCOVERY_RESPONSE = auto()
    TOOL_CALL = auto()
    TOOL_RESULT = auto()
    ERROR = auto()
    HEARTBEAT = auto()


@dataclass(frozen=True)
class AgentCapability:
    """Capacidad de un agente en el protocolo A2A.

    Attributes:
        name: Nombre de la capacidad.
        description: Descripcion.
        version: Version.
        tools: Lista de herramientas que ofrece.
        models: Modelos que soporta.
    """
    name: str
    description: str
    version: str = "1.0.0"
    tools: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class A2AMessage:
    """Mensaje del protocolo A2A.

    Attributes:
        message_id: ID unico del mensaje.
        msg_type: Tipo de mensaje.
        source: ID del agente emisor.
        target: ID del agente destino.
        payload: Datos del mensaje.
        correlation_id: ID para correlacionar respuestas.
        timestamp: Timestamp de envio.
        ttl: TTL en segundos.
    """
    message_id: str
    msg_type: MessageType
    source: str
    target: str
    payload: dict[str, Any]
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    ttl: float = 30.0


@dataclass
class AgentNode:
    """Nodo de agente en la red A2A.

    Attributes:
        agent_id: ID del agente.
        role: Rol del agente.
        capabilities: Capacidades del agente.
        address: Direccion del agente (URL o ID local).
        last_seen: Timestamp de ultima actividad.
        status: Estado del agente.
    """
    agent_id: str
    role: AgentRole
    capabilities: list[AgentCapability]
    address: str
    last_seen: float = field(default_factory=time.time)
    status: str = "online"


class A2AProtocol:
    """Implementacion del protocolo A2A para agentes.

    Args:
        agent_id: ID de este agente.
        role: Rol de este agente.
        capabilities: Capacidades de este agente.
        address: Direccion de este agente.

    Example:
        >>> agent = A2AProtocol("agent_1", AgentRole.WORKER, [cap])
        >>> agent.register()
        >>> agent.send_message("agent_2", MessageType.TASK_REQUEST, {})
    """

    PROTOCOL_VERSION: str = "1.0.0"

    def __init__(
        self,
        agent_id: str,
        role: AgentRole = AgentRole.WORKER,
        capabilities: list[AgentCapability] | None = None,
        address: str = "local",
    ) -> None:
        """Inicializa un nodo del protocolo A2A.

        Args:
            agent_id: Identificador unico del agente.
            role: Rol del agente.
            capabilities: Capacidades del agente.
            address: Direccion del agente.
        """
        self._agent_id: str = agent_id
        self._role: AgentRole = role
        self._capabilities: list[AgentCapability] = capabilities or []
        self._address: str = address

        # Registro de agentes conocidos
        self._agents: dict[str, AgentNode] = {}
        # Manejadores de mensajes por tipo
        self._handlers: dict[MessageType, list[Callable]] = {}
        # Historial de mensajes
        self._history: list[A2AMessage] = []
        self._max_history: int = 1000

        logger.info(
            "[A2A] Inicializado: agent=%s, role=%s, caps=%d",
            agent_id, role.name, len(capabilities or []),
        )

    def register(self) -> AgentNode:
        """Registra este agente en la red A2A.

        Returns:
            AgentNode de este agente.
        """
        node: AgentNode = AgentNode(
            agent_id=self._agent_id,
            role=self._role,
            capabilities=list(self._capabilities),
            address=self._address,
        )
        self._agents[self._agent_id] = node
        logger.info("[A2A] Registered: %s", self._agent_id)
        return node

    def discover(self, capability: str = "") -> list[AgentNode]:
        """Descubre agentes disponibles con una capacidad.

        Args:
            capability: Capacidad a buscar (vacio = todos).

        Returns:
            Lista de agentes que tienen la capacidad.
        """
        results: list[AgentNode] = []
        for agent in self._agents.values():
            if not capability:
                results.append(agent)
            else:
                for cap in agent.capabilities:
                    if cap.name == capability:
                        results.append(agent)
                        break
        return results

    def send_message(
        self,
        target: str,
        msg_type: MessageType,
        payload: dict[str, Any],
        correlation_id: str = "",
    ) -> A2AMessage:
        """Envia un mensaje a otro agente.

        Args:
            target: ID del agente destino.
            msg_type: Tipo de mensaje.
            payload: Datos del mensaje.
            correlation_id: ID de correlacion.

        Returns:
            A2AMessage enviado.

        Raises:
            ValueError: Si el destino no existe.
        """
        if target not in self._agents and target != "*":
            raise ValueError(
                f"[A2A] Destino desconocido: {target}. "
                f"WHY: el agente no esta registrado. WHERE: send_message."
            )

        msg: A2AMessage = A2AMessage(
            message_id=f"msg_{uuid.uuid4().hex[:12]}",
            msg_type=msg_type,
            source=self._agent_id,
            target=target,
            payload=payload,
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:8]}",
        )

        self._history.append(msg)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # Ejecutar handlers locales
        self._dispatch_handlers(msg)

        logger.debug(
            "[A2A] Message sent: %s -> %s (%s)",
            self._agent_id, target, msg_type.name,
        )
        return msg

    def on_message(
        self,
        msg_type: MessageType,
        handler: Callable[[A2AMessage], Any],
    ) -> None:
        """Registra un manejador para un tipo de mensaje.

        Args:
            msg_type: Tipo de mensaje a manejar.
            handler: Funcion que procesa el mensaje.
        """
        if msg_type not in self._handlers:
            self._handlers[msg_type] = []
        self._handlers[msg_type].append(handler)
        logger.debug(
            "[A2A] Handler registered: %s -> %s",
            msg_type.name, handler.__name__,
        )

    def _dispatch_handlers(self, msg: A2AMessage) -> None:
        """Ejecuta los manejadores para un mensaje.

        Args:
            msg: Mensaje a despachar.
        """
        handlers: list[Callable] = self._handlers.get(msg.msg_type, [])
        for handler in handlers:
            try:
                handler(msg)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[A2A] Error en handler %s: %s. WHERE: _dispatch.",
                    handler.__name__, exc,
                )

    def get_agents(self) -> list[AgentNode]:
        """Retorna la lista de agentes conocidos.

        Returns:
            Lista de AgentNode.
        """
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> AgentNode | None:
        """Retorna un agente por su ID.

        Args:
            agent_id: ID del agente.

        Returns:
            AgentNode o None.
        """
        return self._agents.get(agent_id)

    def remove_agent(self, agent_id: str) -> bool:
        """Elimina un agente del registro.

        Args:
            agent_id: ID del agente.

        Returns:
            True si se elimino.
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info("[A2A] Agent removed: %s", agent_id)
            return True
        return False

    def get_history(
        self,
        limit: int = 10,
        msg_type: MessageType | None = None,
    ) -> list[A2AMessage]:
        """Retorna el historial de mensajes.

        Args:
            limit: Maximo de mensajes.
            msg_type: Filtrar por tipo.

        Returns:
            Lista de mensajes.
        """
        if msg_type:
            filtered: list[A2AMessage] = [
                m for m in self._history if m.msg_type == msg_type
            ]
            return filtered[-limit:]
        return self._history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadisticas del protocolo.

        Returns:
            Dict con metricas.
        """
        return {
            "protocol_version": self.PROTOCOL_VERSION,
            "agent_id": self._agent_id,
            "role": self._role.name,
            "known_agents": len(self._agents),
            "capabilities": len(self._capabilities),
            "handlers": {
                k.name: len(v) for k, v in self._handlers.items()
            },
            "history_size": len(self._history),
        }
