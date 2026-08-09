"""
tdd_policy.py - TDDPolicyEngine (H1): autoridad TDD "model proposes, engine disposes".

El motor de politicas TDD es la autoridad que GARANTIZA que SWARMIND use TDD
estricto (test primero). Basado en arXiv 2604.26615 (TDD Governance) y el
TOP-10 TDD 2026: el modelo PROpone cambios y el motor DISPone (aprueba o
bloquea la emision de DONE) con reglas deterministas.

Todos los checks se ejecutan en orden y quedan registrados en
PolicyVerdict.gate_checks para trazabilidad:

    a. fase:        reusa TDDGate.validate_phase (RED sin src/, GREEN/REFACTOR
                    sin cambios en tests).
    b. test_first:  en GREEN/REFACTOR exige red_evidence=True (el test corrio
                    y fallo en RED antes de implementar).
    c. anti_gaming: si tests_hash_red y tests_hash_now estan presentes, deben
                    coincidir (los tests NO pueden cambiar entre RED y DONE).
    d. completitud: si tests_total > 0, exige tests_passed == tests_total.
    e. mutation:    si mutation_score > 0, exige >= MUTATION_MIN.
    f. branch:      si branch_coverage > 0, exige >= BRANCH_MIN.

Uso:
    from harness.orchestrator.workflows.tdd_policy import (
        TDDPolicyEngine, PolicyContext,
    )
    ctx = PolicyContext(task_id="t1", phase=TDDPhase.GREEN, ...)
    ok, message = TDDPolicyEngine().can_emit_done(ctx)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from harness.orchestrator.workflows.tdd_strict import TDDGate, TDDPhase

# ---------------------------------------------------------------------------
# Mensajes de bloqueo (razones del veredicto, con WHAT+WHY+WHERE)
# ---------------------------------------------------------------------------

_NO_RED_EVIDENCE_MSG = (
    "sin_evidencia_red: WHAT: El cambio en GREEN/REFACTOR carece de evidencia "
    "de que el test corrio y fallo en RED. "
    "WHY: TDD estricto exige test primero; sin red_evidence=True el modelo "
    "podria implementar sin fallo previo demostrado. "
    "WHERE: TDDPolicyEngine.evaluate() en harness/orchestrator/workflows/tdd_policy.py."
)

_TESTS_CHANGED_MSG = (
    "tests_modificados_entre_fases: WHAT: El hash actual de los tests difiere "
    "del hash firmado en RED. "
    "WHY: Cambiar (borrar o debilitar) tests entre RED y DONE rompe el "
    "anti-gaming del TDD estricto. "
    "WHERE: TDDPolicyEngine.evaluate() en harness/orchestrator/workflows/tdd_policy.py."
)

_TESTS_NOT_GREEN_MSG = (
    "tests_no_verdes: WHAT: No todos los tests estan en verde "
    "(tests_passed != tests_total). "
    "WHY: La fase solo se cierra con el 100% de tests aprobados. "
    "WHERE: TDDPolicyEngine.evaluate() en harness/orchestrator/workflows/tdd_policy.py."
)

_MUTATION_LOW_MSG = (
    "mutation_bajo_umbral: WHAT: El mutation score esta por debajo del umbral. "
    "WHY: El codigo sin matar suficientes mutantes no es robusto frente a "
    "regresiones; se exige >= MUTATION_MIN. "
    "WHERE: TDDPolicyEngine.evaluate() en harness/orchestrator/workflows/tdd_policy.py."
)

_BRANCH_LOW_MSG = (
    "branch_bajo_umbral: WHAT: La cobertura de ramas esta por debajo del umbral. "
    "WHY: Ramas sin ejercitar esconden bugs; se exige >= BRANCH_MIN. "
    "WHERE: TDDPolicyEngine.evaluate() en harness/orchestrator/workflows/tdd_policy.py."
)

_APPROVED_MSG = "APROBADO: todos los checks del TDDPolicyEngine pasaron; se puede emitir DONE."

# ---------------------------------------------------------------------------
# Mensajes de validacion de PolicyContext (WHAT+WHY+WHERE)
# ---------------------------------------------------------------------------

_CTX_TASK_ID_MSG = (
    "WHAT: PolicyContext con task_id vacio. "
    "WHY: Cada tarea evaluada debe tener un identificador unico. "
    "WHERE: PolicyContext.__post_init__() en harness/orchestrator/workflows/tdd_policy.py."
)

_CTX_TESTS_TOTAL_MSG = (
    "WHAT: PolicyContext con tests_total negativo. "
    "WHY: El total de tests no puede ser menor que 0. "
    "WHERE: PolicyContext.__post_init__() en harness/orchestrator/workflows/tdd_policy.py."
)

_CTX_MUTATION_MSG = (
    "WHAT: PolicyContext con mutation_score fuera de [0, 100]. "
    "WHY: El mutation score es un porcentaje entre 0 y 100. "
    "WHERE: PolicyContext.__post_init__() en harness/orchestrator/workflows/tdd_policy.py."
)

_CTX_BRANCH_MSG = (
    "WHAT: PolicyContext con branch_coverage fuera de [0, 100]. "
    "WHY: La cobertura de ramas es un porcentaje entre 0 y 100. "
    "WHERE: PolicyContext.__post_init__() en harness/orchestrator/workflows/tdd_policy.py."
)


# ---------------------------------------------------------------------------
# PolicyContext: contexto de la tarea evaluada
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyContext:
    """Contexto de politica TDD de una tarea evaluada por TDDPolicyEngine.

    Attributes:
        task_id: Identificador unico de la tarea.
        phase: Fase TDD actual (RED, GREEN o REFACTOR).
        test_files_modified: True si se modificaron archivos de test.
        src_files_modified: True si se modificaron archivos en src/.
        tests_passed: Tests aprobados en la ejecucion actual.
        tests_total: Total de tests de la suite (0 si no evaluado).
        mutation_score: Mutation score en porcentaje (0..100, 0 si no evaluado).
        branch_coverage: Cobertura de ramas en porcentaje (0..100, 0 si no evaluado).
        red_evidence: True si el test corrio y fallo en RED antes de implementar.
        tests_hash_red: Hash de los tests firmados en la fase RED (None si no hay).
        tests_hash_now: Hash actual de los tests (None si no hay).
    """

    task_id: str
    phase: TDDPhase
    test_files_modified: bool
    src_files_modified: bool
    tests_passed: int
    tests_total: int
    mutation_score: float
    branch_coverage: float
    red_evidence: bool
    tests_hash_red: str | None
    tests_hash_now: str | None

    def __post_init__(self) -> None:
        """Valida los invariantes del contexto de politica.

        Raises:
            ValueError: Si task_id esta vacio, tests_total es negativo, o
                mutation_score/branch_coverage estan fuera de [0, 100].
        """
        if not self.task_id:
            raise ValueError(_CTX_TASK_ID_MSG)
        if self.tests_total < 0:
            raise ValueError(_CTX_TESTS_TOTAL_MSG)
        if not 0.0 <= self.mutation_score <= 100.0:
            raise ValueError(_CTX_MUTATION_MSG)
        if not 0.0 <= self.branch_coverage <= 100.0:
            raise ValueError(_CTX_BRANCH_MSG)


# ---------------------------------------------------------------------------
# PolicyVerdict: resultado con trazabilidad
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyVerdict:
    """Veredicto del TDDPolicyEngine con trazabilidad completa.

    Attributes:
        allowed: True si todos los checks pasaron (se puede emitir DONE).
        reasons: Razones de bloqueo, o de aprobacion, en orden de ejecucion.
        gate_checks: Nombres de los checks ejecutados por el gate maestro.
    """

    allowed: bool
    reasons: tuple[str, ...]
    gate_checks: tuple[str, ...]

    def summary(self) -> str:
        """Genera un resumen legible del veredicto para logs y humanos.

        Returns:
            Texto con el estado (APROBADO/BLOQUEADO), los checks ejecutados
            y las razones del veredicto.
        """
        status = "APROBADO" if self.allowed else "BLOQUEADO"
        checks = ", ".join(self.gate_checks)
        reasons = "; ".join(self.reasons) if self.reasons else "ninguna"
        return f"TDDPolicyEngine: {status} ({len(self.gate_checks)} checks: {checks}). Razones: {reasons}."


# ---------------------------------------------------------------------------
# TDDPolicyEngine: gate maestro TDD estricto
# ---------------------------------------------------------------------------


class TDDPolicyEngine:
    """Gate maestro TDD: decide si el cambio propuesto permite emitir DONE.

    Patron "model proposes, engine disposes" (arXiv 2604.26615): el motor no
    propone codigo, solo decide con reglas deterministas si el contexto
    respeta TDD estricto. Todos los checks se ejecutan siempre y se registran
    en PolicyVerdict.gate_checks para trazabilidad.
    """

    MUTATION_MIN = 85.0
    BRANCH_MIN = 80.0
    HASH_ALGORITHM = "sha256"

    def __init__(self) -> None:
        """Inicializa el motor con su gate de fases del TDD estricto."""
        self._gate = TDDGate()

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        """Ejecuta todos los checks del gate maestro y devuelve el veredicto.

        Args:
            ctx: Contexto de la tarea a evaluar.

        Returns:
            PolicyVerdict con allowed=True solo si todos los checks pasan;
            los checks ejecutados quedan en gate_checks para trazabilidad.
        """
        reasons: list[str] = []
        checks: list[str] = []
        self._check_phase(ctx, reasons, checks)
        self._check_test_first(ctx, reasons, checks)
        self._check_anti_gaming(ctx, reasons, checks)
        self._check_completitud(ctx, reasons, checks)
        self._check_mutation(ctx, reasons, checks)
        self._check_branch(ctx, reasons, checks)
        allowed = not reasons
        if allowed:
            reasons.append(_APPROVED_MSG)
        return PolicyVerdict(
            allowed=allowed,
            reasons=tuple(reasons),
            gate_checks=tuple(checks),
        )

    def can_emit_done(self, ctx: PolicyContext) -> tuple[bool, str]:
        """API corta para el orchestrator: True solo si el veredicto lo permite.

        Args:
            ctx: Contexto de la tarea a evaluar.

        Returns:
            Tupla (permitido, mensaje): permitido es True si todos los checks
            pasaron, y el mensaje es el summary legible del veredicto.
        """
        verdict = self.evaluate(ctx)
        return verdict.allowed, verdict.summary()

    @staticmethod
    def hash_tests(test_sources: tuple[str, ...]) -> str:
        """Firma los archivos de test con sha256 (firma anti-gaming).

        Args:
            test_sources: Rutas de los archivos de test a firmar.

        Returns:
            Hash sha256 hex del contenido concatenado de todos los archivos.

        Raises:
            FileNotFoundError: Si alguna ruta no existe, con WHAT+WHY+WHERE.
        """
        digest = hashlib.new(TDDPolicyEngine.HASH_ALGORITHM)
        for source in test_sources:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(
                    "WHAT: No se pudo firmar los tests: el archivo no existe: "
                    f"{source!r}. "
                    "WHY: hash_tests() exige rutas validas a archivos de test; "
                    "un archivo ausente rompe la firma anti-gaming. "
                    "WHERE: TDDPolicyEngine.hash_tests() en "
                    "harness/orchestrator/workflows/tdd_policy.py."
                )
            digest.update(path.read_bytes())
        return digest.hexdigest()

    # -- checks individuales (todos se ejecutan y se registran) -------------

    def _check_phase(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check a: gate por fase (reusa TDDGate.validate_phase)."""
        checks.append("fase")
        phase_ok, phase_msg = self._gate.validate_phase(ctx.phase, ctx.test_files_modified, ctx.src_files_modified)
        if not phase_ok:
            reasons.append(phase_msg)

    def _check_test_first(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check b: evidencia de RED en fases de implementacion."""
        checks.append("test_first")
        if ctx.phase is not TDDPhase.RED and not ctx.red_evidence:
            reasons.append(_NO_RED_EVIDENCE_MSG)

    def _check_anti_gaming(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check c: los tests no pueden cambiar entre RED y DONE."""
        checks.append("anti_gaming")
        if (
            ctx.tests_hash_red is not None
            and ctx.tests_hash_now is not None
            and ctx.tests_hash_red != ctx.tests_hash_now
        ):
            reasons.append(_TESTS_CHANGED_MSG)

    def _check_completitud(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check d: 100% de tests verdes si la suite fue evaluada."""
        checks.append("completitud")
        if ctx.tests_total > 0 and ctx.tests_passed != ctx.tests_total:
            reasons.append(_TESTS_NOT_GREEN_MSG)

    def _check_mutation(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check e: mutation score sobre MUTATION_MIN si fue evaluado."""
        checks.append("mutation")
        if 0.0 < ctx.mutation_score < self.MUTATION_MIN:
            reasons.append(_MUTATION_LOW_MSG)

    def _check_branch(self, ctx: PolicyContext, reasons: list[str], checks: list[str]) -> None:
        """Check f: branch coverage sobre BRANCH_MIN si fue evaluado."""
        checks.append("branch")
        if 0.0 < ctx.branch_coverage < self.BRANCH_MIN:
            reasons.append(_BRANCH_LOW_MSG)
