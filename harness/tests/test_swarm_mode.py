"""
Tests para SwarmMode — ejecucion paralela de agentes en flota.

Cubre: run basico, paralelismo, fallos, consolidacion, dispatch
personalizado, prioridades, contextos, edge cases y error handling.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from harness.orchestrator.swarm_mode import SwarmMode, SwarmResult, SwarmTask


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def swarm_default() -> SwarmMode:
    """SwarmMode con configuracion por defecto."""
    return SwarmMode()


@pytest.fixture
def swarm_single() -> SwarmMode:
    """SwarmMode con un solo worker (ejecucion secuencial efectiva)."""
    return SwarmMode(max_workers=1)


@pytest.fixture
def sample_tasks() -> List[SwarmTask]:
    """Lista de tareas de ejemplo con distintas prioridades."""
    return [
        SwarmTask(agent="builder", description="implementar API REST", priority=5),
        SwarmTask(agent="scientist", description="investigar mejores practicas", priority=3),
        SwarmTask(agent="guardian", description="auditar seguridad", priority=8),
    ]


@pytest.fixture
def slow_dispatch() -> Callable[[str, str], str]:
    """Dispatch que simula trabajo pesado con latencia."""

    def _fn(agent: str, task: str) -> str:
        time.sleep(0.05)
        return f"[{agent}] Hecho: {task[:20]}"

    return _fn


@pytest.fixture
def failing_dispatch() -> Callable[[str, str], str]:
    """Dispatch que falla para ciertos agentes."""

    def _fn(agent: str, task: str) -> str:
        if agent == "failer":
            raise RuntimeError(f"Fallo simulado para {agent}")
        return f"[{agent}] OK"

    return _fn


# ===========================================================================
# Tests de inicializacion
# ===========================================================================


class TestInit:
    """Tests de construccion de SwarmMode."""

    def test_default_workers(self, swarm_default: SwarmMode) -> None:
        """Debe usar 4 workers por defecto."""
        assert swarm_default._max_workers == 4

    def test_custom_workers(self) -> None:
        """Debe aceptar max_workers personalizado."""
        swarm = SwarmMode(max_workers=8)
        assert swarm._max_workers == 8

    def test_default_dispatch_is_mock(self, swarm_default: SwarmMode) -> None:
        """Sin dispatch_fn debe usar _mock_dispatch."""
        assert swarm_default._dispatch.__name__ == "_mock_dispatch"

    def test_custom_dispatch(self) -> None:
        """Debe aceptar dispatch_fn personalizado."""
        def custom(agent: str, task: str) -> str:
            return f"custom-{agent}"
        swarm = SwarmMode(dispatch_fn=custom)
        assert swarm._dispatch("test", "x") == "custom-test"


# ===========================================================================
# Tests de SwarmTask
# ===========================================================================


class TestSwarmTask:
    """Tests del dataclass SwarmTask."""

    def test_default_priority(self) -> None:
        """Priority por defecto debe ser 5."""
        task = SwarmTask(agent="a", description="b")
        assert task.priority == 5

    def test_default_context(self) -> None:
        """Context por defecto debe ser None."""
        task = SwarmTask(agent="a", description="b")
        assert task.context is None

    def test_all_fields(self) -> None:
        """Todos los campos se asignan correctamente."""
        task = SwarmTask(
            agent="builder",
            description="test task",
            context="extra info",
            priority=10,
        )
        assert task.agent == "builder"
        assert task.description == "test task"
        assert task.context == "extra info"
        assert task.priority == 10


# ===========================================================================
# Tests de SwarmResult
# ===========================================================================


class TestSwarmResult:
    """Tests del dataclass SwarmResult."""

    def test_default_error_is_none(self) -> None:
        """Error por defecto debe ser None."""
        task = SwarmTask(agent="a", description="b")
        result = SwarmResult(task=task, success=True, output="ok", time_seconds=0.1)
        assert result.error is None

    def test_with_error(self) -> None:
        """Error debe almacenarse correctamente."""
        task = SwarmTask(agent="a", description="b")
        result = SwarmResult(
            task=task, success=False, output="", time_seconds=0.1, error="algo fallo"
        )
        assert result.error == "algo fallo"
        assert result.success is False


# ===========================================================================
# Tests de run basico
# ===========================================================================


class TestRun:
    """Tests del metodo run."""

    def test_empty_tasks(self, swarm_default: SwarmMode) -> None:
        """Lista vacia debe retornar lista vacia."""
        results = swarm_default.run([])
        assert results == []

    def test_single_task(self, swarm_default: SwarmMode) -> None:
        """Una tarea debe ejecutarse y retornar resultado exitoso."""
        tasks = [SwarmTask(agent="builder", description="hacer algo")]
        results = swarm_default.run(tasks)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].task.agent == "builder"

    def test_multiple_tasks(self, swarm_default: SwarmMode) -> None:
        """Multiples tareas deben ejecutarse todas exitosamente."""
        tasks = [
            SwarmTask(agent="a", description="t1"),
            SwarmTask(agent="b", description="t2"),
            SwarmTask(agent="c", description="t3"),
        ]
        results = swarm_default.run(tasks)
        assert len(results) == 3
        assert all(r.success for r in results)
        agents = {r.task.agent for r in results}
        assert agents == {"a", "b", "c"}

    def test_output_content(self, swarm_default: SwarmMode) -> None:
        """El output debe contener el nombre del agente y la tarea."""
        tasks = [SwarmTask(agent="builder", description="implementar API REST")]
        results = swarm_default.run(tasks)
        assert "[builder]" in results[0].output
        assert "implementar API REST" in results[0].output

    def test_run_with_none_raises(self, swarm_default: SwarmMode) -> None:
        """Pasar None como tasks debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no puede ser None"):
            swarm_default.run(None)  # type: ignore[arg-type]


