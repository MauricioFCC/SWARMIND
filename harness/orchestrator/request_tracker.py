"""Correlación petición/respuesta sobre el kernel (AC-KN5).

Implementa el patrón *request/reply* con `trace_id` sobre cualquier bus que
cumpla ``BusPort`` (por defecto :class:`~harness.orchestrator.agent_bus.KernelBus`):

- La petición y la respuesta comparten ``trace_id`` (correlación estricta).
- Las respuestas se capturan por un handler registrado en el bus, no por
  polling ni `sleep` (tests deterministas).
- El tiempo se inyecta (``clock``) para poder probar el timeout sin esperar.
- Los timeouts son un error **tipado** con WHAT/WHY/WHERE.

Limitación declarada: el kernel es síncrono, así que el timeout se evalúa
*después* del dispatch (no puede interrumpir un handler colgado). Para I/O con
deadline real se usa un adapter asíncrono; el contrato de correlación es el
mismo.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Protocol

__all__ = ["BusPort", "RequestTimeoutError", "RequestTracker"]


class BusPort(Protocol):
    """Puerto mínimo de bus que consume el tracker."""

    def subscribe(self, kind: str, handler: Callable[..., Any]) -> None:
        """Registra el handler de un tipo de mensaje."""

    def publish(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trace_id: str = "",
        source: str = "",
        drain: bool = True,
    ) -> Any:
        """Publica un mensaje y (opcionalmente) lo despacha."""


class RequestTimeoutError(TimeoutError):
    """No hubo respuesta correlacionada dentro del presupuesto de tiempo.

    Args:
        message: Detalle WHAT/WHY/WHERE del fallo.
        trace_id: Correlación de la petición sin respuesta.
    """

    def __init__(self, message: str, *, trace_id: str = "") -> None:
        super().__init__(message)
        self.trace_id = trace_id


class RequestTracker:
    """Correlaciona peticiones y respuestas por ``trace_id``.

    Args:
        bus: Bus que cumple :class:`BusPort` (KernelBus en producción).
        clock: Reloj monótono inyectable (tests deterministas).

    Raises:
        ValueError: Si ``bus`` no expone ``subscribe`` y ``publish``.
    """

    def __init__(
        self, bus: BusPort, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if not hasattr(bus, "subscribe") or not hasattr(bus, "publish"):
            raise ValueError(
                "RequestTracker | WHAT=bus_invalido | WHY=no_cumple_BusPort | "
                "WHERE=__init__ | requiere subscribe+publish"
            )
        self._bus = bus
        self._clock = clock
        self._replies: dict[str, dict[str, Any]] = {}

    def request(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        reply_kind: str,
        timeout_s: float,
        trace_id: str | None = None,
        source: str = "request_tracker",
    ) -> dict[str, Any]:
        """Envía una petición y devuelve la respuesta correlacionada.

        Args:
            kind: Tipo del mensaje de petición.
            payload: Datos de la petición.
            reply_kind: Tipo del mensaje de respuesta esperado.
            timeout_s: Presupuesto máximo en segundos (debe ser > 0).
            trace_id: Correlación explícita (por defecto se genera).
            source: Origen lógico de la petición.

        Returns:
            Payload de la respuesta correlacionada.

        Raises:
            ValueError: Si ``timeout_s`` no es positivo.
            RequestTimeoutError: Si no hay respuesta o se excede el presupuesto.
        """
        if timeout_s <= 0:
            raise ValueError(
                "RequestTracker | WHAT=timeout_invalido | WHY=debe_ser_positivo | "
                f"WHERE=request | timeout_s={timeout_s}"
            )
        trace = trace_id or uuid.uuid4().hex
        self._bus.subscribe(reply_kind, self._capture)
        started = self._clock()
        self._bus.publish(kind, payload, trace_id=trace, source=source)
        return self._consume(trace, kind, reply_kind, started, timeout_s)

    def _consume(
        self,
        trace: str,
        kind: str,
        reply_kind: str,
        started: float,
        timeout_s: float,
    ) -> dict[str, Any]:
        """Recoge la respuesta correlacionada o lanza timeout tipado."""
        elapsed = self._clock() - started
        reply = self._replies.pop(trace, None)
        if reply is None:
            raise RequestTimeoutError(
                "RequestTracker | WHAT=sin_respuesta | WHY=no_llego_reply | "
                f"WHERE=request | kind={kind!r} | reply_kind={reply_kind!r} | "
                f"trace_id={trace}",
                trace_id=trace,
            )
        if elapsed > timeout_s:
            raise RequestTimeoutError(
                "RequestTracker | WHAT=timeout | WHY=excede_presupuesto | "
                f"WHERE=request | kind={kind!r} | elapsed={elapsed:.6f}s | "
                f"timeout_s={timeout_s} | trace_id={trace}",
                trace_id=trace,
            )
        return reply

    def _capture(self, payload: Mapping[str, Any], envelope: Any) -> None:
        """Guarda la respuesta indexada por el ``trace_id`` del envelope."""
        self._replies[str(envelope.trace_id)] = dict(payload)
