"""Tests para bounded_executor — bulkhead + backpressure + watchdog (ADR-0093).

Mesa OTP (2/3: B+D+C-lite): mismo mecanismo (Semaphore + Queue acotada +
wait_for) sin procesos OTP. Bulkhead aisla por dominio; backpressure con
shed (drop-newest+log) en vez de cola infinita/OOM; watchdog detecta hangs
que CB/retry no ven (liveness con deadline, no solo vivo).
"""

import time

import pytest

from harness.orchestrator.bounded_executor import (
    BoundedParallelExecutor,
    ShedLoad,
    ShedPolicy,
)


def _fast_task(name: str):
    """Fabrica tarea rapida que retorna su nombre."""

    def _fn() -> str:
        return name

    return _fn


def _slow_task(seconds: float):
    """Fabrica tarea lenta (para watchdog)."""

    def _fn() -> str:
        time.sleep(seconds)
        return "lento"

    return _fn


def test_executes_all_within_bounds() -> None:
    """N tareas <= capacidad ejecutan todas y retornan en orden."""
    ex = BoundedParallelExecutor(max_workers=2, queue_size=10)
    out = ex.map([_fast_task(f"t{i}") for i in range(4)])
    assert out.results == ["t0", "t1", "t2", "t3"]
    assert out.shed == 0


def test_shed_on_full_queue() -> None:
    """Cola llena + workers ocupados -> shed inmediato (no OOM)."""
    ex = BoundedParallelExecutor(max_workers=1, queue_size=1)
    out = ex.map(
        [_slow_task(0.3), _slow_task(0.3), _fast_task("extra")],
        timeout_s=5.0,
    )
    assert out.shed >= 1
    assert ex.shed_total >= 1


def test_shed_policy_oldest() -> None:
    """Politica oldest descarta la mas vieja encolada (documentado)."""
    ex = BoundedParallelExecutor(
        max_workers=1, queue_size=1, shed_policy=ShedPolicy.DROP_OLDEST
    )
    out = ex.map([_slow_task(0.3), _fast_task("vieja"), _fast_task("nueva")])
    assert out.shed >= 1


def test_watchdog_kills_hang() -> None:
    """Tarea que excede deadline -> TimeoutError sin colgar el pool."""
    ex = BoundedParallelExecutor(max_workers=1, queue_size=5)
    out = ex.map([_slow_task(30.0)], timeout_s=0.2)
    assert out.timeouts == 1
    assert out.results == []


def test_invalid_config_raises() -> None:
    """max_workers/queue_size no positivos fallan accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        BoundedParallelExecutor(max_workers=0, queue_size=5)
    with pytest.raises(ValueError, match="WHAT"):
        BoundedParallelExecutor(max_workers=2, queue_size=0)


def test_metrics_snapshot() -> None:
    """Metricas auditables: ejecutadas, shed, timeouts."""
    ex = BoundedParallelExecutor(max_workers=2, queue_size=10)
    ex.map([_fast_task("a")])
    snap = ex.metrics()
    assert snap["executed"] == 1
    assert snap["shed"] == 0
    assert snap["timeouts"] == 0


def test_shed_load_exception() -> None:
    """ShedLoad es Exception con mensaje accionable."""
    err = ShedLoad("cola llena")
    assert "cola llena" in str(err)