# ===========================================================================
# Tests de paralelismo
# ===========================================================================


class TestParallelism:
    """Tests que verifican la ejecucion paralela."""

    def test_parallel_execution(self) -> None:
        """Tareas con latencia deben completarse en paralelo (menos tiempo que secuencial)."""
        swarm = SwarmMode(max_workers=4)
        tasks = [
            SwarmTask(agent=f"agent-{i}", description="slow task")
            for i in range(4)
        ]

        def slow_dispatch(agent: str, task: str) -> str:
            time.sleep(0.1)
            return f"[{agent}] done"

        swarm._dispatch = slow_dispatch
        start = time.time()
        results = swarm.run(tasks)
        elapsed = time.time() - start

        # Tiempo paralelo debe ser < suma de tiempos individuales
        # 4 tareas x 0.1s = 0.4s secuencial, con 4 workers ~0.1-0.15s
        assert elapsed < 0.3  # margen amplio
        assert len(results) == 4
        assert all(r.success for r in results)

    def test_single_worker_sequential(self, swarm_single: SwarmMode) -> None:
        """Con max_workers=1 las tareas deben ejecutarse secuencialmente."""
        execution_order: List[str] = []

        def tracking_dispatch(agent: str, task: str) -> str:
            execution_order.append(agent)
            time.sleep(0.02)
            return f"[{agent}]"

        swarm_single._dispatch = tracking_dispatch
        tasks = [
            SwarmTask(agent="first", description="t1"),
            SwarmTask(agent="second", description="t2"),
            SwarmTask(agent="third", description="t3"),
        ]
        swarm_single.run(tasks)
        assert execution_order == ["first", "second", "third"]


# ===========================================================================
# Tests de manejo de errores
# ===========================================================================


