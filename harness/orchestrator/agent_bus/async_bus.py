"""AsyncAgentBus — version asincrona para PaCoRe (ADR-0017).

Extraccion mecanica de la clase ``AsyncAgentBus`` del modulo original
``harness/orchestrator/agent_bus.py`` (sin cambios de logica ni firmas).
"""

from __future__ import annotations

import asyncio
from typing import Any


class AsyncAgentBus:
    """
    AgentBus asincrono con asyncio.Queue para coordinacion PaCoRe.

    Permite post/consume de mensajes sin bloqueo, con timeout y cancelacion.
    Cada canal tiene su propia cola asincrona.

    Reference:
        PaCoRe (Parallel Coordination + RL message-passing) — ADR-0017
        MPAC95: 95% overhead reduction, 4.8x speedup
    """

    def __init__(self, loop=None):
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
                self._queues[channel] = asyncio.Queue()
        return await asyncio.wait_for(
            self._queues[channel].get(), timeout=timeout
        )

    def get_queue_size(self, channel: str) -> int:
        """Tamanio actual de la cola de un canal."""
        q = self._queues.get(channel)
        return q.qsize() if q else 0
