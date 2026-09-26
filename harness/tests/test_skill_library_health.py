"""Tests para salud de bibliotecas de skills (ADR-0052).

Cubre:
- Anclas empíricas del estudio (precisión 29.6% @5, 3.3% @100).
- Monotonía decreciente de la precisión entre anclas.
- Clamps fuera de rango y validación de entrada.
- Advertencias accionables según tamaño y umbral.
- Inmutabilidad del reporte.
"""
from __future__ import annotations

from itertools import pairwise

import pytest

from harness.context.skill_library_health import (
    PRECISION_AT_5_SKILLS,
    PRECISION_AT_100_SKILLS,
    ROI_FLATTEN_SIZE,
    assess_library,
    estimate_retrieval_precision,
)


class TestEstimateRetrievalPrecision:
    """Modelo log-lineal entre los puntos medidos."""

    def test_ancla_pequena(self) -> None:
        assert estimate_retrieval_precision(5) == pytest.approx(PRECISION_AT_5_SKILLS)

    def test_ancla_grande(self) -> None:
        assert estimate_retrieval_precision(100) == pytest.approx(
            PRECISION_AT_100_SKILLS
        )

    def test_monotona_decreciente_entre_anclas(self) -> None:
        precisions = [estimate_retrieval_precision(n) for n in range(5, 101, 5)]
        assert all(a >= b for a, b in pairwise(precisions))

    def test_menor_que_cinco_usa_ancla_pequena(self) -> None:
        assert estimate_retrieval_precision(1) == PRECISION_AT_5_SKILLS

    def test_tamano_cero_rechazado(self) -> None:
        with pytest.raises(ValueError, match="tamaño de biblioteca inválido"):
            estimate_retrieval_precision(0)


class TestAssessLibrary:
    """Diagnóstico con advertencias accionables."""

    def test_biblioteca_pequena_es_saludable(self) -> None:
        report = assess_library(5)
        assert report.is_healthy is True
        assert report.warnings == ()
        assert report.estimated_success == pytest.approx(0.364)

    def test_biblioteca_de_100_no_es_saludable(self) -> None:
        report = assess_library(ROI_FLATTEN_SIZE)
        assert report.is_healthy is False
        assert len(report.warnings) == 2  # umbral de precisión + ROI plano
        assert "podar" in report.warnings[0]

    def test_advertencia_roi_aplanado_en_tamano_limite(self) -> None:
        report = assess_library(150)
        assert any("ROI" in warning for warning in report.warnings)

    def test_reporte_es_inmutable(self) -> None:
        report = assess_library(10)
        with pytest.raises(AttributeError):
            report.is_healthy = True  # type: ignore[misc]
