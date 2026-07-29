"""Tests para el modulo de Paralelismo Maximo.

Cubre:
- BatchAccumulator: I/O fusion, backpressure, stats
- AdaptivePool: escalado, metricas, shutdown
- PipelineMACU: DAG vivo, replanning, ready frontier
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

import pytest

from harness.parallel import AdaptivePool, BatchAccumulator, PipelineMACU, PipelineTask


# ============================================================================
# Tests: BatchAccumulator
# ============================================================================

class TestBatchAccumulator:
    """Tests para el acumulador de I/O batch."""

    @pytest.mark.asyncio
    async def test_add_triggers_flush_at_batch_size(self) -> None:
        """Agregar max_batch_size items debe ejecutar flush_fn."""
        flushed: List[int] = []

        async def mock_flush(batch: List[int]) -> None:
            flushed.extend(batch)

        acc = BatchAccumulator(flush_fn=mock_flush, max_batch_size=3, max_latency_ms=5000, name="test")
        await acc.add(1)
        await acc.add(2)
        assert acc.buffer_size == 2  # Aun no hay flush
        await acc.add(3)  # Esto dispara flush (3 items = max_batch_size)

        assert acc.buffer_size == 0
        assert len(flushed) == 3

        stats = acc.stats()
        assert stats.total_items == 3
        assert stats.total_batches == 1

    @pytest.mark.asyncio
    async def test_manual_flush(self) -> None:
        """flush() manual debe descargar el buffer."""
        flushed: List[int] = []

        async def mock_flush(batch: List[int]) -> None:
            flushed.extend(batch)

        acc = BatchAccumulator(flush_fn=mock_flush, max_batch_size=10, max_latency_ms=10000, name="manual")
        await acc.add(1)
        await acc.add(2)
        assert acc.buffer_size == 2

        n = await acc.flush()
        assert n == 2
        assert flushed == [1, 2]
        assert acc.buffer_size == 0

    @pytest.mark.asyncio
    async def test_close_flushes(self) -> None:
        """close() debe hacer flush final."""
        flushed: List[int] = []

        async def mock_flush(batch: List[int]) -> None:
            flushed.extend(batch)

        acc = BatchAccumulator(flush_fn=mock_flush, max_batch_size=10, max_latency_ms=10000, name="close")
        await acc.add(42)
        n = await acc.close()
        assert n == 1
        assert 42 in flushed
        assert acc.is_closed is True

    @pytest.mark.asyncio
    async def test_add_after_close(self) -> None:
        """Agregar items despues de close debe retornar False."""
        async def mock_flush(batch: List[int]) -> None:
            pass

        acc = BatchAccumulator(flush_fn=mock_flush, max_batch_size=10, max_latency_ms=10000, name="closed")
        await acc.close()
        result = await acc.add(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_stats_reflect_operations(self) -> None:
        """Stats debe reflejar operaciones correctamente."""
        async def mock_flush(batch: List[int]) -> None:
            pass  # Flush instantaneo

        acc = BatchAccumulator(flush_fn=mock_flush, max_batch_size=2, max_latency_ms=100, name="stats")
        await acc.add(1)
        await acc.add(2)  # Flush automatico

        stats = acc.stats()
        assert stats.total_items == 2
        assert stats.total_batches == 1
        assert stats.avg_batch_size == 2.0

    @pytest.mark.asyncio
    async def test_sync_flush_fn(self) -> None:
        """Soporte para flush_fn sincrona."""
        flushed: List[int] = []

        def sync_flush(batch: List[int]) -> None:
            flushed.extend(batch)

        acc = BatchAccumulator(flush_fn=sync_flush, max_batch_size=2, max_latency_ms=100, name="sync")
        await acc.add(10)
        await acc.add(20)  # Flush
        assert flushed == [10, 20]

    @pytest.mark.asyncio
    async def test_flush_error_handling(self) -> None:
        """Error en flush_fn no debe romper el acumulador."""
        call_count: int = 0

        async def failing_flush(batch: List[int]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Fallo intencional")

        acc = BatchAccumulator(flush_fn=failing_flush, max_batch_size=2, max_latency_ms=100, name="errors")
        await acc.add(1)
        await acc.add(2)  # flush falla
        await acc.add(3)
        await acc.add(4)  # flush exitoso
        assert call_count == 2


# ============================================================================
# Tests: AdaptivePool
# ============================================================================

class TestAdaptivePool:
    """Tests para el pool adaptativo."""

    def test_submit_and_result(self) -> None:
        """submit() debe ejecutar la funcion y retornar resultado."""
        pool = AdaptivePool(min_workers=1, max_workers=4, scale_interval=10)

        def double(x: int) -> int:
            return x * 2

        future = pool.submit(double, 21)
        result = future.result(timeout=5)
        assert result == 42
        pool.shutdown(wait=False)

    def test_multiple_tasks(self) -> None:
        """Multiples tareas deben ejecutarse concurrentemente."""
        pool = AdaptivePool(min_workers=2, max_workers=4, scale_interval=10)
        results: List[int] = []

        def work(n: int) -> int:
            return n * n

        futures = [pool.submit(work, i) for i in range(5)]
        for f in futures:
            results.append(f.result(timeout=5))

        assert results == [0, 1, 4, 9, 16]
        pool.shutdown(wait=True)

    def test_get_metrics(self) -> None:
        """get_metrics debe retornar metricas del pool."""
        pool = AdaptivePool(min_workers=1, max_workers=4, scale_interval=10)
        pool.submit(lambda: 42).result(timeout=5)

        metrics = pool.get_metrics()
        assert metrics.completed_tasks >= 1
        assert metrics.current_workers >= 1
        pool.shutdown(wait=False)

    def test_shutdown_twice_safe(self) -> None:
        """shutdown() multiple debe ser seguro."""
        pool = AdaptivePool(min_workers=1, max_workers=2, scale_interval=10)
        pool.shutdown(wait=False)
        pool.shutdown(wait=False)  # No debe fallar

    def test_submit_after_shutdown_raises(self) -> None:
        """submit() despues de shutdown debe lanzar RuntimeError."""
        pool = AdaptivePool(min_workers=1, max_workers=2, scale_interval=10)
        pool.shutdown(wait=False)
        with pytest.raises(RuntimeError, match="Pool cerrado"):
            pool.submit(lambda: None)


# ============================================================================
# Tests: PipelineMACU
# ============================================================================

class TestPipelineMACU:
    """Tests para el pipeline DAG con replanning."""

    @pytest.mark.asyncio
    async def test_simple_dag_serial(self) -> None:
        """DAG serial de 3 tareas debe ejecutarse en orden."""
        pipeline = PipelineMACU(max_parallel=2)
        execution_order: List[str] = []

        task_a = PipelineTask(task_id="A", name="Task A", agent="builder", description="First")
        task_b = PipelineTask(task_id="B", name="Task B", agent="builder", description="Second", depends_on={"A"})
        task_c = PipelineTask(task_id="C", name="Task C", agent="builder", description="Third", depends_on={"B"})

        await pipeline.add_task(task_a)
        await pipeline.add_task(task_b)
        await pipeline.add_task(task_c)

        async def dispatch(task: PipelineTask) -> str:
            execution_order.append(task.task_id)
            return f"Result {task.task_id}"

        result = await pipeline.execute(dispatch)

        assert result.total_tasks == 3
        assert result.completed == 3
        assert result.failed == 0
        assert execution_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_parallel_dag(self) -> None:
        """Tareas independientes deben ejecutarse en paralelo."""
        pipeline = PipelineMACU(max_parallel=4)
        timestamps: Dict[str, float] = {}

        tasks = [
            PipelineTask(task_id=f"P{i}", name=f"Parallel {i}", agent="builder", description=f"Task {i}")
            for i in range(4)
        ]
        for t in tasks:
            await pipeline.add_task(t)

        async def dispatch(task: PipelineTask) -> str:
            timestamps[task.task_id] = time.monotonic()
            await asyncio.sleep(0.02)
            return f"OK {task.task_id}"

        result = await pipeline.execute(dispatch)
        assert result.completed == 4

        # Todas deben empezar con < 50ms de diferencia
        vals = list(timestamps.values())
        max_diff = max(vals) - min(vals)
        assert max_diff < 0.1, f"max_diff={max_diff}"

    @pytest.mark.asyncio
    async def test_replanning_generates_new_tasks(self) -> None:
        """Replanning debe generar nuevas tareas basado en resultados."""
        new_tasks: List[str] = []

        def replan(task_id: str, result: Any) -> List[PipelineTask]:
            if task_id == "A":
                t = PipelineTask(task_id="D", name="Replanned D", agent="scientist",
                                 description=f"from {task_id}", depends_on={"A"})
                new_tasks.append("D")
                return [t]
            return []

        pipeline = PipelineMACU(max_parallel=2, replan_fn=replan)

        await pipeline.add_task(PipelineTask(task_id="A", name="A", agent="builder", description="Root"))
        await pipeline.add_task(PipelineTask(task_id="B", name="B", agent="builder", description="Indep"))

        async def dispatch(task: PipelineTask) -> str:
            return f"Result {task.task_id}"

        result = await pipeline.execute(dispatch)
        assert result.total_tasks >= 3
        assert result.completed >= 3
        assert "D" in new_tasks

    @pytest.mark.asyncio
    async def test_failure_cancels_downstream(self) -> None:
        """Fallo de tarea debe cancelar dependientes."""
        pipeline = PipelineMACU(max_parallel=2)

        await pipeline.add_task(PipelineTask(task_id="A", name="A", agent="builder", description="Root"))
        await pipeline.add_task(PipelineTask(task_id="B", name="B", agent="builder", description="Dep", depends_on={"A"}))

        async def dispatch(task: PipelineTask) -> str:
            if task.task_id == "A":
                raise ValueError("Fallo intencional")
            return "OK"

        result = await pipeline.execute(dispatch)
        assert result.failed == 1
        assert result.cancelled >= 1
        assert result.completed == 0

    @pytest.mark.asyncio
    async def test_ready_tasks_ordered_by_priority(self) -> None:
        """get_ready_tasks debe ordenar por prioridad descendente."""
        pipeline = PipelineMACU(max_parallel=10)

        await pipeline.add_task(PipelineTask(task_id="low", name="Low", agent="b", description="", priority=1))
        await pipeline.add_task(PipelineTask(task_id="high", name="High", agent="b", description="", priority=10))
        await pipeline.add_task(PipelineTask(task_id="med", name="Med", agent="b", description="", priority=5))

        ready = await pipeline.get_ready_tasks()
        assert [t.task_id for t in ready] == ["high", "med", "low"]

    @pytest.mark.asyncio
    async def test_get_status_summary(self) -> None:
        """get_status_summary debe retornar conteos correctos."""
        pipeline = PipelineMACU(max_parallel=2)

        await pipeline.add_task(PipelineTask(task_id="X", name="X", agent="b", description=""))
        await pipeline.add_task(PipelineTask(task_id="Y", name="Y", agent="b", description="", depends_on={"X"}))

        summary = pipeline.get_status_summary()
        assert summary.get("READY", 0) == 1  # X lista
        assert summary.get("PENDING", 0) == 1  # Y espera por X

    @pytest.mark.asyncio
    async def test_add_invalid_dependency(self) -> None:
        """Dependencia inexistente debe lanzar ValueError."""
        pipeline = PipelineMACU(max_parallel=2)
        with pytest.raises(ValueError, match="Dependencia inexistente"):
            await pipeline.add_task(PipelineTask(task_id="Z", name="Z", agent="b", description="", depends_on={"NO_EXISTE"}))

    @pytest.mark.asyncio
    async def test_add_duplicate_id(self) -> None:
        """Task ID duplicado debe lanzar ValueError."""
        pipeline = PipelineMACU(max_parallel=2)
        await pipeline.add_task(PipelineTask(task_id="X", name="X", agent="b", description=""))
        with pytest.raises(ValueError, match="duplicado"):
            await pipeline.add_task(PipelineTask(task_id="X", name="X2", agent="b", description=""))

    @pytest.mark.asyncio
    async def test_empty_pipeline(self) -> None:
        """Pipeline sin tareas debe completar inmediatamente."""
        pipeline = PipelineMACU(max_parallel=2)

        async def dispatch(task: PipelineTask) -> str:
            return "ok"

        result = await pipeline.execute(dispatch)
        assert result.total_tasks == 0
        assert result.completed == 0
        assert result.total_time >= 0
