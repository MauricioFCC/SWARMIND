"""test_atdd_spec_example.py — Demo del ciclo Spec->Test->Code (RED inicial).

Este test FALLA a proposito (Ley de Hierro ADR-0047: NO SKILL WITHOUT A
FAILING TEST FIRST). El agente usa el skill atdd-spec para implementar
``harness.context.example_spec_function`` hasta que este test pase.

Uso:
    uv run pytest .opencode/skills/atdd-spec/tests -q
"""

from __future__ import annotations

import pytest

from harness.context.example_spec_module import spec_example_add


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (1, 2, 3),
        (0, 0, 0),
        (-1, 1, 0),
        (100, 200, 300),
    ],
)
def test_spec_example_add_returns_sum(left: int, right: int, expected: int) -> None:
    """Verifica que la suma especificada devuelve el resultado correcto."""
    assert spec_example_add(left, right) == expected