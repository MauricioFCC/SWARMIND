"""example_spec_module.py — Modulo demo para el ciclo SDD del skill atdd-spec.

Implementa la funcion ``spec_example_add`` que el test RED inicial
(``.opencode/skills/atdd-spec/tests/test_atdd_spec_example.py``) exige.
El skill atdd-spec demuestra asi el patron Spec->Test->Code: el test
falla primero (RED), el agente implementa (GREEN), y el contrato
``SKILL.spec.json`` documenta pre/postcondiciones.
"""

from __future__ import annotations


def spec_example_add(left: int, right: int) -> int:
    """Suma dos enteros (funcion demo del ciclo SDD).

    Args:
        left: Primer sumando.
        right: Segundo sumando.

    Returns:
        Suma de ``left`` y ``right``.
    """
    return left + right