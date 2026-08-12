"""Ventana de contexto para el paquete ``context_window_manager``.

Extraido mecanicamente de ``context_window_manager.py`` (regla AGR < 500
lineas). Contiene ``ContextWindow``, el contenedor de secciones con
presupuesto global y renderizado a prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import DEFAULT_BUDGETS, PRIORITY_NORMAL, SECTION_PRIORITIES
from .sections import ContextSection

# ---------------------------------------------------------------------------
# Context Window
# ---------------------------------------------------------------------------

@dataclass
class ContextWindow:
    """The full context window for a single LLM call."""
    sections: dict[str, ContextSection] = field(default_factory=dict)
    total_budget: int = 12000
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_section(
        self,
        name: str,
        content: str,
        priority: int | None = None,
        max_tokens: int | None = None,
        frozen: bool = False,
    ) -> ContextSection:
        """Add or update a section."""
        section = ContextSection(
            name=name,
            content=content,
            priority=priority or SECTION_PRIORITIES.get(name, PRIORITY_NORMAL),
            max_tokens=max_tokens or DEFAULT_BUDGETS.get(name, 1000),
            frozen=frozen,
        )
        self.sections[name] = section
        return section

    def get_section(self, name: str) -> ContextSection | None:
        """Obtiene una seccion por nombre."""
        return self.sections.get(name)

    def remove_section(self, name: str) -> bool:
        """Elimina una seccion por nombre."""
        return self.sections.pop(name, None) is not None

    @property
    def total_tokens(self) -> int:
        """Total de tokens en todas las secciones."""
        return sum(s.token_estimate for s in self.sections.values())

    @property
    def over_budget(self) -> bool:
        """Indica si la ventana excede el presupuesto."""
        return self.total_tokens > self.total_budget

    def to_prompt(self, format: str = "compact") -> str:
        """Render sections as a formatted prompt string.

        Args:
            format: 'compact' = single block, 'labeled' = with headers.

        Returns:
            Formatted prompt string.
        """
        if format == "labeled":
            parts = []
            for name, section in sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            ):
                if section.content:
                    header = name.replace("_", " ").title()
                    parts.append(f"=== {header} ===\n{section.content}")
            return "\n\n".join(parts)
        else:
            sections_in_order = sorted(
                self.sections.items(),
                key=lambda x: x[1].priority,
            )
            return "\n".join(s.content for _, s in sections_in_order if s.content)

    def to_dict(self) -> dict[str, Any]:
        """Serializa la ventana a diccionario (sin contenido completo)."""
        return {
            "total_budget": self.total_budget,
            "total_tokens": self.total_tokens,
            "over_budget": self.over_budget,
            "sections": {
                k: {
                    "name": v.name,
                    "tokens": v.token_estimate,
                    "priority": v.priority,
                    "max_tokens": v.max_tokens,
                    "frozen": v.frozen,
                    "compressed": v.compressed,
                    "over_budget": v.over_budget,
                }
                for k, v in self.sections.items()
            },
        }
