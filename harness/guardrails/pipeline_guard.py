"""pipeline_guard — Guardrail EN LINEA para pipelines de agentes.

WHAT: cablea el ``GuardrailEngine`` existente (``harness/guardrails``) al
flujo de ejecucion de agentes (``ParallelExecutor``). El motor multi-capa
(injection/PII/code-injection/toxicity) YA existia pero NO estaba conectado:
solo su propio paquete y un test lo importaban. Este modulo lo expone como
guardrail en linea: cada output de agente se screen-ea ANTES de devolverse.
WHY: FR-0007 (Cerbia, guardrails para pipelines LLM) motivo auditar el
pipeline; sin este cableado los outputs del fan-out paralelo se devuelven sin
validar contra code-injection/PII.
WHERE: ``ParallelExecutor.__init__(guard=...)`` + ``_apply_guard`` en
``run_parallel``; reutilizable en ``SwarmMode`` u otros ejecutores.

Diseno: hexagonal + DI (``engine`` inyectable), ``GuardScreen`` inmutable
(frozen), errores WHAT+WHY+WHERE, docstrings ES.

Uso:
    from harness.guardrails.pipeline_guard import PipelineGuard
    guard = PipelineGuard()
    screen = guard.screen(output_text, "output")
    if not screen.passed:
        bloquear(screen.blocked_reason())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from harness.guardrails.guardrail_types import GuardrailVerdict

logger = logging.getLogger("harness.guardrails.pipeline_guard")

#: Capas aceptadas por ``PipelineGuard.screen`` -> metodo del engine.
_LAYER_METHODS: dict[str, str] = {
    "input": "check_input",
    "output": "check_output",
    "content": "check_content",
}


@dataclass(frozen=True)
class GuardScreen:
    """Resultado inmutable del screening de un texto contra los guardrails.

    Attributes:
        passed: True salvo que el veredicto sea BLOCK.
        verdict: Veredicto del engine (PASS/BLOCK/FLAG/REWRITE).
        score: Puntaje de riesgo en [0, 1] (0 = seguro, 1 = peligroso).
        violations: Descripciones de las violaciones detectadas (vacio si PASS).
    """

    passed: bool
    verdict: GuardrailVerdict
    score: float
    violations: tuple[str, ...]

    def blocked_reason(self) -> str | None:
        """Razon del bloqueo (None si ``passed``).

        Returns:
            Violaciones unidas en un string, o None si el texto paso.
        """
        if self.passed:
            return None
        return "; ".join(self.violations) or self.verdict.value


class PipelineGuard:
    """Guardrail en linea que screen-ea outputs de agentes con el engine real.

    Args:
        engine: ``GuardrailEngine`` inyectable (None = crea uno real).
        enabled: False = bypass total (todas las evaluaciones pasan).

    Attributes:
        enabled: Estado del bypass.
    """

    def __init__(self, engine: object | None = None, enabled: bool = True) -> None:
        if engine is None:
            from harness.guardrails import GuardrailEngine

            engine = GuardrailEngine()
        self._engine = engine
        self.enabled = enabled

    def screen(self, text: str, layer: str = "output") -> GuardScreen:
        """Evalua ``text`` en la capa dada y devuelve el veredicto.

        Args:
            text: Texto a evaluar.
            layer: Capa del engine: "input" | "output" | "content".

        Returns:
            GuardScreen con el veredicto; ``passed`` False solo si BLOCK.

        Raises:
            TypeError: Si ``text`` no es str.
            ValueError: Si ``layer`` no es valida.
        """
        if not isinstance(text, str):
            raise TypeError(
                f"WHAT: text no es str ({type(text).__name__}). "
                "WHY: el engine evalua texto. "
                "WHERE: PipelineGuard.screen"
            )
        method_name = _LAYER_METHODS.get(layer)
        if method_name is None:
            raise ValueError(
                f"WHAT: layer invalida {layer!r}. "
                f"WHY: capas aceptadas: {sorted(_LAYER_METHODS)}. "
                "WHERE: PipelineGuard.screen"
            )
        if not self.enabled:
            return GuardScreen(passed=True, verdict=GuardrailVerdict.PASS, score=0.0, violations=())

        result = getattr(self._engine, method_name)(text)
        verdict = result.verdict
        passed = verdict is not GuardrailVerdict.BLOCK
        screen = GuardScreen(
            passed=passed,
            verdict=verdict,
            score=float(getattr(result, "score", 0.0)),
            violations=tuple(getattr(result, "violations", ()) or ()),
        )
        if not passed:
            logger.warning(
                "[PipelineGuard] OUTPUT BLOCKEADO (%s): %s",
                verdict.value,
                screen.blocked_reason(),
            )
        return screen