class TestErrors:
    """Tests de manejo de fallos en tareas."""

    def test_task_failure(self) -> None:
        """Una tarea que lanza excepcion debe retornar resultado con error."""
        swarm = SwarmMode(dispatch_fn=lambda a, t: (_ for _ in ()).throw(RuntimeError("boom")))
        tasks = [SwarmTask(agent="failer", description="fallara")]
        results = swarm.run(tasks)
        assert len(results) == 1
        assert results[0].success is False
        assert "boom" in (results[0].error or "")

    def test_mixed_success_failure(self, failing_dispatch: Callable) -> None:
        """Tareas mixtas: algunas exitosas y otras fallidas."""
        swarm = SwarmMode(dispatch_fn=failing_dispatch)
        tasks = [
            SwarmTask(agent="ok1", description="bien"),
            SwarmTask(agent="failer", description="mal"),
            SwarmTask(agent="ok2", description="bien"),
        ]
        results = swarm.run(tasks)
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert len(failures) == 1
        assert failures[0].task.agent == "failer"

    def test_time_measured_on_failure(self) -> None:
        """Incluso en fallo, time_seconds debe ser > 0."""
        swarm = SwarmMode(dispatch_fn=lambda a, t: (_ for _ in ()).throw(ValueError("nope")))
        tasks = [SwarmTask(agent="failer", description="fallara")]
        results = swarm.run(tasks)
        assert results[0].time_seconds >= 0

    def test_all_tasks_fail(self, failing_dispatch: Callable) -> None:
        """Todas las tareas fallan correctamente."""
        swarm = SwarmMode(dispatch_fn=lambda a, t: (_ for _ in ()).throw(RuntimeError("fail")))
        tasks = [
            SwarmTask(agent="a", description="x"),
            SwarmTask(agent="b", description="y"),
        ]
        results = swarm.run(tasks)
        assert all(not r.success for r in results)


# ===========================================================================
# Tests de prioridades
# ===========================================================================


class TestPriority:
    """Tests de ordenamiento por prioridad."""

    def test_results_sorted_by_priority_desc(self, swarm_default: SwarmMode) -> None:
        """Los resultados deben ordenarse por prioridad descendente."""
        tasks = [
            SwarmTask(agent="low", description="baja", priority=1),
            SwarmTask(agent="mid", description="media", priority=5),
            SwarmTask(agent="high", description="alta", priority=10),
        ]
        results = swarm_default.run(tasks)
        priorities = [r.task.priority for r in results]
        assert priorities == [10, 5, 1]

    def test_same_priority_preserves_order(self, swarm_default: SwarmMode) -> None:
        """Tareas con misma prioridad deben aparecer (no se garantiza orden interno)."""
        tasks = [
            SwarmTask(agent="a", description="t1", priority=5),
            SwarmTask(agent="b", description="t2", priority=5),
            SwarmTask(agent="c", description="t3", priority=5),
        ]
        results = swarm_default.run(tasks)
        assert len(results) == 3
        assert all(r.task.priority == 5 for r in results)


# ===========================================================================
# Tests de consolidacion
# ===========================================================================


class TestConsolidate:
    """Tests del metodo consolidate."""

    def test_consolidate_all_success(self) -> None:
        """Consolidacion con todas las tareas exitosas."""
        swarm = SwarmMode()
        tasks = [
            SwarmTask(agent="a", description="t1"),
            SwarmTask(agent="b", description="t2"),
        ]
        results = swarm.run(tasks)
        report = swarm.consolidate(results)
        assert "Exitosos: 2/2" in report
        assert "Fallos:" not in report

    def test_consolidate_with_failures(self) -> None:
        """Consolidacion con algunas tareas fallidas."""
        swarm = SwarmMode(dispatch_fn=lambda a, t: (_ for _ in ()).throw(RuntimeError("error")))
        tasks = [
            SwarmTask(agent="a", description="t1"),
            SwarmTask(agent="b", description="t2"),
        ]
        results = swarm.run(tasks)
        report = swarm.consolidate(results)
        assert "Exitosos: 0/2" in report
        assert "Fallos: 2" in report
        assert "error" in report

    def test_consolidate_mixed(self, failing_dispatch: Callable) -> None:
        """Consolidacion con resultados mixtos."""
        swarm = SwarmMode(dispatch_fn=failing_dispatch)
        tasks = [
            SwarmTask(agent="ok", description="bien"),
            SwarmTask(agent="failer", description="mal"),
        ]
        results = swarm.run(tasks)
        report = swarm.consolidate(results)
        assert "Exitosos: 1/2" in report
        assert "Fallos: 1" in report
        assert "Fallo simulado" in report

    def test_consolidate_header(self) -> None:
        """El reporte debe comenzar con el header markdown."""
        swarm = SwarmMode()
        results = swarm.run([SwarmTask(agent="a", description="t1")])
        report = swarm.consolidate(results)
        assert report.startswith("## Resultados del Swarm")

    def test_consolidate_with_none_raises(self, swarm_default: SwarmMode) -> None:
        """Pasar None a consolidate debe lanzar ValueError."""
        with pytest.raises(ValueError, match="no puede ser None"):
            swarm_default.consolidate(None)  # type: ignore[arg-type]

    def test_consolidate_empty(self, swarm_default: SwarmMode) -> None:
        """Lista vacia debe reportar 0/0 exitosos."""
        report = swarm_default.consolidate([])
        assert "Exitosos: 0/0" in report


