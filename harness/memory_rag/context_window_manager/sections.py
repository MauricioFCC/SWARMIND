"""Secciones de contexto para el paquete ``context_window_manager``.

Extraido mecanicamente de ``context_window_manager.py`` (regla AGR < 500
lineas). Contiene ``ContextSection``, la unidad atomica de la ventana
de contexto con presupuesto de tokens y truncado propio.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from harness.common import CHARS_PER_TOKEN

from .constants import PRIORITY_NORMAL
from .estimator import TokenEstimator

# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

@dataclass
class ContextSection:
    """A section of the context window."""
    name: str
    content: str
    priority: int = PRIORITY_NORMAL
    max_tokens: int = 1000
    frozen: bool = False
    compressed: bool = False
    _token_estimator: TokenEstimator | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def token_estimate(self) -> int:
        """Estima tokens usando el tokenizador real si esta disponible."""
        if self._token_estimator is not None:
            return self._token_estimator.count(self.content)
        return max(1, len(self.content) // int(CHARS_PER_TOKEN))

    @property
    def over_budget(self) -> bool:
        """Indica si la seccion excede su presupuesto de tokens."""
        return self.token_estimate > self.max_tokens

    def truncate_to_budget(self) -> bool:
        """Trunca contenido al presupuesto.

        Returns:
            True si se trunco algo.
        """
        if self.frozen or not self.over_budget:
            return False

        if self._token_estimator is not None:
            current_len = len(self.content)
            truncated = self._token_estimator.truncate_to_token_limit(
                self.content, self.max_tokens
            )
            margin = int(current_len * 0.1)
            last_para = truncated.rfind("\n\n")
            if last_para > len(truncated) - margin:
                truncated = truncated[:last_para]
            self.content = truncated + "\n\n[...truncated...]"
        else:
            max_chars = int(self.max_tokens * CHARS_PER_TOKEN)
            if len(self.content) > max_chars:
                truncated = self.content[:max_chars]
                last_para = truncated.rfind("\n\n")
                if last_para > max_chars // 2:
                    truncated = truncated[:last_para]
                self.content = truncated + "\n\n[...truncated...]"

        self.compressed = True
        return True
