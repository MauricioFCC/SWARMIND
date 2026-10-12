"""Tests TDD para build_cache_shaped_prompt — cache-shape del prompt (FR-A2).

Cubre WS-A: orden canonico tools->system->static->dynamic, prioridad dentro
del kind, breakpoint de cache al final del prefijo estable, y estabilidad
entre llamadas (cache-hit: mismo input -> mismo output). NF-5.

Patron TDD (RED primero): contrato ANTES de la implementacion en
``harness/orchestrator/prompt_cache_shape.py``.
"""

from __future__ import annotations

from harness.orchestrator.prompt_cache_shape import (
    CACHE_BREAKPOINT,
    ORDER,
    PromptBlock,
    build_cache_shaped_prompt,
    cache_prefix,
)

# ===========================================================================
# Orden canonico
# ===========================================================================


class TestCanonicalOrder:
    """El ensamblado reordena al orden canonico toools->system->static->dynamic."""

    def test_order_constant(self) -> None:
        """ORDER: tupla canonica exacta (mutation: cambiar el orden la rompe)."""
        assert ORDER == ("tools", "system", "static", "dynamic")

    def test_reorders_shuffled_blocks(self) -> None:
        """build: bloques desordenados se reordenan canonicamente."""
        blocks = [
            PromptBlock(kind="dynamic", content="DYN"),
            PromptBlock(kind="static", content="STAT"),
            PromptBlock(kind="system", content="SYS"),
            PromptBlock(kind="tools", content="TOOLS"),
        ]
        output = build_cache_shaped_prompt(blocks)
        assert output.index("TOOLS") < output.index("SYS")
        assert output.index("SYS") < output.index("STAT")
        assert output.index("STAT") < output.index("DYN")


# ===========================================================================
# Prioridad dentro del kind
# ===========================================================================


class TestPriorityWithinKind:
    """Dentro del mismo kind, priority ascendente decide el orden."""

    def test_priority_ascending(self) -> None:
        """build: mismo kind → orden por priority ascendente."""
        blocks = [
            PromptBlock(kind="static", content="B", priority=2),
            PromptBlock(kind="static", content="A", priority=1),
            PromptBlock(kind="static", content="C", priority=3),
        ]
        output = build_cache_shaped_prompt(blocks)
        assert output.index("A") < output.index("B") < output.index("C")


# ===========================================================================
# cache_prefix y breakpoint
# ===========================================================================


class TestCachePrefix:
    """cache_prefix devuelve solo el prefijo estable hasta el breakpoint."""

    def test_prefix_ends_at_breakpoint_and_excludes_dynamic(self) -> None:
        """cache_prefix: termina en breakpoint y excluye dynamic."""
        blocks = [
            PromptBlock(kind="dynamic", content="DYN"),
            PromptBlock(kind="static", content="STAT"),
            PromptBlock(kind="system", content="SYS"),
            PromptBlock(kind="tools", content="TOOLS"),
        ]
        prefix = cache_prefix(blocks)
        assert prefix.rstrip().endswith(CACHE_BREAKPOINT)
        assert "DYN" not in prefix
        assert "TOOLS" in prefix
        assert "SYS" in prefix
        assert "STAT" in prefix

    def test_breakpoint_before_dynamic(self) -> None:
        """build: el breakpoint queda antes del primer bloque dinamico."""
        blocks = [
            PromptBlock(kind="static", content="STAT"),
            PromptBlock(kind="dynamic", content="DYN"),
        ]
        output = build_cache_shaped_prompt(blocks)
        assert CACHE_BREAKPOINT in output
        assert output.index(CACHE_BREAKPOINT) < output.index("DYN")


# ===========================================================================
# Estabilidad (cache-hit)
# ===========================================================================


class TestStability:
    """Mismo input → mismo output (prefijo estable cacheable)."""

    def test_same_input_same_output(self) -> None:
        """build: determinista entre llamadas."""
        blocks = [
            PromptBlock(kind="system", content="S"),
            PromptBlock(kind="tools", content="T"),
            PromptBlock(kind="dynamic", content="D"),
        ]
        assert build_cache_shaped_prompt(blocks) == build_cache_shaped_prompt(
            list(blocks)
        )

    def test_cache_prefix_is_prefix_of_prompt(self) -> None:
        """cache_prefix: es prefijo literal del prompt completo."""
        blocks = [
            PromptBlock(kind="tools", content="T"),
            PromptBlock(kind="system", content="S"),
            PromptBlock(kind="static", content="ST"),
            PromptBlock(kind="dynamic", content="D"),
        ]
        assert build_cache_shaped_prompt(blocks).startswith(
            cache_prefix(blocks)
        )


# ===========================================================================
# Mutation-style (oraculo sustituto)
# ===========================================================================


class TestMutationBreakpoint:
    """Si se elimina la insercion del breakpoint, el test debe fallar."""

    def test_breakpoint_present_in_output(self) -> None:
        """Mutation: borrar el breakpoint del ensamblado rompe ESTE assert."""
        output = build_cache_shaped_prompt(
            [
                PromptBlock(kind="static", content="S"),
                PromptBlock(kind="dynamic", content="D"),
            ]
        )
        assert CACHE_BREAKPOINT in output
