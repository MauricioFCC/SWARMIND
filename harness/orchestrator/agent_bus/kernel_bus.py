"""Bus determinista del orchestrator sobre el kernel event-driven.

Implementa el contrato de ``KernelBus`` descrito en el spec
``docs/specs/kernel-event-driven-nautilus.md`` (AC-KN1..AC-KN4):

- **Un solo loop** de dispatch (``KernelLoop``), sin ``spawn`` por mensaje.
- **Cola FIFO acotada** con backpressure tipado (``MailboxFullError``).
- **Mensajes inmutables** con ``seq`` monotónica y ``trace_id`` correlacionado.
- **Event log** append-only para ``replay`` determinista (mismo ``seed`` lógico:
  el orden de publicación).

Este bus NO reemplaza a ``AgentBus`` (persistencia en LanceDB) ni a
``AsyncAgentBus`` (I/O entre procesos): es el sustrato determinista para
publicar eventos internos del orchestrator y poder reproducirlos en tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.kernel import (
    BoundedMailbox,
    EventLog,
    KernelLoop,
    KernelStats,
    MessageEnvelope,
)

from .errors import AgentBusError

__all__ = ["KernelBus", "KernelBusError"]


class KernelBusError(AgentBusError):
    """Error del bus determinista (handler/tipo no registrado)."""


class KernelBus:
    """Bus publish/subscribe determinista (single-loop, FIFO).

    Args:
        capacity: Capacidad del buzón de entrada (>= 1).
        log_entries: Capacidad del event log (>= 1).
        fail_fast: Si True, un handler que falla o un ``kind`` sin suscriptor
            aborta el dispatch (crash-only). Default: registrar y continuar.

    Raises:
        ValueError: Si ``capacity`` o ``log_entries`` no son positivos.
    """

    def __init__(
        self,
        capacity: int = 1024,
        log_entries: int = 10_000,
        *,
        fail_fast: bool = False,
    ) -> None:
        self._mailbox = BoundedMailbox(capacity=capacity)
        self._log = EventLog(max_entries=log_entries)
        self._kernel = KernelLoop(self._mailbox, self._log, fail_fast=fail_fast)
        self._fail_fast = bool(fail_fast)

    def subscribe(self, kind: str, handler: Any) -> None:
        """Registra el handler de un tipo de evento.

        Args:
            kind: Tipo de evento (p. ej. ``task.completed``).
            handler: Callable ``(payload, envelope) -> Any``.

        Raises:
            KernelBusError: Si el handler no es invocable.
        """
        try:
            self._kernel.register(kind, handler)
        except (TypeError, ValueError) as exc:
            raise KernelBusError(f"KernelBus.subscribe | {exc}") from exc

    def publish(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trace_id: str = "",
        source: str = "",
        drain: bool = True,
    ) -> MessageEnvelope:
        """Publica un evento y (por defecto) lo despacha de inmediato.

        Args:
            kind: Tipo de evento.
            payload: Datos del evento (se congelan en el envelope).
            trace_id: Correlación req/resp entre eventos relacionados.
            source: Origen lógico del evento.
            drain: Si True, procesa la cola antes de retornar (determinista).

        Returns:
            Envelope aceptado, con ``seq`` asignada.

        Raises:
            KernelBusError: Si el buzón está lleno (backpressure).
        """
        envelope = self._submit(kind, payload, trace_id, source)
        if drain:
            self.drain()
        return envelope

    def _submit(
        self,
        kind: str,
        payload: Mapping[str, Any] | None,
        trace_id: str,
        source: str,
    ) -> MessageEnvelope:
        """Encola el evento y re-tipa la backpressure como ``KernelBusError``."""
        try:
            return self._kernel.submit(
                kind, payload, trace_id=trace_id, source=source
            )
        except RuntimeError as exc:
            raise KernelBusError(
                f"KernelBus.publish | WHAT=backpressure | WHY=buzon_lleno | "
                f"WHERE=publish | kind={kind!r} | detalle={exc}"
            ) from exc

    def drain(self) -> int:
        """Despacha todos los eventos pendientes en orden FIFO.

        Returns:
            Número de eventos despachados.

        Raises:
            KernelBusError: Si ``fail_fast`` y un handler falla o no existe.
        """
        try:
            return self._kernel.run()
        except Exception as exc:
            raise KernelBusError(
                f"KernelBus.drain | WHAT=fallo_dispatch | WHY=fail_fast | "
                f"WHERE=drain | detalle={type(exc).__name__}: {exc}"
            ) from exc

    def replay(self) -> list[dict[str, Any]]:
        """Representación serializable del event log (contrato de replay)."""
        return self._log.replay()

    def pending(self) -> int:
        """Número de eventos encolados sin despachar."""
        return len(self._mailbox)

    @property
    def stats(self) -> KernelStats:
        """Contadores de dispatch/errores del kernel."""
        return self._kernel.stats

    @property
    def fail_fast(self) -> bool:
        """Si el bus aborta ante el primer error de dispatch."""
        return self._fail_fast
