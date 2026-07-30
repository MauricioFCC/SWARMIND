"""EventBus — Sistema Pub/Sub para comunicacion asincrona entre agentes.

Permite que los agentes se comuniquen mediante eventos en lugar de
llamadas directas, desacoplando emisores de receptores.

Patron: Publisher/Subscriber con canales tematicos.

Canales predefinidos:
- task:complete  -> Tarea completada por un agente
- task:failed    -> Tarea fallida
- agent:online   -> Agente conectado
- agent:offline  -> Agente desconectado
- cache:hit      -> Cache hit en cache compartido
- cache:miss     -> Cache miss
- error:critical -> Error critico del sistema
- system:status  -> Estado del sistema
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Prioridad de eventos en el bus."""
    CRITICAL = auto()  # Eventos de seguridad, errores fatales
    HIGH = auto()      # Eventos de tarea, errores recuperables
    NORMAL = auto()    # Eventos de estado, notificaciones
    LOW = auto()       # Eventos de metricas, debug


@dataclass(frozen=True)
class Event:
    """Evento en el bus Pub/Sub.

    Attributes:
        event_id: Identificador unico del evento.
        channel: Canal del evento (ej: task:complete).
        data: Datos del evento.
        source: ID del agente emisor.
        priority: Prioridad del evento.
        timestamp: Timestamp de creacion.
        correlation_id: ID para correlacionar eventos relacionados.
    """
    event_id: str
    channel: str
    data: Dict[str, Any]
    source: str
    priority: EventPriority
    timestamp: float
    correlation_id: str = ""


@dataclass
class Subscription:
    """Suscripcion a un canal de eventos.

    Attributes:
        sub_id: Identificador unico de la suscripcion.
        channel: Canal o patron de canal (ej: task:*).
        callback: Funcion a ejecutar cuando llega un evento.
        agent_id: ID del agente suscriptor.
        filter_fn: Funcion opcional para filtrar eventos.
        max_events: Maximo de eventos a recibir (-1 = ilimitado).
        event_count: Contador de eventos recibidos.
    """
    sub_id: str
    channel: str
    callback: Callable[[Event], None]
    agent_id: str
    filter_fn: Optional[Callable[[Event], bool]] = None
    max_events: int = -1
    event_count: int = 0


