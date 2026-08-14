"""Recomendaciones accionables del framework de evaluacion.

Submodulo interno del paquete :mod:`harness.evals.eval_factory`.

Extraido de forma mecanica desde ``eval_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``_generate_recommendations`` (analisis de resultados
fallidos) y ``get_recommendations``. Los cuerpos son identicos al original;
solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from .models import EvalReport, EvalResult


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
