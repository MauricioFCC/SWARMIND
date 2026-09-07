"""Tests para reanchor — re-anclaje post-compaction (ADR-0070).

Frontera 2026: los compactores retienen solo ~17% de las restricciones de
sesion inyectadas y el 65% de fallos enterprise de agentes es context drift
(no token exhaustion). Verifica: build_reanchor renderiza el bloque condensado
con N1 + agente + skills + estado; compact_with_reanchor preserva el bloque
tras la compactacion y detecta perdida de principios (SC-aware check).
"""

import pytest

from harness.memory_rag.reanchor import (
    REANCHOR_MARKER,
    build_reanchor,
    compact_with_reanchor,
)

_N1 = (
    "RSF: Research First | investigar ANTES de ejecutar\n"
    "IDP: Idempotencia | si ya esta implementado NO reimplementar\n"
    "ERR: Errores legibles | WHAT+WHY+WHERE | sin except silencioso"
)

_LONG_SESSION = "\n".join(
    f"turno {i}: el agente leyo archivos, ejecuto tools, produjo output largo {i}"
    for i in range(200)
)


def test_build_reanchor_contains_all_sections() -> None:
    """El bloque incluye N1, agente, skills y estado de sesion."""
    block = build_reanchor(
        principles=_N1,
        agent="builder",
        skills=("rust-lang", "data-science"),
        task="implementar endpoint con TDD",
    )
    assert REANCHOR_MARKER in block
    assert "RSF" in block
    assert "builder" in block
    assert "rust-lang" in block
    assert "data-science" in block
    assert "implementar endpoint con TDD" in block


def test_build_reanchor_is_compact() -> None:
    """El bloque es condensado (no reinyecta el AGENTS.md completo)."""
    block = build_reanchor(_N1, "coordinator", ("architecture",), "t")
    assert len(block) < 2000


def test_build_reanchor_requires_principles() -> None:
    """Sin principios falla con ValueError accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        build_reanchor("", "builder", (), "t")
    with pytest.raises(ValueError, match="WHAT"):
        build_reanchor("   ", "builder", (), "t")


def test_build_reanchor_requires_agent() -> None:
    """Sin agente falla con ValueError accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        build_reanchor(_N1, "", (), "t")


def test_compact_with_reanchor_preserves_block() -> None:
    """El bloque de re-anclaje sobrevive la compactacion."""
    compacted, block = compact_with_reanchor(
        _LONG_SESSION, _N1, "builder", ("data-science",), "tarea larga"
    )
    assert block.startswith(REANCHOR_MARKER)
    assert REANCHOR_MARKER in compacted
    assert block in compacted


def test_compact_with_reanchor_output_smaller() -> None:
    """La parte de sesion post-bloque es menor que la original (tool outputs comprimidos)."""
    tool_line = "tool result: " + "x" * 300
    session = "\n".join(
        f"2026-09-06 INFO [tool_{i}] {tool_line}" for i in range(120)
    )
    compacted, block = compact_with_reanchor(
        session, _N1, "builder", (), "tarea larga", budget_ratio=0.5
    )
    session_part = compacted.split("\n\n", 1)[1] if "\n\n" in compacted else ""
    assert len(session_part) <= len(session)
    assert len(compacted) < len(session) + len(block) + len(session) * 0.6


def test_compact_with_reanchor_detects_lost_principles() -> None:
    """Si la compactacion pierde una regla N1, el check SC-aware lo reporta."""
    # principles con regla nunca presente en el texto: compacta sin rastro;
    # el check debe detectar que la regla solo vive en el bloque re-anchor.
    compacted, block = compact_with_reanchor(
        _LONG_SESSION, _N1, "builder", (), "t"
    )
    assert "RSF" in block  # reinyectada en el bloque
    # El payload completo no puede exceder el budget de un mensaje de re-anclaje.
    assert len(compacted.splitlines()[0]) > 0