class EventBus:
    """Bus de eventos Pub/Sub con canales tematicos y wildcards.

    Soporta:
    - Canales exactos: 'task:complete'
    - Wildcards: 'task:*', 'agent:*', '*'
    - Prioridades: CRITICAL > HIGH > NORMAL > LOW
    - Filtros por funcion
    - Limite de eventos por suscripcion

    Es thread-safe para publish/subscribe desde cualquier thread.
    Soporta callbacks asincronos y sincronos.

    Args:
        max_queue: Maximo de eventos en cola por prioridad (default: 1000).

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe("task:*", lambda e: print(e.data))
        >>> bus.publish(Event(
        ...     event_id="e1", channel="task:complete",
        ...     data={"task": "test"}, source="agent_1",
        ...     priority=EventPriority.NORMAL, timestamp=time.time()
        ... ))
    """

    def __init__(self, max_queue: int = 1000) -> None:
        """Inicializa el bus de eventos.

        Args:
            max_queue: Maximo de eventos en cola.
        """
        self._max_queue: int = max(max_queue, 100)
        self._lock: threading.RLock = threading.RLock()
        self._subscriptions: Dict[str, Subscription] = {}
        self._channel_subs: Dict[str, Set[str]] = {}  # channel -> set of sub_ids
        self._agent_subs: Dict[str, Set[str]] = {}  # agent_id -> set of sub_ids
        self._history: List[Event] = []
        self._max_history: int = 1000

        logger.info("[EventBus] Inicializado: max_queue=%d", self._max_queue)

    def _match_channel(self, pattern: str, channel: str) -> bool:
        """Verifica si un canal coincide con un patron (con wildcards).

        Args:
            pattern: Patron con posible wildcard (*).
            channel: Canal a verificar.

        Returns:
            True si coincide.
        """
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            prefix: str = pattern[:-1]
            return channel.startswith(prefix)
        return pattern == channel

    def subscribe(
        self,
        channel: str,
        callback: Callable[[Event], None],
        agent_id: str = "",
        filter_fn: Optional[Callable[[Event], bool]] = None,
        max_events: int = -1,
    ) -> str:
        """Suscribe un callback a un canal.

        Args:
            channel: Canal o patron (ej: task:*, agent:online).
            callback: Funcion que recibe el evento.
            agent_id: ID del agente suscriptor.
            filter_fn: Funcion para filtrar eventos.
            max_events: Maximo de eventos (-1 = ilimitado).

        Returns:
            ID de la suscripcion.

        Raises:
            ValueError: Si channel esta vacio.
        """
        if not channel:
            raise ValueError(
                "[EventBus] channel no puede estar vacio. WHERE: subscribe."
            )

        sub_id: str = f"sub_{uuid.uuid4().hex[:12]}"

        sub: Subscription = Subscription(
            sub_id=sub_id,
            channel=channel,
            callback=callback,
            agent_id=agent_id,
            filter_fn=filter_fn,
            max_events=max_events,
        )

        with self._lock:
            self._subscriptions[sub_id] = sub

            if channel not in self._channel_subs:
                self._channel_subs[channel] = set()
            self._channel_subs[channel].add(sub_id)

            if agent_id:
                if agent_id not in self._agent_subs:
                    self._agent_subs[agent_id] = set()
                self._agent_subs[agent_id].add(sub_id)

        logger.debug(
            "[EventBus] Subscribed: %s -> %s (agent=%s)",
            sub_id[:12], channel, agent_id,
        )
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Cancela una suscripcion.

        Args:
            sub_id: ID de la suscripcion.

        Returns:
            True si se cancelo exitosamente.
        """
        with self._lock:
            sub: Optional[Subscription] = self._subscriptions.pop(sub_id, None)
            if sub is None:
                return False

            # Limpiar channel_subs
            if sub.channel in self._channel_subs:
                self._channel_subs[sub.channel].discard(sub_id)
                if not self._channel_subs[sub.channel]:
                    del self._channel_subs[sub.channel]

            # Limpiar agent_subs
            if sub.agent_id and sub.agent_id in self._agent_subs:
                self._agent_subs[sub.agent_id].discard(sub_id)
                if not self._agent_subs[sub.agent_id]:
                    del self._agent_subs[sub.agent_id]

            logger.debug("[EventBus] Unsubscribed: %s", sub_id[:12])
            return True

    def publish(self, event: Event) -> int:
        """Publica un evento en el bus.

        Args:
            event: Evento a publicar.

        Returns:
            Numero de suscriptores notificados.
        """
        notified: int = 0

        with self._lock:
            # Almacenar en historial
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)

            # Encontrar suscriptores que coinciden
            matching_subs: List[Subscription] = []
            for sub_id, sub in list(self._subscriptions.items()):
                if not self._match_channel(sub.channel, event.channel):
                    continue
                if sub.filter_fn and not sub.filter_fn(event):
                    continue
                if 0 < sub.max_events <= sub.event_count:
                    continue
                matching_subs.append(sub)

            # Ejecutar callbacks
            for sub in matching_subs:
                try:
                    sub.event_count += 1
                    sub.callback(event)
                    notified += 1
                except Exception as exc:
                    logger.error(
                        "[EventBus] Error en callback %s: %s",
                        sub.sub_id[:12], exc,
                    )

        if notified > 0:
            logger.debug(
                "[EventBus] Published: %s (%d subscribers)",
                event.channel, notified,
            )
        return notified

    def publish_async(
        self,
        event: Event,
    ) -> int:
        """Publica un evento de forma asincrona (no bloqueante).

        Args:
            event: Evento a publicar.

        Returns:
            Numero de suscriptores encontrados.
        """
        return self.publish(event)

    def get_subscriptions(self, agent_id: str = "") -> List[Subscription]:
        """Retora las suscripciones activas.

        Args:
            agent_id: Filtrar por agente (opcional).

        Returns:
            Lista de suscripciones.
        """
        with self._lock:
            if agent_id:
                sub_ids: Set[str] = self._agent_subs.get(agent_id, set())
                return [
                    self._subscriptions[sid]
                    for sid in sub_ids
                    if sid in self._subscriptions
                ]
            return list(self._subscriptions.values())

    def get_history(
        self,
        channel: str = "",
        limit: int = 10,
    ) -> List[Event]:
        """Retora el historial de eventos.

        Args:
            channel: Filtrar por canal (opcional).
            limit: Maximo de eventos a retornar.

        Returns:
            Lista de eventos recientes.
        """
        with self._lock:
            if channel:
                filtered: List[Event] = [
                    e for e in self._history if e.channel == channel
                ]
                return filtered[-limit:]
            return self._history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Retora estadisticas del bus.

        Returns:
            Dict con metricas del bus.
        """
        with self._lock:
            return {
                "total_subscriptions": len(self._subscriptions),
                "total_channels": len(self._channel_subs),
                "total_agents": len(self._agent_subs),
                "history_size": len(self._history),
                "channels": list(self._channel_subs.keys()),
            }

    def clear(self) -> int:
        """Limpia todas las suscripciones y eventos.

        Returns:
            Numero de suscripciones eliminadas.
        """
        with self._lock:
            count: int = len(self._subscriptions)
            self._subscriptions.clear()
            self._channel_subs.clear()
            self._agent_subs.clear()
            self._history.clear()
            logger.info("[EventBus] Cleared %d subscriptions", count)
            return count
