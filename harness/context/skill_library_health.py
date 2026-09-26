"""skill_library_health — Salud de una biblioteca de skills conforme crece.

Implementa el ADR-0052: el estudio contrastivo (SkillsBench, 528 triples
emparejados) demostró que el ROI de escribir más skills se aplana rápido y
que la precisión de recuperación COLAPSA con el tamaño de la biblioteca:

- Precisión de recuperación real: 29.6% con 5 skills -> 3.3% con 100.
- Éxito en tarea apenas se movió: 36.4% -> 39.3%.
- 65.7% del efecto de una skill es anclaje procedimental; solo 4.5% es
  inyección de conocimiento.

Este módulo expone un modelo log-lineal entre los puntos medidos para
estimar la salud de la biblioteca local y emitir advertencias accionables
(podar skills, fusionar, priorizar anclaje procedimental).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "PRECISION_AT_5_SKILLS",
    "PRECISION_AT_100_SKILLS",
    "ROI_FLATTEN_SIZE",
    "SUCCESS_AT_5_SKILLS",
    "SUCCESS_AT_100_SKILLS",
    "SkillLibraryReport",
    "assess_library",
    "estimate_retrieval_precision",
]

# Anclas empíricas del estudio contrastivo (ADR-0052).
_ANCHOR_SMALL = 5
_ANCHOR_LARGE = 100
PRECISION_AT_5_SKILLS = 0.296
PRECISION_AT_100_SKILLS = 0.033
SUCCESS_AT_5_SKILLS = 0.364
SUCCESS_AT_100_SKILLS = 0.393

# Tamaño a partir del cual el ROI de añadir skills se considera plano.
ROI_FLATTEN_SIZE = 100

# Suelo de precisión para extrapolación más allá del ancla grande.
_PRECISION_FLOOR = 0.01

# Umbral de advertencia: por debajo de esta precisión conviene podar.
_WARN_PRECISION_THRESHOLD = 0.10


@dataclass(frozen=True)
class SkillLibraryReport:
    """Diagnóstico de salud de una biblioteca de skills.

    Attributes:
        n_skills: Tamaño de la biblioteca evaluada.
        estimated_precision: Precisión de recuperación estimada [0, 1].
        estimated_success: Éxito en tarea estimado [0, 1].
        is_healthy: True si la precisión estimada supera el umbral.
        warnings: Advertencias accionables (vacías si está sana).
    """

    n_skills: int
    estimated_precision: float
    estimated_success: float
    is_healthy: bool
    warnings: tuple[str, ...] = ()


def estimate_retrieval_precision(n_skills: int) -> float:
    """Estima la precisión de recuperación según el tamaño de la biblioteca.

    Interpolación log-lineal entre los dos puntos medidos del estudio
    (5 -> 29.6%, 100 -> 3.3%), con suelo para extrapolación.

    Args:
        n_skills: Número de skills en la biblioteca (>= 1).

    Returns:
        Precisión estimada en [0.01, 1.0].

    Raises:
        ValueError: Si ``n_skills`` es menor que 1.
    """
    if n_skills < 1:
        raise ValueError(
            f"WHAT: tamaño de biblioteca inválido ({n_skills}). "
            "WHY: debe haber al menos 1 skill para estimar precisión. "
            "WHERE: estimate_retrieval_precision()"
        )
    if n_skills <= _ANCHOR_SMALL:
        return PRECISION_AT_5_SKILLS
    log_ratio = math.log(n_skills / _ANCHOR_SMALL) / math.log(
        _ANCHOR_LARGE / _ANCHOR_SMALL
    )
    precision = PRECISION_AT_5_SKILLS + (
        PRECISION_AT_100_SKILLS - PRECISION_AT_5_SKILLS
    ) * log_ratio
    return max(_PRECISION_FLOOR, min(1.0, precision))


def assess_library(n_skills: int) -> SkillLibraryReport:
    """Evalúa la salud de la biblioteca y genera advertencias accionables.

    Args:
        n_skills: Número de skills en la biblioteca.

    Returns:
        Reporte inmutable con precisión/éxito estimados y advertencias.

    Raises:
        ValueError: Si ``n_skills`` es menor que 1.
    """
    precision = estimate_retrieval_precision(n_skills)
    success = SUCCESS_AT_5_SKILLS + (
        SUCCESS_AT_100_SKILLS - SUCCESS_AT_5_SKILLS
    ) * min(1.0, math.log(max(n_skills, 1) / _ANCHOR_SMALL) / math.log(
        _ANCHOR_LARGE / _ANCHOR_SMALL
    ))
    warnings: list[str] = []
    if precision < _WARN_PRECISION_THRESHOLD:
        warnings.append(
            f"Precisión de recuperación estimada {precision:.1%} < "
            f"{_WARN_PRECISION_THRESHOLD:.0%}: podar o fusionar skills "
            "(el agente deja de leer el expediente correcto)"
        )
    if n_skills >= ROI_FLATTEN_SIZE:
        warnings.append(
            f"Biblioteca >= {ROI_FLATTEN_SIZE} skills: el ROI de añadir más "
            "se aplana; priorizar anclaje procedimental sobre nuevas skills"
        )
    return SkillLibraryReport(
        n_skills=n_skills,
        estimated_precision=precision,
        estimated_success=success,
        is_healthy=precision >= _WARN_PRECISION_THRESHOLD,
        warnings=tuple(warnings),
    )
