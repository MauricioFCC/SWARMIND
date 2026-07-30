"""
guardrail_types — Enumeraciones y dataclasses del sistema de guardrails.

Extraido de guardrail_engine.py para mantener modulos < 900 lines.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuardrailVerdict(Enum):
    """Veredicto de un guardrail tras evaluar un texto.

    PASS:    No se detectaron problemas, paso libre.
    BLOCK:   Se debe bloquear la operacion (contenido peligroso).
    FLAG:    Se detectaron anomalias leves, requiere revision.
    REWRITE: El contenido debe ser reescrito (contenido mejorable).
    """

    PASS = "pass"
    BLOCK = "block"
    FLAG = "flag"
    REWRITE = "rewrite"


class GuardrailLayer(Enum):
    """Capas de proteccion del sistema de guardrails.

    Cada capa corresponde a un punto de control en el pipeline
    de ejecucion de Swarmind.
    """

    INPUT = "input"
    OUTPUT = "output"
    CONTENT = "content"
    TOOL = "tool"
    POLICY = "policy"


class GuardrailSeverity(Enum):
    """Nivel de severidad de una regla de guardrail.

    CRITICAL: Violacion bloqueante, detiene ejecucion.
    HIGH:     Violacion importante, requiere accion inmediata.
    MEDIUM:   Violacion moderada, debe revisarse.
    LOW:      Violacion menor, informativa.
    INFO:     Solo informativo, no bloquea.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class GuardrailResult:
    """Resultado de la evaluacion de uno o varios guardrails.

    Attributes:
        verdict: Veredicto final de la evaluacion.
        score: Puntaje de riesgo en [0, 1] (0 = seguro, 1 = peligroso).
        violations: Lista de descripciones de violaciones encontradas.
        metadata: Informacion adicional del chequeo (capas evaluadas, reglas,
            tiempos de ejecucion, etc.).
    """
    verdict: GuardrailVerdict
    score: float = 0.0
    violations: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_blocked(self) -> bool:
        """Indica si el resultado implica bloqueo de la operacion.

        Returns:
            True si el veredicto es BLOCK.
        """
        return self.verdict == GuardrailVerdict.BLOCK

    def is_pass(self) -> bool:
        """Indica si el resultado es completamente limpio.

        Returns:
            True si el veredicto es PASS.
        """
        return self.verdict == GuardrailVerdict.PASS

    def merge(self, other: GuardrailResult) -> GuardrailResult:
        """Combina dos resultados, priorizando el veredicto mas restrictivo.

        El score es el maximo de ambos. Las violaciones se concatenan.
        Los metadata se fusionan (los de ``other`` sobrescriben en caso
        de conflicto).

        Args:
            other: Otro GuardrailResult a fusionar.

        Returns:
            Nuevo GuardrailResult combinado.
        """
        severity_order: dict[GuardrailVerdict, int] = {
            GuardrailVerdict.PASS: 0,
            GuardrailVerdict.FLAG: 1,
            GuardrailVerdict.REWRITE: 2,
            GuardrailVerdict.BLOCK: 3,
        }

        merged_verdict: GuardrailVerdict = (
            self.verdict
            if severity_order.get(self.verdict, 0) >= severity_order.get(other.verdict, 0)
            else other.verdict
        )

        merged_metadata: dict[str, Any] = {**self.metadata, **other.metadata}

        return GuardrailResult(
            verdict=merged_verdict,
            score=max(self.score, other.score),
            violations=self.violations + other.violations,
            metadata=merged_metadata,
        )

    @staticmethod
    def pass_result(metadata: dict[str, Any] | None = None) -> GuardrailResult:
        """Crea un resultado PASS limpio.

        Args:
            metadata: Metadatos opcionales.

        Returns:
            GuardrailResult con verdict PASS y score 0.
        """
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            score=0.0,
            violations=(),
            metadata=metadata or {},
        )

    @staticmethod
    def block_result(
        reason: str,
        score: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """Crea un resultado BLOCK.

        Args:
            reason: Descripcion de la violacion.
            score: Puntaje de riesgo (default 1.0).
            metadata: Metadatos opcionales.

        Returns:
            GuardrailResult con verdict BLOCK.
        """
        return GuardrailResult(
            verdict=GuardrailVerdict.BLOCK,
            score=score,
            violations=(reason,),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class GuardrailRule:
    """Regla de guardrail configurable en el sistema.

    Attributes:
        name: Identificador unico de la regla.
        layer: Capa a la que pertenece (INPUT, OUTPUT, CONTENT, TOOL, POLICY).
        check_fn: Funcion que evalua el texto y retorna (violado, razon).
        severity: Nivel de severidad de la violacion.
        enabled: Si la regla esta activa actualmente.
        action: Accion por defecto ante violacion (BLOCK, FLAG, LOG, REWRITE).
    """
    name: str
    layer: GuardrailLayer
    check_fn: Callable[[str], tuple[bool, str]] = field(compare=False)
    severity: GuardrailSeverity = GuardrailSeverity.HIGH
    enabled: bool = True
    action: GuardrailVerdict = GuardrailVerdict.BLOCK

    def __post_init__(self) -> None:
        """Valida que la accion sea compatible con BLOCK/FLAG/REWRITE."""
        if self.action not in (GuardrailVerdict.BLOCK, GuardrailVerdict.FLAG,
                               GuardrailVerdict.REWRITE):
            object.__setattr__(self, 'action', GuardrailVerdict.BLOCK)
