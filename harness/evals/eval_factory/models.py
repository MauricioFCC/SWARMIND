"""Modelos de datos del framework de evaluacion multi-capa.

Submodulo interno del paquete :mod:`harness.evals.eval_factory`.

Extraido de forma mecanica desde ``eval_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``EvalResult``, ``EvalSuite``, ``EvalReport`` y
``EvalDiff``. Los cuerpos son identicos al original; solo cambia la
ubicacion fisica del codigo. Las dependencias circulares con ``compare``
y ``recommend`` se resuelven con imports lazy dentro de los metodos.
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
        from .compare import compare_reports

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
        from .recommend import _generate_recommendations

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
