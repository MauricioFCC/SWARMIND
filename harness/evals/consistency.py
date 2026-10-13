"""Consistency — Medicion de consistencia run-to-run (arXiv:2607.27942).

Tecnica frontera: el hallazgo mas consecuente del estudio es que **la
inconsistencia run-to-run es tan importante como la accuracy media**. Un sistema
con buena accuracy promedio pero que no resuelve confiablemente una tarea
individual tiene valor de produccion limitado; por eso la guia #4 exige medir la
**consistencia** junto a la accuracy.

Como funciona:
    Para una misma tarea y el mismo sistema se corren ``runs`` ejecuciones del
    verifier DETERMINISTA (``runner``) y se mide el pass rate observado ``p``.
    La varianza Bernoulli ``p * (1 - p)`` es el proxy de la varianza run-to-run
    (maxima en ``p = 0.5``, nula en ``p = 0`` o ``p = 1``): cuanto mas se acerca
    a 0, mas estable es el sistema. El ``consistency_score`` del reporte es la
    fraccion de tareas "stable" (la metrica que exige el paper).

Clasificacion (veredicto):
    - ``stable``: ``pass_rate >= stability_threshold`` (resuelve siempre).
    - ``broken``: ``pass_rate < flaky_threshold`` (nunca/nunca confiable).
    - ``flaky``: banda intermedia (a veces resuelve, a veces no).
    En el limite exacto ``pass_rate == flaky_threshold`` la tarea es ``flaky``
    (umbral de rotura ESTRICTO): exactamente la mitad de las corridas NO es
    "nunca confiable".

Alcance (IDP): este modulo SOLO mide y clasifica. NO ejecuta LLM: el caller
inyecta un ``runner`` determinista (DI / hexagonal). Complementa —no
reemplaza— ``skill_lift`` (lift pareado on/off) y ``calibration`` (Brier/ECE):
consistency mide la ESTABILIDAD del mismo sistema sobre la misma tarea.

Uso:
    def my_runner(task_id: str) -> bool: ...

    evaluator = ConsistencyEvaluator(runner=my_runner)
    result = evaluator.evaluate("pdf-forms", runs=10)
    print(result.pass_rate, result.variance, result.verdict)

    results = evaluator.evaluate_all(["t1", "t2"], runs=10)
    print(evaluator.report(results))  # consistency_score = stable / total
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import mean
from typing import Literal

#: Umbral de estabilidad: pass rate >= este valor =>"stable" (resuelve siempre).
DEFAULT_STABILITY_THRESHOLD: float = 0.95

#: Umbral de rotura: pass rate < este valor => "broken" (nunca confiable).
DEFAULT_FLAKY_THRESHOLD: float = 0.5

#: Numero de corridas por tarea si no se indica.
DEFAULT_RUNS: int = 10

#: Decimales de redondeo para tasas y varianzas.
_ROUND_DECIMALS: int = 4

#: Veredicto posible tras medir la consistencia de una tarea.
Verdict = Literal["stable", "flaky", "broken"]

#: Runner inyectado: recibe ``task_id`` y devuelve el pass/fail de un run.
#: Debe ser DETERMINISTA para que la consistencia sea reproducible.
Runner = Callable[[str], bool]


@dataclass(frozen=True)
class ConsistencyResult:
    """Resultado inmutable de la consistencia run-to-run de una tarea.

    Args:
        task_id: Identificador de la tarea evaluada.
        runs: Numero de corridas ejecutadas.
        passes: Numero de corridas exitosas (``0 <= passes <= runs``).
        pass_rate: Fraccion de corridas exitosas (``passes / runs``, 0.0 a 1.0).
        variance: Varianza Bernoulli ``p * (1 - p)`` (proxy run-to-run).
        stable: ``True`` si el veredicto es ``"stable"``.
        verdict: Clasificacion ``"stable"`` | ``"flaky"`` | ``"broken"``.
        notes: Contexto legible (tasa, varianza y umbrales aplicados).
    """

    task_id: str
    runs: int
    passes: int
    pass_rate: float
    variance: float
    stable: bool
    verdict: Verdict
    notes: str = ""


class ConsistencyEvaluator:
    """Evaluador determinista de estabilidad run-to-run.

    Inyecta la dependencia del verifier via ``runner`` (DI / hexagonal): el
    evaluador no conoce LLM alguno, solo corre el runner N veces y agrega la
    varianza Bernoulli. Es determinista si el ``runner`` lo es.
    """

    def __init__(
        self,
        *,
        runner: Runner,
        stability_threshold: float = DEFAULT_STABILITY_THRESHOLD,
        flaky_threshold: float = DEFAULT_FLAKY_THRESHOLD,
    ) -> None:
        """Inicializa el evaluador con el runner y los umbrales.

        Args:
            runner: Callable ``(task_id) -> bool`` que devuelve el pass/fail
                determinista de un run del verifier para una tarea.
            stability_threshold: Pass rate minimo para considerar "stable".
            flaky_threshold: Pass rate por debajo del cual la tarea es "broken".

        Raises:
            TypeError: Si ``runner`` no es callable.
            ValueError: Si los umbrales no estan en ``[0, 1]`` o estan invertidos.
        """
        if not callable(runner):
            raise TypeError(
                f"runner debe ser callable, recibio {type(runner).__name__}. "
                "WHAT: dependencia invalida | WHERE: ConsistencyEvaluator.__init__() "
                "| WHY: se requiere (task_id) -> bool."
            )
        _validate_thresholds(stability_threshold, flaky_threshold)
        self._runner: Runner = runner
        self._stability_threshold = stability_threshold
        self._flaky_threshold = flaky_threshold

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def evaluate(self, task_id: str, *, runs: int = DEFAULT_RUNS) -> ConsistencyResult:
        """Mide la consistencia run-to-run de una tarea.

        Corre el ``runner`` ``runs`` veces, calcula ``pass_rate`` y la varianza
        Bernoulli ``p(1-p)`` y clasifica la tarea.

        Args:
            task_id: Identificador de la tarea (no vacio).
            runs: Numero de corridas (>= 1).

        Returns:
            ``ConsistencyResult`` con taxa, varianza, veredicto y notas.

        Raises:
            ValueError: Si ``task_id`` esta vacio o ``runs`` < 1.
        """
        self._validate_task(task_id, runs)

        passes = sum(1 for _ in range(runs) if self._runner(task_id))
        pass_rate = passes / runs
        # Varianza Bernoulli p(1-p): proxy de la varianza run-to-run (max en 0.5).
        variance = pass_rate * (1.0 - pass_rate)
        verdict = self._classify(pass_rate)
        notes = (
            f"task='{task_id}' | passes={passes}/{runs} | p={pass_rate:.4f} "
            f"| var={variance:.4f} | verdict={verdict} "
            f"(stable>={self._stability_threshold:.2f}, broken<{self._flaky_threshold:.2f})"
        )
        return ConsistencyResult(
            task_id=task_id,
            runs=runs,
            passes=passes,
            pass_rate=round(pass_rate, _ROUND_DECIMALS),
            variance=round(variance, _ROUND_DECIMALS),
            stable=verdict == "stable",
            verdict=verdict,
            notes=notes,
        )

    def evaluate_all(
        self, task_ids: list[str], *, runs: int = DEFAULT_RUNS
    ) -> list[ConsistencyResult]:
        """Mide la consistencia de varias tareas, preservando el orden.

        Args:
            task_ids: Identificadores de tarea (no vacia).
            runs: Corridas por tarea (>= 1).

        Returns:
            Lista de ``ConsistencyResult`` en el mismo orden que ``task_ids``.

        Raises:
            ValueError: Si ``task_ids`` esta vacia.
        """
        if not task_ids:
            raise ValueError(
                "task_ids no puede estar vacia. WHAT: sin tareas no hay medicion "
                "| WHERE: ConsistencyEvaluator.evaluate_all()"
            )
        return [self.evaluate(task_id, runs=runs) for task_id in task_ids]

    def report(self, results: Iterable[ConsistencyResult]) -> dict[str, float]:
        """Agrega los resultados en un resumen de estabilidad.

        El ``consistency_score`` es la fraccion de tareas "stable": la metrica
        que exige el paper (arXiv:2607.27942, guia #4).

        Args:
            results: Resultados de consistencia a resumir.

        Returns:
            Diccionario con conteos ``stable``/``flaky``/``broken``,
            ``mean_pass_rate``, ``mean_variance`` y ``consistency_score``
            (todos 0.0 si no hay resultados).
        """
        materialized = list(results)
        counts = {"stable": 0, "flaky": 0, "broken": 0}
        for result in materialized:
            counts[result.verdict] += 1
        total = len(materialized)
        mean_pass_rate = mean(r.pass_rate for r in materialized) if total else 0.0
        mean_variance = mean(r.variance for r in materialized) if total else 0.0
        consistency_score = counts["stable"] / total if total else 0.0
        return {
            "stable": counts["stable"],
            "flaky": counts["flaky"],
            "broken": counts["broken"],
            "mean_pass_rate": round(mean_pass_rate, _ROUND_DECIMALS),
            "mean_variance": round(mean_variance, _ROUND_DECIMALS),
            "consistency_score": round(consistency_score, _ROUND_DECIMALS),
        }

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _classify(self, pass_rate: float) -> Verdict:
        """Clasifica el pass rate en stable/flaky/broken.

        Args:
            pass_rate: Fraccion de corridas exitosas (sin redondear).

        Returns:
            ``"stable"`` si ``pass_rate >= stability_threshold``; ``"broken"``
            si ``pass_rate < flaky_threshold``; ``"flaky"`` en caso contrario
            (incluye el limite exacto ``pass_rate == flaky_threshold``).
        """
        if pass_rate >= self._stability_threshold:
            return "stable"
        if pass_rate < self._flaky_threshold:
            return "broken"
        return "flaky"

    @staticmethod
    def _validate_task(task_id: str, runs: int) -> None:
        """Valida los argumentos de ``evaluate`` (guardrail de entrada).

        Args:
            task_id: Identificador de la tarea.
            runs: Numero de corridas.

        Raises:
            ValueError: Si ``task_id`` esta vacio o ``runs`` < 1.
        """
        if not task_id or not task_id.strip():
            raise ValueError(
                "task_id no puede estar vacio. WHAT: identificador faltante "
                "| WHERE: ConsistencyEvaluator.evaluate()"
            )
        if runs < 1:
            raise ValueError(
                f"runs debe ser >= 1, recibio {runs}. WHAT: sin corridas no hay "
                "varianza run-to-run | WHERE: ConsistencyEvaluator.evaluate()"
            )


def _validate_thresholds(stability_threshold: float, flaky_threshold: float) -> None:
    """Valida los umbrales de clasificacion (guardrail de entrada).

    Args:
        stability_threshold: Pass rate minimo para "stable".
        flaky_threshold: Pass rate por debajo del cual la tarea es "broken".

    Raises:
        ValueError: Si algun umbral sale de ``[0, 1]`` o estan invertidos.
    """
    for name, value in (
        ("stability_threshold", stability_threshold),
        ("flaky_threshold", flaky_threshold),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"{name} debe estar en [0, 1], recibio {value}. WHAT: umbral invalido "
                "| WHERE: ConsistencyEvaluator.__init__()"
            )
    if flaky_threshold > stability_threshold:
        raise ValueError(
            f"flaky_threshold ({flaky_threshold}) no puede superar a "
            f"stability_threshold ({stability_threshold}). WHAT: umbrales invertidos "
            "| WHERE: ConsistencyEvaluator.__init__()"
        )


__all__ = [
    "DEFAULT_FLAKY_THRESHOLD",
    "DEFAULT_RUNS",
    "DEFAULT_STABILITY_THRESHOLD",
    "ConsistencyEvaluator",
    "ConsistencyResult",
    "Runner",
    "Verdict",
]
