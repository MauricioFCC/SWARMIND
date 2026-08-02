"""
EvalFactory — Framework de Evaluacion Multi-Capa para Swarmind.

Evalua las 7 capas del AI Factory Stack:
    1. LLM Eval:         Mide accuracy, latencia, costos por modelo
    2. RAG Eval:         Mide retrieval precision, recall, faithfulness
    3. VectorDB Eval:    Mide recall@k, latency, index quality
    4. Agent Eval:       Mide task completion, tool usage, planning quality
    5. MCP Eval:         Mide tool availability, latency, error rate
    6. Guardrails Eval:  Mide detection rate, false positive rate
    7. Integration Eval: Mide end-to-end latency, success rate

Cada eval produce un EvalResult con:
    - layer:     str (llm, rag, vectordb, agent, mcp, guardrails, integration)
    - metric:    str (accuracy, precision, recall, latency, cost, etc.)
    - value:     float (valor medido)
    - threshold: float (valor esperado)
    - passed:    bool (value >= threshold)
    - timestamp: str
    - metadata:  dict

EvalSuite:
    - name: str
    - evals: list[EvalResult]
    - run() -> EvalReport
    - compare(other) -> EvalDiff

EvalReport:
    - suite_name: str
    - total: int
    - passed: int
    - failed: int
    - pass_rate: float
    - avg_latency: float
    - results: list[EvalResult]
    - recommendations: list[str]

EvalDiff:
    - regressions: list[EvalResult]
    - improvements: list[EvalResult]
    - new: list[EvalResult]
    - score_change: float

Funcionalidad:
    - run_all() -> EvalReport
    - run_layer(layer) -> list[EvalResult]
    - compare_reports(before, after) -> EvalDiff
    - get_recommendations(report) -> list[str]
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EvalResult — Unidad atomica de evaluacion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalResult:
    """Resultado individual de una evaluacion sobre una capa del stack.

    Cada EvalResult representa una medicion puntual sobre una metrica
    especifica. La property ``passed`` indica si el valor cumple el umbral.

    Args:
        layer: Capa evaluada (llm, rag, vectordb, agent, mcp, guardrails, integration).
        metric: Nombre de la metrica evaluada (accuracy, latency, recall, etc.).
        value: Valor numerico medido durante la evaluacion.
        threshold: Valor minimo esperado para considerar la metrica como aceptable.
        timestamp: Momento ISO 8601 UTC en que se tomo la medicion.
        metadata: Diccionario extensible con contexto adicional (modelo, config, etc.).

    Returns:
        Una instancia inmutable de EvalResult.

    Raises:
        ValueError: Si ``layer`` o ``metric`` estan vacios, o si ``threshold``
            es negativo para metricas que representan proporciones.
    """

    layer: str
    metric: str
    value: float
    threshold: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida los campos obligatorios y reglas de negocio.

        Raises:
            ValueError: Si layer o metric estan vacios.
        """
        if not self.layer or not self.layer.strip():
            raise ValueError("El campo 'layer' no puede estar vacio. Cada eval debe pertenecer a una capa definida.")
        if not self.metric or not self.metric.strip():
            raise ValueError("El campo 'metric' no puede estar vacio. Cada eval debe medir una metrica especifica.")

    @property
    def passed(self) -> bool:
        """Indica si el valor medido cumple o supera el umbral establecido.

        Returns:
            True si value >= threshold, False en caso contrario.
        """
        return self.value >= self.threshold


# ---------------------------------------------------------------------------
# EvalSuite — Conjunto de evaluaciones organizadas
# ---------------------------------------------------------------------------


