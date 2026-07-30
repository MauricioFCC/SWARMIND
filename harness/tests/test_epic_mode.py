"""
Tests para EpicMode — Multi-step workflows.

Verifica:
  - Inicializacion correcta
  - Ejecucion del workflow completo
  - Limite de iteraciones
  - Deteccion temprana de completitud
  - Estructura de artefactos generados
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from harness.orchestrator.worktable import Compendium, EpicMode, Worktable

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def epic() -> EpicMode:
    """EpicMode con configuracion por defecto (max 3 iteraciones)."""
    return EpicMode()


@pytest.fixture
def epic_one_iter() -> EpicMode:
    """EpicMode con solo 1 iteracion."""
    return EpicMode(max_iterations=1)


# ---------------------------------------------------------------------------
# Test: Init
# ---------------------------------------------------------------------------


class TestInit:
    """EpicMode inicializa correctamente."""

    def test_init_default(self) -> None:
        """Valores por defecto: max_iterations=3, artifacts vacio."""
        epic = EpicMode()
        assert epic._max_iterations == 3
        assert epic._artifacts == []

    def test_init_custom(self) -> None:
        """max_iterations personalizado."""
        epic = EpicMode(max_iterations=5)
        assert epic._max_iterations == 5
        assert epic._artifacts == []


# ---------------------------------------------------------------------------
# Test: Run
# ---------------------------------------------------------------------------


class TestRun:
    """Ejecucion del workflow epico."""

    def test_run_returns_compendium(self, epic: EpicMode) -> None:
        """run() retorna un Compendium."""
        result = epic.run("Implementar autenticacion")
        assert isinstance(result, Compendium)
        assert result.summary != ""
        assert "Epic mode" in result.summary

    def test_run_generates_artifacts(self, epic_one_iter: EpicMode) -> None:
        """Con 1 iteracion se genera 1 artefacto."""
        epic_one_iter.run("Tarea simple")
        assert len(epic_one_iter._artifacts) == 1
        artifact = epic_one_iter._artifacts[0]
        assert "iteration" in artifact
        assert "plan" in artifact
        assert "execution" in artifact
        assert "review" in artifact

    def test_run_max_iterations_respected(self) -> None:
        """EpicMode con max_iterations=2 solo ejecuta 2 iteraciones."""
        epic = EpicMode(max_iterations=2)
        result = epic.run("Tarea larga")
        # El summary dice cuantas iteraciones se ejecutaron
        assert "2" in result.summary or "1" in result.summary
        assert len(epic._artifacts) <= 2


# ---------------------------------------------------------------------------
# Test: Early completion
# ---------------------------------------------------------------------------


class TestEarlyCompletion:
    """Deteccion temprana de completitud."""

    def test_early_completion_completo(self) -> None:
        """Review con 'completo' rompe el loop temprano."""
        epic = EpicMode(max_iterations=5)

        call_count = [0]

        def mock_debate(
            self: Any,
            topic: str,
            agents: Any = None,
            rounds: int = 3,
            use_bundler: bool = False,
            creative_mode: bool = False,
        ) -> Compendium:
            call_count[0] += 1
            # En la tercera llamada (review) de la primera iteracion,
            # retornamos summary que contiene 'completo' exactamente
            if "Revisar" in topic and call_count[0] == 3:
                return Compendium(
                    summary="Trabajo completo, todo resuelto",
                    agreements=["done"],
                    trade_offs=[],
                    recommendations=[],
                )
            return Compendium(
                summary="En progreso",
                agreements=["continue"],
                trade_offs=[],
                recommendations=[],
            )

        with patch.object(Worktable, "debate", mock_debate):
            result = epic.run("Tarea con deteccion")

        # Solo deberia ejecutar 1 iteracion (porque 'completo' aparece)
        assert len(epic._artifacts) == 1
        assert "1" in result.summary

    def test_early_completion_aceptado(self) -> None:
        """Review con 'aceptado' rompe el loop temprano."""
        epic = EpicMode(max_iterations=5)

        call_count = [0]

        def mock_debate(
            self: Any,
            topic: str,
            agents: Any = None,
            rounds: int = 3,
            use_bundler: bool = False,
            creative_mode: bool = False,
        ) -> Compendium:
            call_count[0] += 1
            if "Revisar" in topic and call_count[0] == 3:
                return Compendium(
                    summary="Propuesta aceptado por el equipo",
                    agreements=["accepted"],
                    trade_offs=[],
                    recommendations=[],
                )
            return Compendium(
                summary="Iterando...",
                agreements=["pending"],
                trade_offs=[],
                recommendations=[],
            )

        with patch.object(Worktable, "debate", mock_debate):
            result = epic.run("Tarea aceptada")

        assert len(epic._artifacts) == 1
        assert "1" in result.summary


# ---------------------------------------------------------------------------
# Test: Artifact structure
# ---------------------------------------------------------------------------


class TestArtifactStructure:
    """Estructura de artefactos generados."""

    def test_artifact_keys(self, epic_one_iter: EpicMode) -> None:
        """Cada artefacto tiene las claves esperadas."""
        epic_one_iter.run("Diseñar API")
        artifact = epic_one_iter._artifacts[0]
        expected_keys = {"iteration", "plan", "execution", "review"}
        assert set(artifact.keys()) == expected_keys

    def test_artifact_values_are_strings(self, epic_one_iter: EpicMode) -> None:
        """plan, execution, review son strings (summaries)."""
        epic_one_iter.run("Refactorizar modulo")
        artifact = epic_one_iter._artifacts[0]
        assert isinstance(artifact["plan"], str)
        assert isinstance(artifact["execution"], str)
        assert isinstance(artifact["review"], str)
        assert isinstance(artifact["iteration"], int)
