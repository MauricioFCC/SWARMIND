"""read_guard.py — Shunt de lecturas grandes a artifacts (ADR-0088, Spotify).

WHAT: Topa lecturas a max_chars; lo que excede va a ArtifactStore y al
contexto solo entra preview + handle (recuperable por offset).
WHY: Spotify+Claude: 90% de tokens era MOVER contexto, no pensar; el
plugin `shunt` bloquea lecturas grandes -> workers baratos, frontier
solo para reasoning. No mover contexto que no se va a razonar.
WHERE: Toda lectura de archivo/log del harness antes del contexto.

Uso:
    guard = ReadGuard()
    out = guard.read(big_text)  # out.inline + out.handle si trunco
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from harness.memory_rag.artifact_store import ArtifactStore

logger = logging.getLogger("harness.orchestrator.read_guard")

#: Tope default de lectura inline (chars).
DEFAULT_MAX_CHARS = 8000


@dataclass(frozen=True)
class GuardedRead:
    """Resultado de una lectura con shunt.

    Attributes:
        inline: Texto para el contexto (completo o preview+handle).
        truncated: True si se derivo a artifact.
        handle: Handle del artifact ("" si no trunco).
    """

    inline: str
    truncated: bool
    handle: str = ""


class ReadGuard:
    """Guard de lecturas con spill a artifacts.

    Args:
        max_chars: Tope inline (debe ser > 0).
        store: ArtifactStore inyectable (tests).
    """

    def __init__(
        self, max_chars: int = DEFAULT_MAX_CHARS, store: ArtifactStore | None = None
    ) -> None:
        """Inicializa el guard validando el tope.

        Args:
            max_chars: Maximo de chars inline.
            store: Store para el spill.

        Raises:
            ValueError: Si max_chars no es positivo (WHAT+WHY+WHERE).
        """
        if max_chars <= 0:
            raise ValueError(
                f"WHAT: max_chars invalido: {max_chars}. "
                "WHY: el tope debe ser positivo para acotar lecturas. "
                "WHERE: ReadGuard.__init__"
            )
        self._max_chars = max_chars
        self._store = store or ArtifactStore()

    def read(self, content: str) -> GuardedRead:
        """Lee con shunt: chico pasa, grande va a artifact.

        Args:
            content: Contenido a leer.

        Returns:
            GuardedRead con inline y handle si trunco.
        """
        if len(content) <= self._max_chars:
            return GuardedRead(inline=content, truncated=False)
        evicted = self._store.evict(content, force=True)
        logger.info(
            "read_guard: shunt de %d chars -> handle=%s", len(content), evicted.handle
        )
        return GuardedRead(
            inline=evicted.inline, truncated=True, handle=evicted.handle
        )

    def retrieve(self, handle: str, offset: int = 0) -> str:
        """Recupera el contenido completo desde el handle.

        Args:
            handle: Handle del artifact.
            offset: Linea inicial (0-based).

        Returns:
            Contenido desde offset.
        """
        return self._store.retrieve(handle, offset)
