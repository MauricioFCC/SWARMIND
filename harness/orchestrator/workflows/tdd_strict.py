"""
tdd_strict.py - Workflow TDD estricto (ADR-0033): Spec-First, Code-Second.

El humano aprueba especificaciones; los tests son la ley y el codigo generado
por el agente es un detalle desechable. El DAG de 3 niveles bloquea la
escritura en src/ hasta que los tests sean auditados y aprobados:

    NIVEL 0 (Spec):      scientist define invariantes + tests PBT; guardian
                         audita exhaustividad y casos borde. Fase RED.
    NIVEL 1 (Green):     builder implementa hasta que los tests pasen;
                         guardian ejecuta mutation testing. Fase GREEN.
    NIVEL 2 (Confianza): coordinator genera el Test Confidence Report sin
                         mostrar codigo.

Uso:
    from harness.orchestrator.workflows.tdd_strict import (
        TDDGate, TDDPhase, build_tdd_dag, TestConfidenceReport,
    )
    ok, mensaje = TDDGate().validate_phase(TDDPhase.RED, False, True)
    print(build_tdd_dag())
    print(TestConfidenceReport(142, 142, 5000, 88.5, 12, 96.2, 4).render())
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# TDDPhase: fases del ciclo y sus reglas de oro (SurePrompts)
# ---------------------------------------------------------------------------


class TDDPhase(Enum):
    """Fases del ciclo TDD estricto con su prohibicion de oro asociada."""

    RED = ("RED", "PROHIBIDO implementar; el único trabajo es el test que falla correctamente")
    GREEN = ("GREEN", "PROHIBIDO tocar el test; solo implementación mínima para pasar")
    REFACTOR = ("REFACTOR", "PROHIBIDO cambiar comportamiento; solo mejorar la cualidad nombrada")

    def __init__(self, code: str, prohibition: str) -> None:
        """Inicializa el miembro del enum con su prohibicion de oro.

        Args:
            code: Identificador corto de la fase (p.ej. "RED").
            prohibition: Regla de oro que nadie puede violar en la fase.
        """
        self.code: str = code
        self.prohibition: str = prohibition


# ---------------------------------------------------------------------------
# Estructura del DAG
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TDDLevel:
    """Nivel del DAG TDD estricto: agentes, objetivo, fase y prohibicion.

    Attributes:
        level: Numero del nivel (0, 1, 2).
        name: Nombre del nivel ("Spec", "Green", "Confianza").
        phase: Fase TDD aplicada en el nivel (None en Confianza, sin codigo).
        agents: Agentes que operan en el nivel.
        objective: Trabajo que el nivel debe producir.
        prohibition: Regla de oro vigente en el nivel.
    """

    level: int
    name: str
    phase: TDDPhase | None
    agents: tuple[str, ...]
    objective: str
    prohibition: str


_DEFAULT_LEVELS: tuple[TDDLevel, ...] = (
    TDDLevel(
        level=0,
        name="Spec",
        phase=TDDPhase.RED,
        agents=("scientist", "guardian"),
        objective=(
            "scientist define invariantes y tests PBT; guardian audita "
            "exhaustividad y casos borde."
        ),
        prohibition=TDDPhase.RED.prohibition,
    ),
    TDDLevel(
        level=1,
        name="Green",
        phase=TDDPhase.GREEN,
        agents=("builder", "guardian"),
        objective=(
            "builder implementa hasta que los tests pasen; guardian ejecuta "
            "mutation testing."
        ),
        prohibition=TDDPhase.GREEN.prohibition,
    ),
    TDDLevel(
        level=2,
        name="Confianza",
        phase=None,
        agents=("coordinator",),
        objective="coordinator genera Test Confidence Report sin mostrar codigo.",
        prohibition="PROHIBIDO mostrar codigo fuente en el reporte de confianza.",
    ),
)


@dataclass(frozen=True)
class TDDStrictDAG:
    """DAG TDD estricto de 3 niveles (ADR-0033) y su validacion de estructura.

    Attributes:
        name: Nombre canonico del workflow ("tdd_strict").
        levels: Tupla de niveles ordenados (Spec, Green, Confianza).
    """

    name: str = "tdd_strict"
    levels: tuple[TDDLevel, ...] = _DEFAULT_LEVELS

    def validate(self) -> tuple[bool, str]:
        """Valida que la estructura del DAG es la canonica del ADR-0033.

        Returns:
            Tupla (valido, mensaje) donde valido es True si el DAG tiene
            exactamente 3 niveles con nombre, fases y agentes correctos.
        """
        if self.name != "tdd_strict":
            return False, (
                "WHAT: El DAG no se llama 'tdd_strict'. "
                f"WHY: El workflow exige name='tdd_strict' (obtuvo {self.name!r}). "
                "WHERE: TDDStrictDAG.validate() en harness/orchestrator/workflows/tdd_strict.py."
            )
        if len(self.levels) != 3:
            return False, (
                "WHAT: El DAG no tiene los 3 niveles esperados. "
                f"WHY: ADR-0033 define Spec, Green y Confianza (obtuvo {len(self.levels)}). "
                "WHERE: TDDStrictDAG.validate() en harness/orchestrator/workflows/tdd_strict.py."
            )
        for index, level in enumerate(self.levels):
            canonical = _DEFAULT_LEVELS[index]
            if (level.level, level.name, level.agents, level.phase) != (
                canonical.level,
                canonical.name,
                canonical.agents,
                canonical.phase,
            ):
                return False, (
                    f"WHAT: El nivel {index} no coincide con la estructura canonica. "
                    f"WHY: Se esperaba nivel={canonical.level}, nombre={canonical.name!r}, "
                    f"agentes={canonical.agents}, fase={canonical.phase} "
                    f"(obtuvo nivel={level.level}, nombre={level.name!r}, "
                    f"agentes={level.agents}, fase={level.phase}). "
                    "WHERE: TDDStrictDAG.validate() en harness/orchestrator/workflows/tdd_strict.py."
                )
        return True, (
            "WHAT: El DAG tdd_strict es estructuralmente valido. "
            "WHY: Los 3 niveles cumplen nombre, fases y agentes del ADR-0033. "
            "WHERE: TDDStrictDAG.validate() en harness/orchestrator/workflows/tdd_strict.py."
        )


def build_tdd_dag() -> dict[str, Any]:
    """Construye el DAG TDD estricto completo en formato dict.

    Returns:
        Dict con la clave "name" y la lista "levels", donde cada nivel
        incluye level, name, phase (nombre de TDDPhase o None), agents,
        objective y prohibition.
    """
    dag = TDDStrictDAG()
    return {
        "name": dag.name,
        "levels": [
            {
                "level": level.level,
                "name": level.name,
                "phase": level.phase.name if level.phase is not None else None,
                "agents": list(level.agents),
                "objective": level.objective,
                "prohibition": level.prohibition,
            }
            for level in dag.levels
        ],
    }


# ---------------------------------------------------------------------------
# Test Confidence Report (NIVEL 2, sin mostrar codigo)
# ---------------------------------------------------------------------------


def _fmt_pct(value: float) -> str:
    """Formatea un porcentaje sin decimales innecesarios.

    Args:
        value: Porcentaje a formatear (p.ej. 88.5 o 100.0).

    Returns:
        Cadena con el porcentaje: "88.5" o "100".
    """
    return f"{value:g}"


@dataclass(frozen=True)
class TestConfidenceReport:
    """Reporte de confianza del nivel Confianza (coordinator, sin codigo).

    Attributes:
        tests_passed: Tests unitarios aprobados.
        tests_total: Total de tests unitarios.
        pbt_generations: Generaciones ejecutadas por property-based testing.
        pbt_failures: Fallos detectados por PBT (0 si ninguno).
        mutation_score: Mutation score en porcentaje (0..100).
        surviving_mutants: Mutantes supervivientes aceptados como riesgo.
        branch_coverage: Cobertura de ramas logicas en porcentaje.
        sandbox_iterations: Ciclos ejecutados en el SandboxLoop.
        sandbox_duration_seconds: Duracion del ciclo autonomo en segundos.
        files_modified: Archivos modificados en src/ (nunca se muestran rutas).
    """

    tests_passed: int
    tests_total: int
    pbt_generations: int
    mutation_score: float
    surviving_mutants: int
    branch_coverage: float
    sandbox_iterations: int
    sandbox_duration_seconds: float = 192.0
    files_modified: tuple[str, ...] = ()
    pbt_failures: int = 0

    # Evita que pytest intente recolectar la clase como suite de tests.
    __test__ = False

    @property
    def pass_rate(self) -> float:
        """Calcula la tasa de aprobacion de tests en porcentaje.

        Returns:
            Porcentaje de tests aprobados (0..100).

        Raises:
            ValueError: Si tests_total es menor o igual a 0.
        """
        if self.tests_total <= 0:
            raise ValueError(
                "WHAT: No se puede calcular pass rate con tests_total <= 0. "
                f"WHY: tests_total={self.tests_total} invalida la division. "
                "WHERE: TestConfidenceReport.pass_rate en harness/orchestrator/workflows/tdd_strict.py."
            )
        return self.tests_passed / self.tests_total * 100.0

    @property
    def mutation_verdict(self) -> str:
        """Veredicto de robustez segun el mutation score.

        Returns:
            "Robusto" si mutation_score >= 85, si no "Requiere refuerzo".
        """
        return "Robusto" if self.mutation_score >= 85.0 else "Requiere refuerzo"

    def _render_pbt(self) -> str:
        """Renderiza la linea de Property-Based Testing del reporte.

        Returns:
            Linea con generaciones formateadas con separador de miles y el
            estado de fallos (sin fallos, 1 fallo o N fallos).
        """
        generations = f"{self.pbt_generations:,}"
        if self.pbt_failures == 0:
            return f"   • Property-Based Testing (PBT): {generations} generaciones sin fallos."
        noun = "fallo" if self.pbt_failures == 1 else "fallos"
        verb = "detectado" if self.pbt_failures == 1 else "detectados"
        return (
            f"   • Property-Based Testing (PBT): {generations} generaciones "
            f"con {self.pbt_failures} {noun} {verb}."
        )

    def render(self) -> str:
        """Genera el Test Confidence Report en el formato canonico del ADR-0033.

        El reporte NO muestra codigo fuente: solo metricas agregadas y el
        conteo de archivos modificados en src/.

        Returns:
            Texto del reporte con la estructura exacta del ADR-0033.
        """
        minutes, seconds = divmod(int(self.sandbox_duration_seconds), 60)
        return "\n".join(
            [
                "✅ ESPECIFICACIÓN APROBADA (Fuente Única de Verdad)",
                "📊 Métricas de Confianza:",
                (
                    f"   • Tests Unitarios: {self.tests_passed}/{self.tests_total} "
                    f"Passing ({_fmt_pct(self.pass_rate)}%)"
                ),
                self._render_pbt(),
                (
                    f"   • Mutation Score: {_fmt_pct(self.mutation_score)}% "
                    f"({self.mutation_verdict}, {self.surviving_mutants} mutantes "
                    "supervivientes aceptados como riesgo conocido)."
                ),
                f"   • Cobertura de Ramas Lógicas: {_fmt_pct(self.branch_coverage)}%",
                (
                    f"⏱️ Ciclo Autónomo: {self.sandbox_iterations} iteraciones "
                    f"en el SandboxLoop ({minutes} min {seconds} seg)."
                ),
                (
                    f"🛡️ Archivos modificados: {len(self.files_modified)} en `src/` "
                    "(Ocultos. Usa `!show code` solo si es estrictamente necesario para debug)."
                ),
            ]
        )


# ---------------------------------------------------------------------------
# TDDGate: validacion determinista por fase
# ---------------------------------------------------------------------------

_RED_FAIL_MSG = (
    "WHAT: El gate bloqueo la fase RED porque se detectaron cambios en src/ "
    "(src_files_modified=True). "
    "WHY: En RED esta PROHIBIDO implementar (regla de oro ADR-0033); el unico "
    "trabajo permitido es escribir el test que falla correctamente. "
    "WHERE: TDDGate.validate_phase() en harness/orchestrator/workflows/tdd_strict.py."
)

_GREEN_FAIL_MSG = (
    "WHAT: El gate bloqueo la fase GREEN porque test_files_modified=True. "
    "WHY: En GREEN esta PROHIBIDO tocar el test; el builder solo escribe "
    "implementacion minima en src/ hasta que los tests pasen. "
    "WHERE: TDDGate.validate_phase() en harness/orchestrator/workflows/tdd_strict.py."
)

_REFACTOR_FAIL_MSG = (
    "WHAT: El gate bloqueo la fase REFACTOR porque test_files_modified=True. "
    "WHY: En REFACTOR esta PROHIBIDO cambiar tests o comportamiento; solo se "
    "mejora la cualidad nombrada. "
    "WHERE: TDDGate.validate_phase() en harness/orchestrator/workflows/tdd_strict.py."
)

_OK_MSG = (
    "WHAT: La fase cumple las reglas de oro del TDD estricto. "
    "WHY: Ninguna prohibicion de la fase fue violada. "
    "WHERE: TDDGate.validate_phase() en harness/orchestrator/workflows/tdd_strict.py."
)


class TDDGate:
    """Validacion determinista de fases: bloquea violaciones de las reglas de oro."""

    def validate_phase(
        self,
        phase: TDDPhase,
        test_files_modified: bool,
        src_files_modified: bool,
    ) -> tuple[bool, str]:
        """Valida que una fase no viole su prohibicion de oro.

        Args:
            phase: Fase TDD a validar (RED, GREEN o REFACTOR).
            test_files_modified: True si se modificaron archivos de test.
            src_files_modified: True si se modificaron archivos en src/.

        Returns:
            Tupla (valido, mensaje): valido es False si la fase viola su
            prohibicion, con mensaje WHAT+WHY+WHERE explicando el bloqueo.
        """
        if phase is TDDPhase.RED and src_files_modified:
            return False, _RED_FAIL_MSG
        if phase is TDDPhase.GREEN and test_files_modified:
            return False, _GREEN_FAIL_MSG
        if phase is TDDPhase.REFACTOR and test_files_modified:
            return False, _REFACTOR_FAIL_MSG
        return True, _OK_MSG
