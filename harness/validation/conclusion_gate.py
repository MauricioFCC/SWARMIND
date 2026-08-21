"""conclusion_gate — Gate adversarial de conclusiones (ADR-0054).

Checklist de 10 ataques del Coherence Atlas: antes de aceptar una
conclusion, someterla a cada ataque y registrar si sobrevive. Si sobrevive
a todos -> ACCEPT; si cae ante alguno -> REVISE_CONFIDENCE con factor
sugerido. Ningun check puede omitirse silenciosamente.

Ejemplo::

    gate = ConclusionGate()
    veredicto = gate.submit(
        "El fix resuelve el bug",
        attack_results={"counterexample": True, "inverse": False, ...},
    )
    if not veredicto.accepted:
        ajustar_confianza(veredicto.confidence_factor)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Los 10 ataques del Atlas (constantes nombradas, fuente unica)
# ---------------------------------------------------------------------------

CHECK_COUNTEREXAMPLE = "counterexample"
CHECK_INVERSE = "inverse"
CHECK_ALTERNATIVE_CAUSE = "alternative_cause"
CHECK_MISSING_VARIABLE = "missing_variable"
CHECK_MEASUREMENT_ERROR = "measurement_error"
CHECK_SELECTION_BIAS = "selection_bias"
CHECK_GOODHART = "goodhart_gaming"
CHECK_ADVERSARIAL_ACTOR = "adversarial_actor"
CHECK_DISTRIBUTIONAL_HARM = "distributional_harm"
CHECK_LONG_TERM_CONSEQUENCE = "long_term_consequence"

#: Checklist completo en orden canonico del Atlas.
ADVERSARIAL_CHECKS: tuple[str, ...] = (
    CHECK_COUNTEREXAMPLE,
    CHECK_INVERSE,
    CHECK_ALTERNATIVE_CAUSE,
    CHECK_MISSING_VARIABLE,
    CHECK_MEASUREMENT_ERROR,
    CHECK_SELECTION_BIAS,
    CHECK_GOODHART,
    CHECK_ADVERSARIAL_ACTOR,
    CHECK_DISTRIBUTIONAL_HARM,
    CHECK_LONG_TERM_CONSEQUENCE,
)

#: Penalizacion de confianza por cada ataque NO superado.
_CONFIDENCE_PENALTY_PER_FAILURE = 0.15


class Verdict(Enum):
    """Veredicto del gate sobre una conclusion."""

    ACCEPT = "accept"
    REVISE_CONFIDENCE = "revise_confidence"


@dataclass(frozen=True)
class GateResult:
    """Resultado de someter una conclusion al gate adversarial.

    Args:
        conclusion: Conclusion evaluada.
        verdict: ACCEPT o REVISE_CONFIDENCE.
        failed_checks: Ataques que la conclusion NO supero.
        confidence_factor: Factor sugerido (1.0 = sin cambio).
    """

    conclusion: str
    verdict: Verdict
    failed_checks: tuple[str, ...]
    confidence_factor: float

    @property
    def accepted(self) -> bool:
        """True si el gate acepto la conclusion sin revisar confianza."""
        return self.verdict is Verdict.ACCEPT


class ConclusionGate:
    """Gate adversarial para conclusions antes de consolidarlas.

    Exige resultados explicitos de TODOS los checks del checklist;
    las omisiones son error, no silencio (regla ERR/Atlas).
    """

    def submit(
        self,
        conclusion: str,
        attack_results: dict[str, bool],
    ) -> GateResult:
        """Evalua una conclusion contra el checklist adversarial.

        Args:
            conclusion: Enunciado de la conclusion a validar (no vacio).
            attack_results: Mapa check -> True si la conclusion SOBREVIVE
                al ataque, False si cae.

        Returns:
            GateResult inmutable con veredicto y factor de confianza.

        Raises:
            ValueError: si conclusion es vacia, si falta algun check del
                checklist o si hay checks desconocidos (WHAT falta/sobra /
                WHY sin omisiones silenciosas / WHERE argumentos).
        """
        if not conclusion or not conclusion.strip():
            raise ValueError(
                "ValueError: la conclusion esta vacia. WHY: no se puede "
                "atacar un enunciado inexistente. WHERE: ConclusionGate."
                "submit (argumento 'conclusion')."
            )
        missing = [c for c in ADVERSARIAL_CHECKS if c not in attack_results]
        if missing:
            raise ValueError(
                f"ValueError: faltan resultados de los checks {missing}. "
                "WHY: ninguna omision silenciosa; todo ataque debe ejecutarse "
                "y registrarse. WHERE: ConclusionGate.submit "
                "(argumento 'attack_results')."
            )
        unknown = set(attack_results) - set(ADVERSARIAL_CHECKS)
        if unknown:
            raise ValueError(
                f"ValueError: checks desconocidos {sorted(unknown)}. WHY: solo "
                "se aceptan los 10 ataques del checklist canonico. WHERE: "
                "ConclusionGate.submit (argumento 'attack_results')."
            )
        failed = tuple(c for c in ADVERSARIAL_CHECKS if not attack_results[c])
        if not failed:
            return GateResult(
                conclusion=conclusion,
                verdict=Verdict.ACCEPT,
                failed_checks=(),
                confidence_factor=1.0,
            )
        factor = round(
            1.0 - _CONFIDENCE_PENALTY_PER_FAILURE * len(failed), 4
        )
        logger.warning(
            "ConclusionGate: '%s' cayo ante %d/%d ataques %s; factor=%.2f",
            conclusion[:60], len(failed), len(ADVERSARIAL_CHECKS),
            list(failed), factor,
        )
        return GateResult(
            conclusion=conclusion,
            verdict=Verdict.REVISE_CONFIDENCE,
            failed_checks=failed,
            confidence_factor=max(factor, 0.0),
        )
