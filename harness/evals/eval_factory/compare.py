"""Comparacion de reportes de evaluacion.

Submodulo interno del paquete :mod:`harness.evals.eval_factory`.

Extraido de forma mecanica desde ``eval_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``compare_reports``. Los cuerpos son identicos al
original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from .models import EvalDiff, EvalReport, EvalResult


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
