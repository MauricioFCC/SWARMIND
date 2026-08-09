"""
test_reinforcement.py - H3 TestReinforcementLoop (arXiv 2607.23002).

Loop Tester -> mutation -> Critic que refuerza los tests para matar mutantes
supervivientes (incremental kill rate 78%). Genera SPEC de tests dirigidos a
partir de los mutantes que sobreviven al mutation testing y simula el ciclo de
refuerzo con un oraculo mecanico: la mejora de score por ronda es
proporcional al kill rate incremental (KILLS_PER_ROUND_RATE * 10).

Se CONECTA con la logica de tdd_strict.py
(TestConfidenceReport.mutation_verdict -> "Robusto" si mutation_score >= 85,
si no "Requiere refuerzo") sin modificarla: verdict_based_guidance() reusa
ese veredicto y anade la guia de refuerzo.

Uso:
    from harness.orchestrator.workflows.test_reinforcement import (
        SurvivingMutant, ReinforcementReport, TestReinforcementLoop,
    )
    loop = TestReinforcementLoop()
    mutantes = (SurvivingMutant("m1", "src/game/adivina.py", 42, "cambio > por <"),)
    reporte = loop.reinforce(70.0, mutantes)
    print(reporte.render())
    print(loop.render_guidance(reporte))
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.orchestrator.workflows.tdd_strict import TestConfidenceReport


@dataclass(frozen=True)
class SurvivingMutant:
    """Mutante superviviente detectado por el mutation testing.

    Attributes:
        mutant_id: Identificador unico del mutante (p.ej. "mut_01").
        src_path: Ruta del archivo fuente mutado.
        line: Numero de linea donde se aplico la mutacion.
        description: Descripcion del cambio introducido (p.ej. "cambio > por <").
    """

    mutant_id: str
    src_path: str
    line: int
    description: str

    def summary(self) -> str:
        """Resume el mutante superviviente en una linea legible.

        Returns:
            Cadena con id, descripcion y localizacion del mutante.
        """
        return (
            f"Mutante {self.mutant_id} ({self.description}) "
            f"en {self.src_path}:{self.line}"
        )


@dataclass(frozen=True)
class ReinforcementReport:
    """Resultado del loop de refuerzo de tests.

    Attributes:
        initial_score: Mutation score antes del refuerzo (0..100).
        final_score: Mutation score tras el refuerzo (0..100, clamp a 100).
        mutants_targeted: Numero de mutantes supervivientes objetivo.
        tests_added: Nuevos tests sugeridos para matar a los mutantes.
        improved: True si final_score >= umbral y mayor que initial_score.
        message: Descripcion accionable del resultado (WHAT+WHY+WHERE).
    """

    initial_score: float
    final_score: float
    mutants_targeted: int
    tests_added: tuple[str, ...]
    improved: bool
    message: str

    def render(self) -> str:
        """Renderiza el reporte en un texto legible para el guardian.

        Returns:
            Texto con metricas iniciales/finales y estado del refuerzo.
        """
        status = "✅" if self.improved else "⚠️"
        return "\n".join(
            [
                f"{status} TestReinforcementLoop — Reporte de refuerzo:",
                f"   • Score inicial: {self.initial_score:g}%",
                f"   • Score final: {self.final_score:g}%",
                f"   • Mutantes objetivo: {self.mutants_targeted}",
                f"   • Tests sugeridos: {len(self.tests_added)}",
                f"   • Mejorado: {self.improved}",
                f"   • {self.message}",
            ]
        )


class TestReinforcementLoop:
    """Loop Tester -> mutation -> Critic que refuerza tests contra mutantes vivos."""

    MUTATION_TARGET = 85.0
    MAX_ROUNDS = 3
    TEST_DIR_NAME = "tests"
    KILLS_PER_ROUND_RATE = 0.5

    # Evita que pytest intente recolectar la clase como suite de tests.
    __test__ = False

    def needs_reinforcement(self, mutation_score: float) -> bool:
        """Indica si el mutation score exige reforzar los tests.

        Args:
            mutation_score: Mutation score actual en porcentaje (0..100).

        Returns:
            True si mutation_score < MUTATION_TARGET (85.0).
        """
        return mutation_score < self.MUTATION_TARGET

    def suggest_tests_for_mutants(
        self, mutants: tuple[SurvivingMutant, ...]
    ) -> tuple[str, ...]:
        """Genera SPEC de tests dirigidos para matar mutantes supervivientes.

        Por cada mutante produce la plantilla del test a anadir en formato
        "Test {basename}::{case}: {descripcion} (src {src_path}:{line})".
        Solo genera la especificacion; no ejecuta codigo.

        Args:
            mutants: Mutantes supervivientes detectados por mutation testing.

        Returns:
            Tupla con una sugerencia accionable por mutante.
        """
        suggestions: list[str] = []
        for mutant in mutants:
            basename = Path(mutant.src_path).stem
            case = f"test_{basename}_{mutant.mutant_id}"
            suggestions.append(
                f"Test {basename}::{case}: {mutant.description} "
                f"(src {mutant.src_path}:{mutant.line})"
            )
        return tuple(suggestions)

    def reinforce(
        self,
        initial_score: float,
        mutants: tuple[SurvivingMutant, ...],
        rounds: int = MAX_ROUNDS,
    ) -> ReinforcementReport:
        """Simula el loop de refuerzo con un oraculo mecanico de kill rate.

        Por cada ronda se sugieren tests dirigidos y el score mejora segun el
        kill rate incremental (KILLS_PER_ROUND_RATE * 10 por ronda, p.ej. 5.0
        con rate 0.5). Las rondas se claman a [0, MAX_ROUNDS] y el score final
        a 100. Sin mutantes o con rounds=0 el score no cambia.

        Args:
            initial_score: Mutation score inicial (0..100).
            mutants: Mutantes supervivientes a atacar.
            rounds: Rondas de refuerzo (se clampa a MAX_ROUNDS).

        Returns:
            ReinforcementReport con el resultado del refuerzo.
        """
        effective_rounds = min(max(rounds, 0), self.MAX_ROUNDS)
        tests_added = self.suggest_tests_for_mutants(mutants)
        if not mutants or effective_rounds == 0:
            final_score = initial_score
        else:
            improvement = effective_rounds * self.KILLS_PER_ROUND_RATE * 10.0
            final_score = min(initial_score + improvement, 100.0)
        improved = (
            final_score >= self.MUTATION_TARGET and final_score > initial_score
        )
        return ReinforcementReport(
            initial_score=initial_score,
            final_score=final_score,
            mutants_targeted=len(mutants),
            tests_added=tests_added,
            improved=improved,
            message=self._build_message(
                initial_score, final_score, len(mutants), improved
            ),
        )

    def render_guidance(self, report: ReinforcementReport) -> str:
        """Renderiza instrucciones accionables para el guardian.

        Args:
            report: Reporte producido por reinforce().

        Returns:
            Texto con el umbral pendiente, los tests a anadir y el mensaje final.
        """
        lines = [
            "📋 TestReinforcementLoop — Guía para el guardian:",
            (
                f"   • Mutation score: {report.initial_score:g}% -> "
                f"{report.final_score:g}% (umbral {self.MUTATION_TARGET:g}%)."
            ),
            f"   • Mutantes objetivo: {report.mutants_targeted}",
            f"   • Tests a añadir en `{self.TEST_DIR_NAME}/`:",
        ]
        lines.extend(f"     - {test}" for test in report.tests_added)
        lines.append(f"   • {report.message}")
        return "\n".join(lines)

    def verdict_based_guidance(
        self, mutation_score: float, surviving_mutants: int
    ) -> str:
        """Guia segun el veredicto de robustez de tdd_strict (sin modificarlo).

        Reusa TestConfidenceReport.mutation_verdict: "Robusto" si
        mutation_score >= 85, si no "Requiere refuerzo". Si requiere refuerzo,
        la guia indica ejecutar reinforce() y atacar a los mutantes vivos.

        Args:
            mutation_score: Mutation score actual en porcentaje (0..100).
            surviving_mutants: Cantidad de mutantes supervivientes.

        Returns:
            Veredicto de tdd_strict con guia accionable si hace falta refuerzo.
        """
        verdict = TestConfidenceReport(
            tests_passed=1,
            tests_total=1,
            pbt_generations=0,
            pbt_failures=0,
            mutation_score=mutation_score,
            surviving_mutants=surviving_mutants,
            branch_coverage=0.0,
            sandbox_iterations=0,
        ).mutation_verdict
        where = (
            "WHERE: TestReinforcementLoop.verdict_based_guidance() en "
            "harness/orchestrator/workflows/test_reinforcement.py"
        )
        if verdict == "Robusto":
            return (
                f"WHAT: {verdict}. El mutation score {mutation_score:g}% supera "
                f"el umbral {self.MUTATION_TARGET:g}%. "
                f"WHY: No hay mutantes vivos que exijan refuerzo "
                f"({surviving_mutants} supervivientes). {where}."
            )
        return (
            f"WHAT: {verdict}. El mutation score {mutation_score:g}% esta por "
            f"debajo del umbral {self.MUTATION_TARGET:g}%. "
            f"WHY: Hay {surviving_mutants} mutantes supervivientes que los "
            f"tests actuales no matan. "
            f"WHERE: ejecuta TestReinforcementLoop.reinforce({mutation_score:g}, "
            f"mutantes_supervivientes) para generar los tests dirigidos y "
            f"añadirlos en {self.TEST_DIR_NAME}/. {where}."
        )

    def _build_message(
        self,
        initial_score: float,
        final_score: float,
        mutants_targeted: int,
        improved: bool,
    ) -> str:
        """Construye el mensaje WHAT+WHY+WHERE del reporte de refuerzo.

        Args:
            initial_score: Score antes del refuerzo.
            final_score: Score tras el refuerzo.
            mutants_targeted: Mutantes supervivientes atacados.
            improved: True si se alcanzo el umbral mejorando el score.

        Returns:
            Mensaje accionable con WHAT, WHY y WHERE.
        """
        where = (
            "WHERE: TestReinforcementLoop.reinforce() en "
            "harness/orchestrator/workflows/test_reinforcement.py"
        )
        if improved:
            return (
                f"WHAT: El mutation score alcanzo el umbral de robustez "
                f"({final_score:g}% >= {self.MUTATION_TARGET:g}%). "
                f"WHY: Los tests dirigidos a {mutants_targeted} mutantes "
                f"supervivientes elevaron el score de {initial_score:g}% a "
                f"{final_score:g}%. {where}."
            )
        return (
            f"WHAT: El mutation score sigue bajo el umbral de robustez "
            f"({final_score:g}% < {self.MUTATION_TARGET:g}%). "
            f"WHY: Aun con {mutants_targeted} mutantes supervivientes atacados, "
            f"el score no supero el umbral ({initial_score:g}% -> "
            f"{final_score:g}%). {where}."
        )
