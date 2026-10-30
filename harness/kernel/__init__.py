"""Kernel event-driven de SWARMIND (mensajes inmutables + cola bounded + log).

Contrato (spec `kernel-event-driven-nautilus.md`):

  - ``MessageEnvelope``: mensaje **inmutable** con ``seq`` monotónica,
    ``trace_id`` para correlación req/resp y payload congelado.
  - ``BoundedMailbox``: cola FIFO acotada con backpressure **tipado**
    (nunca descarta en silencio).
  - ``EventLog``: registro append-only ordenado por ``seq`` (contrato de
    replay/auditoría); al llenarse falla rápido por defecto.
  - ``KernelLoop``: dispatch síncrono en un solo hilo, sin ``spawn`` por
    mensaje; el handler recibe el payload y el envelope.

El kernel es agnóstico del dominio (no conoce agentes ni tools): los
handlers son la composición concreta.
"""

from __future__ import annotations

from .envelope import MessageEnvelope
from .event_log import EventLog, EventLogFullError
from .loop import KernelLoop, KernelStats, UnregisteredKindError
from .mailbox import BoundedMailbox, MailboxFullError

__all__ = [
    "BoundedMailbox",
    "EventLog",
    "EventLogFullError",
    "KernelLoop",
    "KernelStats",
    "MailboxFullError",
    "MessageEnvelope",
    "UnregisteredKindError",
]
