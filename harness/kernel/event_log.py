"""Registro append-only de eventos del kernel (contrato de replay)."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Mapping
from typing import Any

from .envelope import MessageEnvelope


class EventLogFullError(RuntimeError):
    """El event log alcanzó su capacidad máxima (fail-stop, no descarte)."""


class EventLog:
    """Registro ordenado por ``seq`` de los envelopes despachados.

    Args:
        max_entries: Capacidad máxima (>= 1).
        overflow: ``"raise"`` (default, fail-stop) o ``"drop_oldest"``.

    Raises:
        ValueError: Si ``max_entries`` no es positivo o ``overflow`` es inválido.
    """

    def __init__(self, max_entries: int = 10_000, overflow: str = "raise") -> None:
        if max_entries <= 0:
            raise ValueError("EventLog: max_entries debe ser > 0")
        if overflow not in ("raise", "drop_oldest"):
            raise ValueError(f"EventLog: overflow invalido: {overflow!r}")
        self._max = int(max_entries)
        self._overflow = overflow
        self._entries: deque[MessageEnvelope] = deque()
        self._lock = threading.Lock()
        self._next_seq = 1

    @property
    def next_seq(self) -> int:
        """Siguiente secuencia que se asignará."""
        return self._next_seq

    def append(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trace_id: str = "",
        source: str = "",
        seq: int | None = None,
    ) -> MessageEnvelope:
        """Añade un envelope al log y lo devuelve (``seq`` asignada o explícita).

        Args:
            kind: Tipo de mensaje.
            payload: Datos del mensaje.
            trace_id: Correlación req/resp.
            source: Origen lógico.
            seq: Secuencia explícita (replay); por defecto la siguiente.

        Raises:
            EventLogFullError: Si está lleno y ``overflow="raise"``.
        """
        with self._lock:
            self._reserve_slot()
            envelope = self._build(kind, payload, trace_id, source, seq)
            self._entries.append(envelope)
            if seq is None or int(seq) >= self._next_seq:
                self._next_seq = envelope.seq + 1
            return envelope

    def _reserve_slot(self) -> None:
        """Libera o rechaza un slot según la política de overflow."""
        if len(self._entries) < self._max:
            return
        if self._overflow == "raise":
            raise EventLogFullError(
                "EventLog | WHAT=log_lleno | "
                f"WHY=capacidad_excedida | WHERE=append | max={self._max}"
            )
        self._entries.popleft()

    def _build(
        self,
        kind: str,
        payload: Mapping[str, Any] | None,
        trace_id: str,
        source: str,
        seq: int | None,
    ) -> MessageEnvelope:
        """Construye el envelope con la secuencia asignada o explícita."""
        return MessageEnvelope(
            seq=self._next_seq if seq is None else int(seq),
            kind=kind,
            payload=dict(payload or {}),
            trace_id=trace_id,
            source=source,
        )

    def entries(self) -> tuple[MessageEnvelope, ...]:
        """Copia inmutable de los envelopes en orden de ``seq``."""
        with self._lock:
            return tuple(self._entries)

    def replay(self) -> list[dict[str, Any]]:
        """Representación serializable del log (para diagnóstico/replay)."""
        return [envelope.as_dict() for envelope in self.entries()]

    def __len__(self) -> int:
        """Número de eventos registrados."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Vacía el log y reinicia la secuencia."""
        with self._lock:
            self._entries.clear()
            self._next_seq = 1


__all__ = ["EventLog", "EventLogFullError"]
