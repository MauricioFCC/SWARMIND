"""Contrato de la escalera de presupuesto de ataque (ciclo 11.17 - AlphaProof Nexus).

WHAT: verifica ``harness/complex_problems/budget.py`` contra la frontera:

- **AlphaProof Nexus** (arXiv 2605.22763, 9/353 Erdos abiertos): escalera de
  presupuesto — intentos con presupuesto creciente (más compute en los
  intentos tardios una vez la direccion se afino) + tope global de episodios
  (cap 3000 del paper).

WHY: sin escalera, el ataque gasta igual en intentos tempranos exploratorios
y tardios prometedores; sin tope global, un loop fallido consume compute
infinito (failure-spend sin registro).

WHERE: ``harness/complex_problems/budget.py``.
"""

from __future__ import annotations

import pytest

from harness.complex_problems.budget import (
    DEFAULT_EPISODE_CAP,
    AttackBudget,
    BudgetLadder,
)


class TestBudgetLadder:
    """Contrato de la escalera (rungs) valida y determinista."""

    def test_rungs_vacios_se_rechazan(self) -> None:
        with pytest.raises(ValueError, match="escalera"):
            BudgetLadder(rungs=())

    def test_rung_no_positivo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="positivo"):
            BudgetLadder(rungs=(2, 0, 5))

    def test_rungs_decrecientes_se_rechazan(self) -> None:
        """La escalera debe ser monotonamente creciente (mas compute al final)."""
        with pytest.raises(ValueError, match="creciente"):
            BudgetLadder(rungs=(5, 3, 9))

    def test_intenta_mas_alla_del_ultimo_rung_usa_el_ultimo(self) -> None:
        ladder = BudgetLadder(rungs=(1, 2, 4))

        assert ladder.allocate(0) == 1
        assert ladder.allocate(2) == 4
        assert ladder.allocate(99) == 4, "intentos tardios capados en el ultimo rung"

    def test_intento_negativo_se_rechaza(self) -> None:
        ladder = BudgetLadder(rungs=(1, 2))

        with pytest.raises(ValueError, match="negativo"):
            ladder.allocate(-1)

    def test_asignacion_determinista(self) -> None:
        a = BudgetLadder(rungs=(1, 3, 7))
        b = BudgetLadder(rungs=(1, 3, 7))

        assert tuple(a.allocate(i) for i in range(5)) == tuple(
            b.allocate(i) for i in range(5)
        )


class TestAttackBudget:
    """Contrato del gasto acumulado con tope global de episodios (Nexus)."""

    def test_consume_acota_al_restante(self) -> None:
        budget = AttackBudget(BudgetLadder(rungs=(2,)))

        budget.consume(1)

        assert budget.remaining == 1
        assert budget.spent == 1
        assert budget.exhausted is False

    def test_consumo_sobre_el_restante_es_error(self) -> None:
        budget = AttackBudget(BudgetLadder(rungs=(2,)))

        budget.consume(2)

        assert budget.exhausted is True
        with pytest.raises(ValueError, match="restante"):
            budget.consume(1)

    def test_costo_negativo_se_rechaza(self) -> None:
        budget = AttackBudget(BudgetLadder(rungs=(2,)))

        with pytest.raises(ValueError, match="negativo"):
            budget.consume(-1)

    def test_episode_cap_global_acota_los_intentos(self) -> None:
        """Nexus cap=3000: el tope es global, no por intento."""
        ladder = BudgetLadder(rungs=(10,))
        budget = AttackBudget(ladder, episode_cap=12)

        assert budget.start_attempt(0) == 10
        assert budget.start_attempt(1) == 2, "al tope solo queda el remanente"
        assert budget.start_attempt(2) == 0
        assert budget.exhausted is True

    def test_episode_cap_por_defecto_es_3000(self) -> None:
        assert DEFAULT_EPISODE_CAP == 3000

    def test_intentos_tardios_reciben_mas_presupuesto(self) -> None:
        budget = AttackBudget(BudgetLadder(rungs=(1, 4, 9)))

        first = budget.start_attempt(0)
        second = budget.start_attempt(1)

        assert first == 1
        assert second == 4
        assert second > first, "escalera creciente: mas compute al final"