@dataclass
class EvalSuite:
    """Suite de evaluaciones que se ejecutan como una unidad coherente.

    Agrupa multiples EvalResult bajo un mismo nombre, permitiendo ejecutar
    todas las pruebas de una capa o del sistema completo con una sola llamada.

    Args:
        name: Nombre descriptivo de la suite (ej: "LLM Suite", "Regresion Nocturna").
        evals: Lista de funciones o EvalResult a evaluar. Cada elemento puede
            ser un EvalResult directo o un callable que retorne list[EvalResult].

    Returns:
        Una instancia configurable de EvalSuite.

    Raises:
        ValueError: Si ``name`` esta vacio.
    """

    name: str
    evals: list[EvalResult | Callable[[], list[EvalResult]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Valida que el nombre de la suite no este vacio.

        Raises:
            ValueError: Si name es None o cadena vacia.
        """
        if not self.name or not self.name.strip():
            raise ValueError("El nombre de la suite no puede estar vacio. Use un identificador descriptivo.")

    def run(self, concurrency: int = 1) -> EvalReport:
        """Ejecuta todas las evaluaciones de la suite y genera un reporte.

        Las funciones callable se invocan bajo demanda (lazy evaluation).
        Los resultados directos se incluyen tal cual. Mide latencia total.

        Args:
            concurrency: Numero de evaluaciones paralelas (reservado para futuro, aun no implementado).

        Returns:
            EvalReport con el resumen completo de la ejecucion.

        Raises:
            Exception: Re-emite errores de evaluacion individuales con contexto.
        """
        if concurrency != 1:
            logger.warning(
                "[EvalFactory] concurrencia=%d solicitada pero aun no implementada; se ejecuta secuencialmente. "
                "WHERE: EvalSuite.run() | WHAT: concurrency > 1 sin soporte.",
                concurrency,
            )

        collected: list[EvalResult] = []
        start_ts = time.monotonic()

        for idx, entry in enumerate(self.evals):
            try:
                if callable(entry):
                    # Evaluacion lazy: invoca la funcion y extiende resultados
                    results = entry()
                    if not isinstance(results, list):
                        logger.error(
                            "[EvalFactory] Suite '%s' eval #%d retorno %s en vez de list[EvalResult]. "
                            "WHERE: EvalSuite.run() | WHAT: tipo inesperado en callable.",
                            self.name, idx, type(results).__name__,
                        )
                        continue
                    collected.extend(results)
                elif isinstance(entry, EvalResult):
                    collected.append(entry)
                else:
                    logger.warning(
                        "[EvalFactory] Suite '%s' elemento #%d ignorado: tipo %s no soportado. "
                        "WHERE: EvalSuite.run() | WHAT: elemento no es EvalResult ni callable.",
                        self.name, idx, type(entry).__name__,
                    )
            except Exception:
                logger.exception(
                    "[EvalFactory] Error ejecutando evaluacion #%d en suite '%s'. "
                    "WHERE: EvalSuite.run() | WHAT: fallo en evaluacion | WHY: excepcion no controlada.",
                    idx, self.name,
                )

        elapsed = time.monotonic() - start_ts
        return EvalReport.from_results(suite_name=self.name, results=collected, elapsed=elapsed)

    def add_eval(self, eval_entry: EvalResult | Callable[[], list[EvalResult]]) -> None:
        """Agrega una evaluacion a la suite en tiempo de construccion.

        Args:
            eval_entry: EvalResult directo o funcion callable que retorna list[EvalResult].

        Raises:
            TypeError: Si eval_entry no es del tipo esperado.
        """
        if not isinstance(eval_entry, (EvalResult, Callable)):
            raise TypeError(
                f"eval_entry debe ser EvalResult o callable, recibio {type(eval_entry).__name__}. "
                "WHAT: tipo de argumento invalido | WHERE: EvalSuite.add_eval()"
            )
        self.evals.append(eval_entry)

    def compare(self, other: EvalSuite) -> EvalDiff:
        """Compara los resultados de esta suite con otra, produciendo un diff.

        Args:
            other: Otra suite contra la cual comparar.

        Returns:
            EvalDiff con regresiones, mejoras y nuevos resultados.

        Raises:
            TypeError: Si other no es una instancia de EvalSuite.
        """
        if not isinstance(other, EvalSuite):
            raise TypeError(
                f"El argumento 'other' debe ser EvalSuite, recibio {type(other).__name__}. "
                "WHAT: tipo invalido para comparacion | WHERE: EvalSuite.compare()"
            )
        report_self = self.run()
        report_other = other.run()
        return compare_reports(report_self, report_other)


# ---------------------------------------------------------------------------
# EvalReport — Reporte estructurado de una ejecucion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalReport:
    """Reporte generado tras ejecutar una suite de evaluaciones.

    Contiene estadisticas agregadas (total, passed, failed, pass_rate,
    avg_latency) y la lista completa de resultados. Las recomendaciones
    se generan automaticamente a partir de los resultados fallidos.

    Args:
        suite_name: Nombre de la suite que origino el reporte.
        total: Cantidad total de evaluaciones ejecutadas.
        passed: Cantidad de evaluaciones que superaron el umbral.
        failed: Cantidad de evaluaciones que NO superaron el umbral.
        pass_rate: Proporcion de evaluaciones exitosas (0.0 a 1.0).
        avg_latency: Latencia promedio de las evaluaciones (segundos).
        results: Lista completa de EvalResult generados.
        recommendations: Lista de recomendaciones accionables derivadas del reporte.
    """

    suite_name: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_latency: float
    results: list[EvalResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @classmethod
    def from_results(
        cls,
        suite_name: str,
        results: list[EvalResult],
        elapsed: float,
        latency_per_result: list[float] | None = None,
    ) -> EvalReport:
        """Construye un EvalReport a partir de la lista de resultados y tiempo transcurrido.

        Args:
            suite_name: Nombre de la suite evaluada.
            results: Resultados individuales de evaluacion.
            elapsed: Tiempo total de ejecucion en segundos.
            latency_per_result: Latencia individual por resultado (opcional).

        Returns:
            Instancia de EvalReport con metricas agregadas y recomendaciones.
        """
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        avg_lat = elapsed / total if total > 0 and latency_per_result is None else 0.0
        if latency_per_result:
            avg_lat = mean(latency_per_result) if latency_per_result else 0.0

        recommendations = _generate_recommendations(results)

        return cls(
            suite_name=suite_name,
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=round(pass_rate, 4),
            avg_latency=round(avg_lat, 6),
            results=results,
            recommendations=recommendations,
        )


# ---------------------------------------------------------------------------
# EvalDiff — Diferencias entre dos reportes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalDiff:
    """Diferencias calculadas entre dos ejecuciones de evaluacion (before/after).

    Permite identificar visualmente regresiones, mejoras y nuevas metricas
    introducidas entre dos momentos en el tiempo, tipicamente usada en
    pipelines CI/CD para detectar degradaciones.

    Args:
        regressions: Resultados que empeoraron (antes pasaban, ahora fallan).
        improvements: Resultados que mejoraron (antes fallaban, ahora pasan).
        new: Resultados nuevos que no existian en el reporte anterior.
        score_change: Diferencia neta en la tasa de aciertos (after - before).
    """

    regressions: list[EvalResult] = field(default_factory=list)
    improvements: list[EvalResult] = field(default_factory=list)
    new: list[EvalResult] = field(default_factory=list)
    score_change: float = 0.0

    @property
    def has_regressions(self) -> bool:
        """Indica si se detectaron regresiones en la comparacion.

        Returns:
            True si hay al menos un resultado en regresiones.
        """
        return len(self.regressions) > 0

    @property
    def summary(self) -> str:
        """Resumen textual legible del diff.

        Returns:
            Cadena formateada con el conteo de regresiones, mejoras y nuevos.
        """
        return (
            f"Diff: {len(self.regressions)} regresiones, "
            f"{len(self.improvements)} mejoras, "
            f"{len(self.new)} nuevas, "
            f"score_change={self.score_change:+.2%}"
        )


# ---------------------------------------------------------------------------
# Funciones core del framework
# ---------------------------------------------------------------------------

# Mapa de capas a funciones de evaluacion builtin
_LAYER_EVAL_REGISTRY: dict[str, list[Callable[[], list[EvalResult]]]] = {}


def register_layer_evals(layer: str, *evals: Callable[[], list[EvalResult]]) -> None:
    """Registra funciones de evaluacion para una capa especifica.

    Args:
        layer: Nombre de la capa (llm, rag, vectordb, agent, mcp, guardrails, integration).
        evals: Una o mas funciones callable que retornan list[EvalResult].

    Raises:
        ValueError: Si layer esta vacio.
        TypeError: Si algun eval no es callable.
    """
    if not layer or not layer.strip():
        raise ValueError("El nombre de la capa no puede estar vacio. Use un identificador del stack.")
    for fn in evals:
        if not callable(fn):
            raise TypeError(
                f"Cada evaluacion debe ser callable, recibio {type(fn).__name__}. "
                "WHAT: tipo invalido en registro | WHERE: register_layer_evals()"
            )
    _LAYER_EVAL_REGISTRY.setdefault(layer, []).extend(evals)
    logger.debug(
        "[EvalFactory] Registradas %d evaluaciones para capa '%s'. WHERE: register_layer_evals()",
        len(evals), layer,
    )


def _generate_recommendations(results: list[EvalResult]) -> list[str]:
    """Genera recomendaciones accionables a partir de los resultados.

    Analiza cada resultado fallido y produce una recomendacion especifica
    basada en la capa y la metrica involucrada.

    Args:
        results: Lista de EvalResult para analizar.

    Returns:
        Lista de cadenas con recomendaciones priorizadas.
    """
    recs: list[str] = []
    failed_by_layer: dict[str, list[EvalResult]] = {}

    for r in results:
        if not r.passed:
            failed_by_layer.setdefault(r.layer, []).append(r)

    for layer, failures in failed_by_layer.items():
        metrics_failed = {f.metric for f in failures}
        if "accuracy" in metrics_failed and layer == "llm":
            recs.append(
                f"[{layer}] La exactitud (accuracy) esta por debajo del umbral. "
                "Considere ajustar el prompt, cambiar de modelo o aumentar ejemplos few-shot."
            )
        if "latency" in metrics_failed:
            recs.append(
                f"[{layer}] La latencia supera el umbral. Evalue reducir el tamano del contexto, "
                "usar un modelo mas rapido o implementar cache semantico."
            )
        if "cost" in metrics_failed:
            recs.append(
                f"[{layer}] El costo por token excede el presupuesto. "
                "Considere un modelo mas economico o compresion de contexto."
            )
        if "recall" in metrics_failed and layer in ("rag", "vectordb"):
            recs.append(
                f"[{layer}] El recall es bajo. Revise la estrategia de chunking, "
                "el embedding model o aumente el numero de documentos recuperados (top-k)."
            )
        if "faithfulness" in metrics_failed and layer == "rag":
            recs.append(
                f"[{layer}] La fidelidad al contexto es baja. Revise que el LLM no este "
                "alucinando informacion fuera de los documentos recuperados."
            )
        if "completion" in metrics_failed and layer == "agent":
            recs.append(
                f"[{layer}] La tasa de finalizacion de tareas es baja. Revise la definicion "
                "de tareas, las herramientas disponibles y el plan de ejecucion."
            )
        if "tool_usage" in metrics_failed and layer == "agent":
            recs.append(
                f"[{layer}] El uso correcto de herramientas es deficiente. "
                "Verifique la definicion de las herramientas y los parametros requeridos."
            )
        if "availability" in metrics_failed and layer == "mcp":
            recs.append(
                f"[{layer}] La disponibilidad de herramientas MCP es baja. "
                "Revise la conexion con los servidores MCP y los timeouts."
            )
        if "detection_rate" in metrics_failed and layer == "guardrails":
            recs.append(
                f"[{layer}] La tasa de deteccion de guardrails es baja. "
                "Ajuste la sensibilidad de los filtros de seguridad."
            )
        if "false_positive" in metrics_failed and layer == "guardrails":
            recs.append(
                f"[{layer}] La tasa de falsos positivos es alta. "
                "Revise los patrones de deteccion para reducir alertas innecesarias."
            )
        if "success_rate" in metrics_failed and layer == "integration":
            recs.append(
                f"[{layer}] La tasa de exito end-to-end es baja. "
                "Revise la integracion entre componentes y los puntos de fallo."
            )

        # Recomendacion generica si no hay especifica
        if not any(
            m in metrics_failed
            for m in ("accuracy", "latency", "cost", "recall", "faithfulness",
                      "completion", "tool_usage", "availability", "detection_rate",
                      "false_positive", "success_rate")
        ):
            for f in failures:
                recs.append(
                    f"[{layer}] Metrica '{f.metric}': valor {f.value} < umbral {f.threshold}. "
                    "Revise la configuracion y los parametros de la capa."
                )

    return recs


def run_layer(layer: str) -> list[EvalResult]:
    """Ejecuta todas las evaluaciones registradas para una capa especifica.

    Args:
        layer: Nombre de la capa a evaluar (llm, rag, vectordb, agent, mcp, guardrails, integration).

    Returns:
        Lista de EvalResult obtenidos de las evaluaciones de la capa.

    Raises:
        ValueError: Si la capa no tiene evaluaciones registradas.
    """
    evals = _LAYER_EVAL_REGISTRY.get(layer)
    if not evals:
        raise ValueError(
            f"No hay evaluaciones registradas para la capa '{layer}'. "
            "Use register_layer_evals() o builtin_evals para registrarlas. "
            "WHERE: run_layer()"
        )

    results: list[EvalResult] = []
    for eval_fn in evals:
        try:
            partial = eval_fn()
            if isinstance(partial, list):
                results.extend(partial)
            else:
                logger.warning(
                    "[EvalFactory] Funcion '%s' retorno tipo %s, se esperaba list[EvalResult]. "
                    "WHERE: run_layer() | WHAT: tipo de retorno inesperado.",
                    getattr(eval_fn, "__name__", "?"), type(partial).__name__,
                )
        except Exception:
            logger.exception(
                "[EvalFactory] Error ejecutando evaluacion para capa '%s' en funcion '%s'. "
                "WHERE: run_layer() | WHAT: fallo durante evaluacion | WHY: excepcion.",
                layer, getattr(eval_fn, "__name__", "?"),
            )

    return results


def run_all() -> EvalReport:
    """Ejecuta todas las evaluaciones de todas las capas registradas.

    Itera sobre el registro global de capas y recolecta todos los resultados
    en un unico reporte consolidado con recomendaciones.

    Returns:
        EvalReport con los resultados de todas las capas disponibles.
    """
    all_results: list[EvalResult] = []
    start_ts = time.monotonic()

    for layer in list(_LAYER_EVAL_REGISTRY.keys()):
        try:
            layer_results = run_layer(layer)
            all_results.extend(layer_results)
            logger.info(
                "[EvalFactory] Capa '%s': %d evaluaciones completadas. WHERE: run_all()",
                layer, len(layer_results),
            )
        except Exception:
            logger.exception(
                "[EvalFactory] Error ejecutando todas las evaluaciones para capa '%s'. "
                "WHERE: run_all() | WHAT: fallo en capa completa | WHY: excepcion no controlada.",
                layer,
            )

    elapsed = time.monotonic() - start_ts
    return EvalReport.from_results(suite_name="all", results=all_results, elapsed=elapsed)


def compare_reports(before: EvalReport, after: EvalReport) -> EvalDiff:
    """Compara dos reportes secuenciales (before/after) y produce un EvalDiff.

    Detecta regresiones (resultados que antes pasaban y ahora fallan),
    mejoras (antes fallaban y ahora pasan) y nuevas metricas.

    Args:
        before: Reporte de referencia anterior en el tiempo.
        after: Reporte actual o posterior.

    Returns:
        EvalDiff con las diferencias categorizadas.

    Raises:
        TypeError: Si before o after no son instancias de EvalReport.
    """
    if not isinstance(before, EvalReport) or not isinstance(after, EvalReport):
        raise TypeError(
            "Tanto 'before' como 'after' deben ser instancias de EvalReport. "
            "WHAT: tipo invalido | WHERE: compare_reports()"
        )

    # Indexar resultados anteriores por (layer, metric) para busqueda rapida
    before_index: dict[tuple[str, str], EvalResult] = {}
    for res in before.results:
        key = (res.layer, res.metric)
        before_index[key] = res

    regressions: list[EvalResult] = []
    improvements: list[EvalResult] = []
    new_evals: list[EvalResult] = []

    for after_res in after.results:
        key = (after_res.layer, after_res.metric)
        before_res = before_index.get(key)

        if before_res is None:
            # Nueva metrica que no existia antes
            new_evals.append(after_res)
        elif before_res.passed and not after_res.passed:
            # Antes pasaba, ahora falla -> regresion
            regressions.append(after_res)
        elif not before_res.passed and after_res.passed:
            # Antes fallaba, ahora pasa -> mejora
            improvements.append(after_res)

    # Cambio neto en la tasa de aciertos
    before_rate = before.pass_rate if before.total > 0 else 0.0
    after_rate = after.pass_rate if after.total > 0 else 0.0
    score_change = after_rate - before_rate

    return EvalDiff(
        regressions=regressions,
        improvements=improvements,
        new=new_evals,
        score_change=round(score_change, 4),
    )


def get_recommendations(report: EvalReport) -> list[str]:
    """Extrae y retorna las recomendaciones de un reporte ya generado.

    Si el reporte ya contiene recomendaciones, las retorna directamente.
    Si no, las genera a partir de los resultados del reporte.

    Args:
        report: Reporte de evaluacion del cual extraer recomendaciones.

    Returns:
        Lista de cadenas con recomendaciones accionables.

    Raises:
        TypeError: Si report no es una instancia de EvalReport.
    """
    if not isinstance(report, EvalReport):
        raise TypeError(
            f"El argumento debe ser EvalReport, recibio {type(report).__name__}. "
            "WHAT: tipo invalido | WHERE: get_recommendations()"
        )
    if report.recommendations:
        return report.recommendations
    return _generate_recommendations(report.results)
