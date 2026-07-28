"""Tests para AgentBenchmark — evaluacion estandarizada de agentes."""
from __future__ import annotations

import pytest

from harness.orchestrator.agent_benchmark import AgentBenchmark, BenchmarkResult


class TestAgentBenchmark:
    """Suite de pruebas para la clase AgentBenchmark."""

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def bench(self) -> AgentBenchmark:
        """Benchmark con dispatch mock por defecto."""
        return AgentBenchmark()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_evaluate_basic(self, bench: AgentBenchmark) -> None:
        """Debe evaluar una tarea con dispatch mock y devolver resultado valido.

        Verifica que el resultado tenga los campos esperados y que
        el score por defecto sea 1.0 cuando no hay expected_output.
        """
        result = bench.evaluate("Hola mundo")
        assert isinstance(result, BenchmarkResult)
        assert result.task == "Hola mundo"
        assert result.score == 1.0
        assert result.tokens_used > 0
        assert result.time_seconds >= 0
        assert result.success is True
        assert result.errors == []

    def test_evaluate_with_expected_output_match(self, bench: AgentBenchmark) -> None:
        """Debe asignar score 1.0 si expected_output aparece en la salida.

        El mock devuelve '[coordinator] Ejecutado: ...' por lo que
        'coordinator' debe coincidir.
        """
        result = bench.evaluate("Prueba", expected_output="coordinator")
        assert result.score == 1.0
        assert result.success is True

    def test_evaluate_with_expected_output_no_match(self, bench: AgentBenchmark) -> None:
        """Debe asignar score 0.0 si expected_output NO aparece en la salida.

        El mock no incluye 'INEXISTENTE', por lo que el score debe ser 0.
        """
        result = bench.evaluate("Sin coincidencia", expected_output="INEXISTENTE")
        assert result.score == 0.0
        assert result.success is False

    def test_evaluate_dispatch_exception(self) -> None:
        """Debe capturar excepcion del dispatch y devolver resultado con error.

        Si dispatch lanza una excepcion, el BenchmarkResult debe reflejar
        el error, score 0.0 y success=False.
        """

        def failing_dispatch(agent: str, task: str) -> str:
            raise RuntimeError("Fallo simulado")

        bench = AgentBenchmark(dispatch_fn=failing_dispatch)
        result = bench.evaluate("Tarea fallida")
        assert result.score == 0.0
        assert result.success is False
        assert len(result.errors) == 1
        assert "Fallo simulado" in result.errors[0]

    def test_evaluate_batch(self, bench: AgentBenchmark) -> None:
        """Debe evaluar multiples tareas y devolver lista de resultados.

        Verifica que la cantidad de resultados coincida con la cantidad
        de tareas y que cada uno sea un BenchmarkResult valido.
        """
        tasks = ["Tarea A", "Tarea B", "Tarea C"]
        results = bench.evaluate_batch(tasks)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, BenchmarkResult)
            assert r.score >= 0

    def test_get_summary_empty(self) -> None:
        """Debe devolver resumen con ceros si no hay evaluaciones.

        El diccionario debe contener las claves esperadas con valores
        en cero / 0.0.
        """
        bench = AgentBenchmark()
        summary = bench.get_summary()
        assert summary["avg_score"] == 0.0
        assert summary["total_time"] == 0.0
        assert summary["total_tokens"] == 0
        assert summary["success_rate"] == 0.0

    def test_get_summary_with_results(self, bench: AgentBenchmark) -> None:
        """Debe calcular estadisticas correctas tras varias evaluaciones.

        Se ejecutan dos tareas (una exitosa, una fallida) y se verifica
        que el resumen refleje los valores acumulados.
        """
        bench.evaluate("Tarea 1", expected_output="coordinator")  # success
        bench.evaluate("Tarea 2", expected_output="NO_EXISTE")     # fail

        summary = bench.get_summary()
        # avg_score = (1.0 + 0.0) / 2 = 0.5
        assert summary["avg_score"] == 0.5
        assert summary["total_time"] >= 0
        assert summary["total_tokens"] > 0
        # success_rate = 1 / 2 = 0.5
        assert summary["success_rate"] == 0.5

    def test_custom_dispatch(self) -> None:
        """Debe usar dispatch personalizado en lugar del mock por defecto.

        Un dispatch que devuelve 'OK' siempre debe producir score 1.0
        cuando el expected_output es 'OK'.
        """

        def custom_dispatch(agent: str, task: str) -> str:
            return f"[{agent}] OK: {task}"

        bench = AgentBenchmark(dispatch_fn=custom_dispatch)
        result = bench.evaluate("Tarea personalizada", expected_output="OK")
        assert result.score == 1.0
        assert result.success is True

    def test_evaluate_empty_task_raises(self, bench: AgentBenchmark) -> None:
        """Debe lanzar ValueError si la tarea es vacia o solo espacios."""
        with pytest.raises(ValueError, match="no puede estar vacia"):
            bench.evaluate("")
        with pytest.raises(ValueError, match="no puede estar vacia"):
            bench.evaluate("   ")
