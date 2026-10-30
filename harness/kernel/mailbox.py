"""Cola FIFO acotada con backpressure tipado (sin descartes silenciosos)."""

from __future__ import annotations

import threading
from collections import deque

from .envelope import MessageEnvelope


class MailboxFullError(RuntimeError):
    """La cola está llena: el productor debe esperar o degradar explícitamente."""


class BoundedMailbox:
    """Buzón FIFO acotado y thread-safe.

    Args:
        capacity: Capacidad máxima (>= 1).

    Raises:
        ValueError: Si ``capacity`` no es positivo.
    """

    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError(f"BoundedMailbox: capacity debe ser > 0, no {capacity}")
        self._capacity = int(capacity)
        self._items: deque[MessageEnvelope] = deque()
        self._lock = threading.Lock()
        self._rejected = 0

    @property
    def capacity(self) -> int:
        """Capacidad máxima del buzón."""
        return self._capacity

    @property
    def rejected(self) -> int:
        """Mensajes rechazados por backpressure (telemetría)."""
        return self._rejected

    def __len__(self) -> int:
        """Número de mensajes pendientes."""
        with self._lock:
            return len(self._items)

    def put(self, envelope: MessageEnvelope) -> None:
        """Encola un mensaje o falla con ``MailboxFullError``.

        Args:
            envelope: Mensaje a encolar.

        Raises:
            MailboxFullError: Si no hay capacidad disponible.
        """
        with self._lock:
            if len(self._items) >= self._capacity:
                self._rejected += 1
                raise MailboxFullError(
                    "BoundedMailbox | WHAT=cola_llena | "
                    f"WHY=backpressure | WHERE=put | capacity={self._capacity}"
                )
            self._items.append(envelope)

    def get(self) -> MessageEnvelope | None:
        """Extrae el mensaje más antiguo (FIFO) o ``None`` si está vacío."""
        with self._lock:
            return self._items.popleft() if self._items else None

    def drain(self) -> list[MessageEnvelope]:
        """Vacía el buzón preservando el orden FIFO."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
            return items

    def clear(self) -> None:
        """Descarta los mensajes pendientes (no cuenta como backpressure)."""
        with self._lock:
            self._items.clear()


__all__ = ["BoundedMailbox", "MailboxFullError"]
