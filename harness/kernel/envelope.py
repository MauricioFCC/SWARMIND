"""Sobre inmutable de mensajes del kernel SWARMIND."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def _utcnow_iso() -> str:
    """Timestamp UTC ISO-8601 del mensaje."""
    return dt.datetime.now(dt.UTC).isoformat()


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Mensaje inmutable del kernel.

    Args:
        seq: Secuencia monotónica asignada por el ``EventLog`` (orden canónico).
        kind: Tipo de mensaje (p. ej. ``task.dispatch``); selecciona el handler.
        payload: Datos del mensaje (se congelan en ``__post_init__``).
        trace_id: Identificador de correlación para req/resp.
        source: Origen lógico (agente, componente o adapter).
        created_at: Timestamp UTC ISO-8601 de creación.

    Raises:
        TypeError: Si ``payload`` no es un mapping.
    """

    seq: int
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    source: str = ""
    created_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        """Congela el payload y valida la forma minima del envelope."""
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("MessageEnvelope: kind vacio o no-str")
        if not isinstance(self.payload, Mapping):
            raise TypeError(
                f"MessageEnvelope: payload debe ser Mapping, no {type(self.payload).__name__}"
            )
        if not isinstance(self.payload, MappingProxyType):
            object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def as_dict(self) -> dict[str, Any]:
        """Representación serializable (para logs/event store durable)."""
        return {
            "seq": self.seq,
            "kind": self.kind,
            "payload": dict(self.payload),
            "trace_id": self.trace_id,
            "source": self.source,
            "created_at": self.created_at,
        }


__all__ = ["MessageEnvelope"]
