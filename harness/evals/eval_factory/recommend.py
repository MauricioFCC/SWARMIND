"""Recomendaciones accionables del framework de evaluacion.

Submodulo interno del paquete :mod:`harness.evals.eval_factory`.

Extraido de forma mecanica desde ``eval_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``_generate_recommendations`` (analisis de resultados
fallidos) y ``get_recommendations``. Los cuerpos son identicos al original;
solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from collections.abc import Callable

from .models import EvalReport, EvalResult

# Metricas con recomendacion especifica. Si un layer no falla ninguna de
# ellas se emite una recomendacion generica por cada resultado fallido.
_KNOWN_METRICS: tuple[str, ...] = (
    "accuracy",
    "latency",
    "cost",
    "recall",
    "faithfulness",
    "completion",
    "tool_usage",
    "availability",
    "detection_rate",
    "false_positive",
    "success_rate",
)

# Un predicado decide si la regla aplica a un layer y su set de metricas.
_Predicate = Callable[[str, frozenset[str]], bool]
# Recomendacion como plantilla con el placeholder ``{layer}``.
_Recommendation = str
_Rule = tuple[_Predicate, _Recommendation]

# Tabla de reglas evaluada en orden; varias reglas pueden aplicar a un layer.
_RULES: tuple[_Rule, ...] = (
    (
        lambda layer, metrics: "accuracy" in metrics and layer == "llm",
        (
            "[{layer}] La exactitud (accuracy) esta por debajo del umbral. "
            "Considere ajustar el prompt, cambiar de modelo o aumentar ejemplos few-shot."
        ),
    ),
    (
        lambda layer, metrics: "latency" in metrics,
        (
            "[{layer}] La latencia supera el umbral. Evalue reducir el tamano del contexto, "
            "usar un modelo mas rapido o implementar cache semantico."
        ),
    ),
    (
        lambda layer, metrics: "cost" in metrics,
        (
            "[{layer}] El costo por token excede el presupuesto. "
            "Considere un modelo mas economico o compresion de contexto."
        ),
    ),
    (
        lambda layer, metrics: "recall" in metrics and layer in ("rag", "vectordb"),
        (
            "[{layer}] El recall es bajo. Revise la estrategia de chunking, "
            "el embedding model o aumente el numero de documentos recuperados (top-k)."
        ),
    ),
    (
        lambda layer, metrics: "faithfulness" in metrics and layer == "rag",
        (
            "[{layer}] La fidelidad al contexto es baja. Revise que el LLM no este "
            "alucinando informacion fuera de los documentos recuperados."
        ),
    ),
    (
        lambda layer, metrics: "completion" in metrics and layer == "agent",
        (
            "[{layer}] La tasa de finalizacion de tareas es baja. Revise la definicion "
            "de tareas, las herramientas disponibles y el plan de ejecucion."
        ),
    ),
    (
        lambda layer, metrics: "tool_usage" in metrics and layer == "agent",
        (
            "[{layer}] El uso correcto de herramientas es deficiente. "
            "Verifique la definicion de las herramientas y los parametros requeridos."
        ),
    ),
    (
        lambda layer, metrics: "availability" in metrics and layer == "mcp",
        (
            "[{layer}] La disponibilidad de herramientas MCP es baja. "
            "Revise la conexion con los servidores MCP y los timeouts."
        ),
    ),
    (
        lambda layer, metrics: "detection_rate" in metrics and layer == "guardrails",
        (
            "[{layer}] La tasa de deteccion de guardrails es baja. "
            "Ajuste la sensibilidad de los filtros de seguridad."
        ),
    ),
    (
        lambda layer, metrics: "false_positive" in metrics and layer == "guardrails",
        (
            "[{layer}] La tasa de falsos positivos es alta. "
            "Revise los patrones de deteccion para reducir alertas innecesarias."
        ),
    ),
    (
        lambda layer, metrics: "success_rate" in metrics and layer == "integration",
        (
            "[{layer}] La tasa de exito end-to-end es baja. "
            "Revise la integracion entre componentes y los puntos de fallo."
        ),
    ),
)


def _recommendations_for_layer(
    layer: str, failures: list[EvalResult]
) -> list[str]:
    """Aplica la tabla de reglas a los resultados fallidos de una capa.

    Args:
        layer: Nombre de la capa evaluada.
        failures: Resultados fallidos pertenecientes a la capa.

    Returns:
        Recomendaciones especificas (o genericas) para la capa, en orden.
    """
    metrics_failed = frozenset(failure.metric for failure in failures)
    recommendations = [
        template.format(layer=layer)
        for predicate, template in _RULES
        if predicate(layer, metrics_failed)
    ]
    if metrics_failed.isdisjoint(_KNOWN_METRICS):
        recommendations.extend(
            f"[{layer}] Metrica '{failure.metric}': valor {failure.value} < "
            f"umbral {failure.threshold}. "
            "Revise la configuracion y los parametros de la capa."
            for failure in failures
        )
    return recommendations


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

    for result in results:
        if not result.passed:
            failed_by_layer.setdefault(result.layer, []).append(result)

    for layer, failures in failed_by_layer.items():
        recs.extend(_recommendations_for_layer(layer, failures))

    return recs


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