# ===========================================================================
# Tests de dispatch personalizado
# ===========================================================================


class TestCustomDispatch:
    """Tests con funciones dispatch personalizadas."""

    def test_custom_dispatch_called(self) -> None:
        """La funcion dispatch personalizada debe ser invocada."""
        mock_fn = MagicMock(return_value="custom-output")
        swarm = SwarmMode(dispatch_fn=mock_fn)
        tasks = [SwarmTask(agent="builder", description="test")]
        swarm.run(tasks)
        mock_fn.assert_called_once_with("builder", "test")

    def test_custom_dispatch_result_in_output(self) -> None:
        """El output de dispatch personalizado debe aparecer en el resultado."""
        def custom(agent: str, task: str) -> str:
            return f"RESULT:{agent}:{task}"

        swarm = SwarmMode(dispatch_fn=custom)
        results = swarm.run([SwarmTask(agent="custom-agent", description="custom-task")])
        assert results[0].output == "RESULT:custom-agent:custom-task"

    def test_context_passed_through(self) -> None:
        """El campo context de SwarmTask debe propagarse (sin cambios)."""
        swarm = SwarmMode()
        task = SwarmTask(
            agent="builder",
            description="test",
            context="ctx-data-123",
        )
        results = swarm.run([task])
        assert results[0].task.context == "ctx-data-123"


# ===========================================================================
# Tests de integracion y borde
# ===========================================================================


class TestIntegration:
    """Tests de integracion y casos borde."""

    def test_many_tasks(self, swarm_default: SwarmMode) -> None:
        """50 tareas deben ejecutarse sin problemas."""
        tasks = [SwarmTask(agent=f"a{i}", description=f"task-{i}") for i in range(50)]
        results = swarm_default.run(tasks)
        assert len(results) == 50
        assert all(r.success for r in results)

    def test_result_type(self, swarm_default: SwarmMode) -> None:
        """Cada resultado debe ser instancia de SwarmResult."""
        results = swarm_default.run([SwarmTask(agent="a", description="t1")])
        assert isinstance(results[0], SwarmResult)

    def test_dispatch_return_type_coercion(self) -> None:
        """Dispatch que retorna no-string debe ser convertido a string."""
        swarm = SwarmMode(dispatch_fn=lambda a, t: 42)
        results = swarm.run([SwarmTask(agent="a", description="t1")])
        assert results[0].success is True
        assert results[0].output == "42"

    def test_long_description_truncated_in_mock(self) -> None:
        """Mock dispatch debe truncar descripciones largas a 50 chars."""
        swarm = SwarmMode()
        long_desc = "A" * 100
        results = swarm.run([SwarmTask(agent="a", description=long_desc)])
        output = results[0].output
        # output: "[a] Ejecutado en swarm: AAAA...AAA..."
        # la parte tras ":" son 50 A's + "...", tras rstrip quedan 50
        truncated = output.split(": ")[-1].rstrip(".")
        assert len(truncated) == 50
        assert truncated == "A" * 50

    def test_priority_edge_values(self, swarm_default: SwarmMode) -> None:
        """Prioridades extremas (0, negativas, muy altas) deben funcionar."""
        tasks = [
            SwarmTask(agent="zero", description="z", priority=0),
            SwarmTask(agent="neg", description="n", priority=-5),
            SwarmTask(agent="big", description="b", priority=9999),
        ]
        results = swarm_default.run(tasks)
        priorities = [r.task.priority for r in results]
        assert priorities == [9999, 0, -5]
