"""Modelos de datos para el paquete ``context_assembler``.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene ``ContextAssembly``, el contexto estructurado final
entregado a un agente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ContextAssembly:
    """The final assembled context delivered to an agent."""

    instructions: str = ""
    relevant_docs: list[dict[str, Any]] = field(default_factory=list)
    task_context: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-friendly)."""
        return {
            "instructions": self.instructions,
            "relevant_docs": self.relevant_docs,
            "task_context": self.task_context,
            "conversation_history": self.conversation_history,
            "metadata": self.metadata,
        }
