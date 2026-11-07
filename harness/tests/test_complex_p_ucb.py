"""Contrato del P-UCB sobre familias de sketches (ciclo 11.17 - AlphaProof Nexus).

WHAT: verifica ``harness/complex_problems/p_ucb.py`` contra la frontera:

- **AlphaProof Nexus** (arXiv 2605.22763): P-UCB sobre poblacion de sketches
  — Upper Confidence Bound sobre familias con fitness binario (verificado /
  no verificado), garantizando cobertura inicial (cada familia se prueba al
  menos una vez) antes de explotar las de mayor tasa de exito.

WHY: sin exploracion garantizada, la busqueda se congela en la primera
familia que da un acierto temprano (sesgo de arranque); con UCB puro
deterministico (empate -> primera familia en orden), el proceso es
reproducible sin rng.

WHERE: ``harness/complex_problems/p_ucb.py``.
"""

from __future__ import annotations

import math

import pytest

from harness.complex_problems.p_ucb import DEFAULT_EXPLORATION, PopulationUCB


class TestInit:
    """Validacion de la poblacion de familias."""

    def test_familias_vacias_se_rechazan(self) -> None:
        with pytest.raises(ValueError, match="familias"):
            PopulationUCB(arms=())

    def test_familia_duplicada_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="duplicada"):
            PopulationUCB(arms=("a", "a"))

    def test_exploracion_no_positiva_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="exploracion"):
            PopulationUCB(arms=("a",), exploration=0.0)

    def test_exploracion_por_defecto_es_sqrt2(self) -> None:
        assert DEFAULT_EXPLORATION == math.sqrt(2.0)

    def test_exploracion_fraccional_se_acepta(self) -> None:
        """Cualquier exploration > 0 es valida, tambien <= 1 (umbral estricto)."""
        population = PopulationUCB(arms=("a",), exploration=0.5)

        assert population.exploration == 0.5


class TestSelect:
    """Seleccion determinista con cobertura garantizada."""

    def test_sin_tiradas_devuelve_la_primera_familia(self) -> None:
        population = PopulationUCB(arms=("b", "a"))

        assert population.select() == "b", "orden de declaracion, sin azar"

    def test_cobertura_garantiza_todas_las_familias(self) -> None:
        """Ninguna familia queda sin probarse: visita cada una antes de repetir."""
        population = PopulationUCB(arms=("a", "b", "c"))

        visited: list[str] = []
        for _ in range(3):
            choice = population.select()
            visited.append(choice)
            population.record(choice, won=False)

        assert visited == ["a", "b", "c"]

    def test_familia_nunca_probada_gana_por_bonus(self) -> None:
        population = PopulationUCB(arms=("a", "b"))
        population.record("a", won=True)

        assert population.select() == "b", "el bonus de exploracion la rescata"

    def test_explota_la_familia_de_mayor_tasa(self) -> None:
        population = PopulationUCB(arms=("a", "b"))
        for arm, won in (("a", True), ("a", True), ("b", False)):
            population.record(arm, won)

        assert population.select() == "a"

    def test_empate_de_uct_elige_la_primera_en_orden(self) -> None:
        population = PopulationUCB(arms=("z", "a"))
        population.record("z", won=True)
        population.record("a", won=True)

        assert population.select() == "z", "determinismo sin rng"

    def test_determinismo_misma_historia_misma_sucesion(self) -> None:
        def play() -> list[str]:
            population = PopulationUCB(arms=("a", "b", "c"))
            picks = []
            for won in (True, False, True, False):
                choice = population.select()
                picks.append(choice)
                population.record(choice, won)
            return picks

        assert play() == play()


class TestRecord:
    """Registro de fitness binario."""

    def test_tiradas_y_victorias_se_acumulan(self) -> None:
        population = PopulationUCB(arms=("a",))
        population.record("a", won=True)
        population.record("a", won=False)

        assert population.pulls["a"] == 2
        assert population.wins["a"] == 1
        assert population.total_pulls == 2

    def test_familia_desconocida_es_keyerror(self) -> None:
        population = PopulationUCB(arms=("a",))

        with pytest.raises(KeyError):
            population.record("fantasma", won=True)

    def test_pulls_es_inmutable_desde_fuera(self) -> None:
        population = PopulationUCB(arms=("a",))

        with pytest.raises(TypeError):
            population.pulls["a"] = 99  # type: ignore[index]
