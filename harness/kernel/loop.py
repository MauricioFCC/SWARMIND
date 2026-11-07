"""Loop de dispatch determinista del kernel (single-thread, FIFO, sin spawn)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .envelope import MessageEnvelope
from .event_log import EventLog
from .mailbox import BoundedMailbox

logger = logging.getLogger("harness.kernel.loop")

#: Firma de un handler: recibe payload y envelope, devuelve un resultado libre.
Handler = Callable[[Mapping[str, Any], MessageEnvelope], Any]


class UnregisteredKindError(LookupError):
    """No hay handler registrado para el ``kind`` del mensaje."""


@dataclass
class KernelStats:
    """Contadores del kernel (telemetría de dispatch y errores)."""

    dispatched: int = 0
    errors: int = 0
    unregistered: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


class KernelLoop:
    """Kernel de mensajes determinista (single-loop).

    Args:
        mailbox: Buzón acotado de entrada.
        event_log: Registro append-only de eventos.
        fail_fast: Si True, un handler que falla aborta el loop (crash-only);
            por defecto se registra el fallo y se continúa.

    Raises:
        ValueError: Si ``mailbox`` o ``event_log`` son ``None``.
    """

    def __init__(
        self,
        mailbox: BoundedMailbox,
        event_log: EventLog,
        fail_fast: bool = False,
    ) -> None:
        if mailbox is None or event_log is None:
            raise ValueError("KernelLoop: mailbox y event_log son obligatorios")
        self._mailbox = mailbox
        self._log = event_log
        self._fail_fast = fail_fast
        self._handlers: dict[str, Handler] = {}
        self._stats = KernelStats()

    @property
    def stats(self) -> KernelStats:
        """Contadores del kernel (snapshot)."""
        return KernelStats(
            dispatched=self._stats.dispatched,
            errors=self._stats.errors,
            unregistered=self._stats.unregistered,
            by_kind=dict(self._stats.by_kind),
        )

    def register(self, kind: str, handler: Handler) -> None:
        """Registra (o reemplaza) el handler de un tipo de mensaje.

        Args:
            kind: Tipo de mensaje.
            handler: Callable ``(payload, envelope) -> Any``.

        Raises:
            ValueError: Si ``kind`` está vacío o ``handler`` no es callable.
        """
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("KernelLoop.register: kind vacio")
        if not callable(handler):
            raise TypeError(f"KernelLoop.register: handler no callable ({type(handler).__name__})")
        self._handlers[kind] = handler

    def submit(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trace_id: str = "",
        source: str = "",
    ) -> MessageEnvelope:
        """Registra el mensaje en el log y lo encola (devuelve el envelope).

        Args:
            kind: Tipo de mensaje.
            payload: Datos del mensaje.
            trace_id: Correlación req/resp.
            source: Origen lógico.

        Raises:
            MailboxFullError: Si la cola está llena (backpressure).
        """
        # Replay: el log solo contiene mensajes aceptados (sin backpressure fantasma).
        envelope = self._build_envelope(kind, payload, trace_id, source)
        self._mailbox.put(envelope)
        self._log.append(
            kind,
            envelope.payload,
            trace_id=trace_id,
            source=source,
            seq=envelope.seq,
        )
        return envelope

    def _build_envelope(
        self,
        kind: str,
        payload: Mapping[str, Any] | None,
        trace_id: str,
        source: str,
    ) -> MessageEnvelope:
        """Construye el envelope con la próxima secuencia del log."""
        return MessageEnvelope(
            seq=self._log.next_seq,
            kind=kind,
            payload=dict(payload or {}),
            trace_id=trace_id,
            source=source,
        )

    def step(self) -> MessageEnvelope | None:
        """Despacha **un** mensaje (FIFO) y devuelve su envelope."""
        envelope = self._mailbox.get()
        if envelope is None:
            return None
        self._dispatch(envelope)
        return envelope

    def run(self, max_messages: int | None = None) -> int:
        """Despacha mensajes hasta vaciar el buzón o alcanzar el límite.

        Args:
            max_messages: Máximo de mensajes a procesar (``None`` = todos).

        Returns:
            Número de mensajes despachados en esta pasada (0 si el buzón está
            vacío).
        """
        processed = 0
        while max_messages is None or processed < max_messages:
            envelope = self._mailbox.get()
            if envelope is None:
                break
            self._dispatch(envelope)
            processed += 1
        return processed

    def _dispatch(self, envelope: MessageEnvelope) -> None:
        """Ejecuta el handler del envelope y actualiza contadores."""
        self._stats.dispatched += 1
        kind = envelope.kind
        self._stats.by_kind[kind] = self._stats.by_kind.get(kind, 0) + 1
        handler = self._handlers.get(kind)
        if handler is None:
            self._on_unregistered(envelope)
            return
        try:
            handler(envelope.payload, envelope)
        except Exception as exc:  # noqa: BLE001 - se registra y se decide politica
            self._on_handler_error(envelope, exc)

    def _on_unregistered(self, envelope: MessageEnvelope) -> None:
        """Registra un kind sin handler y aplica ``fail_fast`` si procede."""
        self._stats.unregistered += 1
        logger.warning(
            "kernel: sin handler para kind=%s seq=%d", envelope.kind, envelope.seq
        )
        self._log.append(
            "kernel.unregistered",
            {"kind": envelope.kind, "seq": envelope.seq},
            trace_id=envelope.trace_id,
            source="kernel",
        )
        if self._fail_fast:
            raise UnregisteredKindError(
                f"KernelLoop | WHAT=kind_sin_handler | WHY=no_registrado | "
                f"WHERE=_dispatch | kind={envelope.kind!r} | seq={envelope.seq}"
            )

    def _on_handler_error(self, envelope: MessageEnvelope, exc: Exception) -> None:
        """Registra el fallo del handler y lo re-lanza si ``fail_fast``."""
        self._stats.errors += 1
        logger.exception(
            "kernel: handler fallo kind=%s seq=%d trace=%s",
            envelope.kind,
            envelope.seq,
            envelope.trace_id,
        )
        self._log.append(
            "kernel.error",
            {
                "kind": envelope.kind,
                "seq": envelope.seq,
                "error": f"{type(exc).__name__}: {exc}",
            },
            trace_id=envelope.trace_id,
            source="kernel",
        )
        if self._fail_fast:
            raise exc

__all__ = ["Handler", "KernelLoop", "KernelStats", "UnregisteredKindError"]
