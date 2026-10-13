"""Skill Lift — evaluacion pareada (paired evaluation) skill-on vs skill-off.

Implementa la tecnica frontera **Paired Evaluation / Skill Lift** (SkillsBench,
arXiv:2602.12670): para cada skill se corren las MISMAS tareas dos veces, una
con la skill activa y otra sin ella (ablacion), y se mide el delta de pass rate
en puntos porcentuales (``delta_pp = (pass_with - pass_without) * 100``).

El estandar de la literatura indica que muchas skills tienen lift <= 0 (16 de
84 tareas con delta negativo; las skills self-generated rinden -1.3pp). Por eso
solo se deben conservar las skills con ``verdict == "useful"`` (lift > 0).

Alcance (IDP): este modulo SOLO mide y clasifica. NO ejecuta LLM: el caller
inyecta un ``runner`` determinista (p. ej. respaldado por una tarea con verifier
determinista). NO aplica retiro de skills; el retiro es responsabilidad de
Library Drift. Complementa —no reemplaza— ``eval_factory.compare``, que compara
reportes secuenciales y NO hace ablacion pareada on/off.

Uso:
    def my_runner(task_id: str, skill: str | None) -> bool: ...

    evaluator = SkillLiftEvaluator(runner=my_runner)
    result = evaluator.evaluate("pdf-forms", ["t1", "t2", "t3"], trials=5)
    print(result.delta_pp, result.verdict)

    ranked = evaluator.evaluate_all(["skill-a", "skill-b"], ["t1", "t2"])
    print(evaluator.report(ranked))
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import mean
from typing import Literal

logger = logging.getLogger(__name__)

#: Ancho de la banda neutra en puntos porcentuales. Un |delta| <= este valor
#: se considera "neutral" (ruido de muestreo, sin lift significativo).
NEUTRAL_BAND_PP: float = 1.0

#: Numero de corridas por tarea y por condicion (pass@trials) si no se indica.
DEFAULT_TRIALS: int = 5

#: Factor de conversion de proporcion (0..1) a puntos porcentuales.
_PERCENT_SCALE: float = 100.0

#: Decimales de redondeo para tasas y deltas (coherente con EvalReport).
_ROUND_DECIMALS: int = 4

#: Veredicto posible de una skill tras medir su lift.
Verdict = Literal["useful", "neutral", "harmful"]

#: Runner inyectado: recibe (task_id, skill_name | None) y devuelve pass/fail.
#: ``skill_name is None`` representa la condicion de ablacion (sin skill).
SkillRunner = Callable[[str, str | None], bool]


@dataclass(frozen=True)
class LiftResult:
    """Resultado de la evaluacion pareada de una skill.

    Args:
        skill: Nombre de la skill evaluada.
        trials: Numero de corridas por tarea y condicion (pass@trials).
        pass_with: Pass rate promedio con la skill activa (0.0 a 1.0).
        pass_without: Pass rate promedio sin la skill (ablacion, 0.0 a 1.0).
        delta_pp: Lift en puntos porcentuales (``pass_with - pass_without``).
        verdict: Clasificacion segun ``delta_pp`` y ``NEUTRAL_BAND_PP``.
        notes: Contexto legible (tasas y motivo del veredicto).
    """

    skill: str
    trials: int
    pass_with: float
    pass_without: float
    delta_pp: float
    verdict: Verdict
    notes: str = ""


class SkillLiftEvaluator:
    """Evaluador pareado determinista skill-on vs skill-off.

    Inyecta la dependencia del verifier via ``runner`` (DI / hexagonal): el
    evaluador no conoce LLM alguno, solo orquesta la ablacion y agrega los
    resultados. Es determinista si el ``runner`` lo es.
    """

    def __init__(self, *, runner: SkillRunner) -> None:
        """Inicializa el evaluador con el runner inyectado.

        Args:
            runner: Callable ``(task_id, skill_name | None) -> bool`` que
                devuelve el pass/fail determinista del verifier para una tarea
                en una condicion (con skill o sin skill).

        Raises:
            TypeError: Si ``runner`` no es callable.
        """
        if not callable(runner):
            raise TypeError(
                f"runner debe ser callable, recibio {type(runner).__name__}. "
                "WHAT: dependencia invalida | WHERE: SkillLiftEvaluator.__init__() "
                "| WHY: se requiere (task_id, skill|None) -> bool."
            )
        self._runner: SkillRunner = runner

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def evaluate(self, skill: str, tasks: list[str], *, trials: int = DEFAULT_TRIALS) -> LiftResult:
        """Mide el lift de una skill sobre un conjunto de tareas (on/off).

        Corre cada tarea ``trials`` veces con la skill y ``trials`` veces sin
        ella, promedia el pass rate por condicion y calcula el delta en pp.

        Args:
            skill: Nombre de la skill a evaluar (no vacio).
            tasks: Lista de identificadores de tarea (no vacia).
            trials: Corridas por tarea y condicion (>= 1).

        Returns:
            LiftResult con tasas, delta, veredicto y notas.

        Raises:
            ValueError: Si ``skill`` o ``tasks`` estan vacios, o ``trials`` < 1.
        """
        self._validate(skill, tasks, trials)

        pass_with = self._pass_rate(skill, tasks, trials)
        pass_without = self._pass_rate(None, tasks, trials)
        delta_pp = round((pass_with - pass_without) * _PERCENT_SCALE, _ROUND_DECIMALS)
        verdict = self._classify(delta_pp)
        notes = (
            f"skill='{skill}' | with={pass_with:.4f} without={pass_without:.4f} "
            f"| delta={delta_pp:+.2f}pp | verdict={verdict} "
            f"(banda neutra +/-{NEUTRAL_BAND_PP:.1f}pp, trials={trials})"
        )
        return LiftResult(
            skill=skill,
            trials=trials,
            pass_with=round(pass_with, _ROUND_DECIMALS),
            pass_without=round(pass_without, _ROUND_DECIMALS),
            delta_pp=delta_pp,
            verdict=verdict,
            notes=notes,
        )

    def evaluate_all(
        self,
        skills: list[str],
        tasks: list[str],
        *,
        trials: int = DEFAULT_TRIALS,
    ) -> list[LiftResult]:
        """Evalua varias skills y las ordena por lift descendente.

        Args:
            skills: Nombres de skills a evaluar (no vacia).
            tasks: Tareas sobre las que evaluar cada skill (no vacia).
            trials: Corridas por tarea y condicion (>= 1).

        Returns:
            Lista de LiftResult ordenada por ``delta_pp`` de mayor a menor.

        Raises:
            ValueError: Si ``skills`` esta vacia.
        """
        if not skills:
            raise ValueError(
                "skills no puede estar vacia. WHAT: sin skills a evaluar "
                "| WHERE: SkillLiftEvaluator.evaluate_all()"
            )
        results = [self.evaluate(skill, tasks, trials=trials) for skill in skills]
        return sorted(results, key=lambda item: item.delta_pp, reverse=True)

    def report(self, results: Iterable[LiftResult]) -> dict[str, float]:
        """Agrega los resultados en un resumen por veredicto.

        Args:
            results: Resultados de lift a resumir.

        Returns:
            Diccionario con conteos ``useful``, ``neutral``, ``harmful`` y la
            ``mean_delta_pp`` (media de delta, 0.0 si no hay resultados).
        """
        materialized = list(results)
        counts = {"useful": 0, "neutral": 0, "harmful": 0}
        for result in materialized:
            counts[result.verdict] += 1
        if counts["harmful"]:
            logger.warning(
                "Skill Lift: %d skill(s) con lift negativo (harmful); candidatas a "
                "retiro via Library Drift. WHAT: delta_pp<0; WHY: danan la tarea; "
                "WHERE: SkillLiftEvaluator.report",
                counts["harmful"],
            )
        mean_delta = mean(r.delta_pp for r in materialized) if materialized else 0.0
        return {
            "useful": counts["useful"],
            "neutral": counts["neutral"],
            "harmful": counts["harmful"],
            "mean_delta_pp": round(mean_delta, _ROUND_DECIMALS),
        }

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _pass_rate(self, skill: str | None, tasks: list[str], trials: int) -> float:
        """Calcula el pass rate promedio (media del pass@trials por tarea).

        Args:
            skill: Skill activa o ``None`` para la condicion de ablacion.
            tasks: Tareas a correr.
            trials: Corridas por tarea.

        Returns:
            Proporcion media de corridas exitosas (0.0 a 1.0).
        """
        per_task: list[float] = []
        for task_id in tasks:
            passes = sum(1 for _ in range(trials) if self._runner(task_id, skill))
            per_task.append(passes / trials)
        return mean(per_task)

    @staticmethod
    def _classify(delta_pp: float) -> Verdict:
        """Clasifica el delta en la banda util/neutra/danina.

        Args:
            delta_pp: Lift en puntos porcentuales.

        Returns:
            "useful" si ``delta_pp > NEUTRAL_BAND_PP``; "harmful" si
            ``delta_pp < -NEUTRAL_BAND_PP``; "neutral" en caso contrario.
        """
        if delta_pp > NEUTRAL_BAND_PP:
            return "useful"
        if delta_pp < -NEUTRAL_BAND_PP:
            return "harmful"
        return "neutral"

    @staticmethod
    def _validate(skill: str, tasks: list[str], trials: int) -> None:
        """Valida los argumentos de ``evaluate`` (guardrail de entrada).

        Args:
            skill: Nombre de la skill.
            tasks: Lista de tareas.
            trials: Corridas por tarea.

        Raises:
            ValueError: Si algun argumento no cumple su contrato.
        """
        if not skill or not skill.strip():
            raise ValueError(
                "skill no puede estar vacia. WHAT: identificador faltante "
                "| WHERE: SkillLiftEvaluator.evaluate()"
            )
        if not tasks:
            raise ValueError(
                "tasks no puede estar vacia. WHAT: sin tareas no hay ablacion "
                "| WHERE: SkillLiftEvaluator.evaluate()"
            )
        if trials < 1:
            raise ValueError(
                f"trials debe ser >= 1, recibio {trials}. WHAT: pass@trials invalido "
                "| WHERE: SkillLiftEvaluator.evaluate()"
            )


__all__ = [
    "DEFAULT_TRIALS",
    "NEUTRAL_BAND_PP",
    "LiftResult",
    "SkillLiftEvaluator",
    "Verdict",
]
