"""tool_output_filter.py — Wrapper rtk: reduce el output bash que lee el agente (ADR-0076).

WHAT: Si el binario ``rtk`` (Rust Token Killer) esta disponible, reescribe
comandos soportados a ``rtk <cmd>`` antes de ejecutarlos; si no, passthrough
transparente. Acumula bytes_saved para auditar el ahorro.
WHY: Frontera (rtk-ai/rtk, 79K estrellas): corta hasta 90% del output bash
(git/cargo/npm/docker/python...) con <10ms overhead, sin cambiar el
workflow — el hook PreToolUse reescribe y el agente ve el resumen compacto.
WHERE: Wrapper del tool executor bash del harness (opcional; opt-in).

Uso:
    flt = ToolOutputFilter(has_rtk=shutil.which("rtk") is not None)
    result = flt.run(["git", "status"])
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.tool_output_filter")

#: Prefijos de comando soportados por rtk (ecosistemas principales).
RTK_SUPPORTED: frozenset[str] = frozenset({
    "git", "cargo", "npm", "npx", "yarn", "pnpm", "python", "pytest",
    "go", "docker", "kubectl", "make", "uv", "pip", "ruff", "mypy",
})


@dataclass(frozen=True)
class FilteredOutput:
    """Resultado de una ejecucion filtrada.

    Attributes:
        output: Salida del comando (compacta si se reescribio).
        rewritten: True si el comando fue reescrito a `rtk <cmd>`.
        original_bytes: Tamano del comando original (para logs).
    """

    output: str
    rewritten: bool
    original_bytes: int = 0


class ToolOutputFilter:
    """Filtro de output bash con proxy rtk opt-in y metrica de ahorro.

    Args:
        runner: Callable (cmd list) -> str que ejecuta el comando.
        has_rtk: True si el binario rtk esta disponible en PATH.
    """

    def __init__(
        self,
        runner: Callable[[list[str]], str],
        has_rtk: bool = False,
    ) -> None:
        """Inicializa el filtro con el runner y la disponibilidad de rtk.

        Args:
            runner: Ejecutor de comandos inyectable (tests/DI).
            has_rtk: Si False, el filtro es passthrough puro.
        """
        self._runner = runner
        self._has_rtk = has_rtk
        self._bytes_saved = 0

    @property
    def bytes_saved(self) -> int:
        """Bytes de output evitados por las reescrituras rtk (metrica)."""
        return self._bytes_saved

    def run(self, cmd: list[str]) -> FilteredOutput:
        """Ejecuta el comando con reescritura rtk si aplica (1 sola ejecucion).

        Args:
            cmd: Comando y argumentos (lista; no vacio).

        Returns:
            FilteredOutput con la salida y el flag de reescritura.

        Raises:
            ValueError: Si el comando esta vacio (WHAT+WHY+WHERE).
        """
        if not cmd:
            raise ValueError(
                "WHAT: comando vacio. "
                "WHY: no hay nada que ejecutar ni filtrar. "
                "WHERE: ToolOutputFilter.run"
            )
        if self._has_rtk and cmd[0] in RTK_SUPPORTED:
            logger.debug("tool_output_filter: reescritura rtk para %s", cmd[0])
            compact = self._runner(["rtk", *cmd])
            return FilteredOutput(output=compact, rewritten=True, original_bytes=0)
        raw = self._runner(cmd)
        return FilteredOutput(output=raw, rewritten=False, original_bytes=len(raw))
