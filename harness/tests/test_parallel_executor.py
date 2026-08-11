"""
Tests de ParallelExecutor (fan-out paralelo + votacion gobernada).

Aportacion anexada de ORCA (stablyai/orca, ADE 2026) implementada de forma
nativa en SWARMIND (sin dependencia externa):
  - Fan-out paralelo de tasks independientes (speedup wall-clock 1.5-2.5x).
  - Voting gobernado: N variantes solo para tareas complejas ambiguas
    (score >= 70 y confidence < 0.7 del ModelRouter), con tope de presupuesto
    budget * budget_factor (token economics ADR-0040).

Reglas: DI (provider/router inyectables), respeta max_workers, errores
WHAT+WHY+WHERE, sin except silencioso, determinismo en votacion.
"""
from __future__ import annotations

import time

import pytest

from harness.model_router.multi_provider_types import ExecutionResult
from harness.orchestrator.parallel_executor import (
    ParallelExecutor,
    ParallelResult,
    ParallelTask,
    VotingOutcome,
)

# ---------------------------------------------------------------------------
# Fakes (sin red, deterministas)
# ---------------------------------------------------------------------------

class FakeProvider:
    """MultiAPIProvider fake: registra llamadas y retorna resultados."""
    def __init__(self, fail_prompts: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_prompts = fail_prompts or set()
        self.delay_ms = 0.0

    def execute(self, model: str, prompt: str, **kwargs: object) -> ExecutionResult:
        self.calls.append((model, prompt))
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        if prompt in self.fail_prompts:
            return ExecutionResult(
                success=False, output="", source="cloud", model=model,
                duration_ms=5.0, error="Fake failure for task",
            )
        return ExecutionResult(
            success=True, output=f"out:{prompt[:10]}", source="cloud",
            model=model, duration_ms=1.0, tokens_used=100,
        )


class FakeRouter:
    """ModelRouter fake con score/confidence configurables por prompt."""
    def __init__(self, score: float = 30.0, confidence: float = 0.9) -> None:
        self.score = score
        self.confidence = confidence
        self.calls: list[str] = []

    def route(self, task_text: str, **kwargs: object) -> object:
        self.calls.append(task_text)
        return type(
            "R", (),
            {
                "model_route": type(
                    "MR", (),
                    {"route": "frontier" if self.score >= 50 else "small",
                     "score": self.score, "confidence": self.confidence},
                )(),
            },
        )()


# ---------------------------------------------------------------------------
# ParallelTask / ParallelResult
# ---------------------------------------------------------------------------

class TestParallelTask:
    """Contrato de ParallelTask."""

    def test_fields(self) -> None:
        """ParallelTask tiene id, prompt, agent_role y model_preference."""
        t = ParallelTask(id="t1", prompt="haz algo")
        assert t.id == "t1"
        assert t.prompt == "haz algo"
        assert t.agent_role == "*"
        assert t.model_preference is None

    def test_frozen(self) -> None:
        """ParallelTask es inmutable."""
        t = ParallelTask(id="t1", prompt="p")
        with pytest.raises(AttributeError):
            t.id = "otro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# run_parallel
# ---------------------------------------------------------------------------

class TestRunParallel:
    """Fan-out paralelo de tasks independientes."""

    def test_returns_one_result_per_task(self) -> None:
        """N tasks -> N ParallelResult."""
        provider = FakeProvider()
        ex = ParallelExecutor(provider=provider)
        tasks = [
            ParallelTask(id=f"t{i}", prompt=f"task {i}") for i in range(3)
        ]
        results = ex.run_parallel(tasks)
        assert len(results) == 3
        assert all(isinstance(r, ParallelResult) for r in results)
        assert all(r.success for r in results)
        assert provider.calls[0][0] in ("small", "frontier")

    def test_empty_tasks(self) -> None:
        """Sin tasks -> lista vacia sin errores."""
        ex = ParallelExecutor(provider=FakeProvider())
        assert ex.run_parallel([]) == []

    def test_max_workers_limits_concurrency(self) -> None:
        """max_workers=1 fuerza ejecucion secuencial (sin solapamiento)."""
        provider = FakeProvider()
        provider.delay_ms = 50.0
        ex = ParallelExecutor(provider=provider, max_workers=1)
        tasks = [ParallelTask(id=f"t{i}", prompt=f"p{i}") for i in range(3)]
        t0 = time.perf_counter()
        ex.run_parallel(tasks)
        elapsed = time.perf_counter() - t0
        # 3 x 50ms secuenciales >= 140ms; paralelo seria ~50ms
        assert elapsed >= 0.14

    def test_parallel_faster_than_sequential(self) -> None:
        """Con max_workers=3 el tiempo ~1x delay, no 3x."""
        provider = FakeProvider()
        provider.delay_ms = 100.0
        ex = ParallelExecutor(provider=provider, max_workers=3)
        tasks = [ParallelTask(id=f"t{i}", prompt=f"p{i}") for i in range(3)]
        t0 = time.perf_counter()
        ex.run_parallel(tasks)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.28  # 100ms + margen, no 300ms

    def test_failure_isolated(self) -> None:
        """Una task que falla no impide completar las demas."""
        provider = FakeProvider(fail_prompts={"b"})
        ex = ParallelExecutor(provider=provider)
        tasks = [
            ParallelTask(id="t0", prompt="a"),
            ParallelTask(id="t1", prompt="b"),
            ParallelTask(id="t2", prompt="c"),
        ]
        results = {r.task_id: r for r in ex.run_parallel(tasks)}
        assert results["t1"].success is False
        assert "Fake failure" in (results["t1"].error or "")
        assert results["t0"].success and results["t2"].success

    def test_router_determines_model(self) -> None:
        """El router decide small/frontier por task."""
        provider = FakeProvider()
        router = FakeRouter(score=80.0)
        ex = ParallelExecutor(provider=provider, router=router)
        ex.run_parallel([ParallelTask(id="t1", prompt="compleja")])
        assert provider.calls[0][0] == "frontier"
        assert router.calls == ["compleja"]


# ---------------------------------------------------------------------------
# Voting gobernado
# ---------------------------------------------------------------------------

class TestVotingGate:
    """El gate decide CUANDO pagar el costo 3x de la votacion."""

    def test_simple_task_no_voting(self) -> None:
        """Score < 70 (o confianza alta) -> ejecucion simple (1 llamada)."""
        provider = FakeProvider()
        router = FakeRouter(score=30.0, confidence=0.9)
        ex = ParallelExecutor(provider=provider, router=router)
        outcome = ex.vote_on_task(ParallelTask(id="t1", prompt="simple"))
        assert outcome.gate_applied is False
        assert len(provider.calls) == 1
        assert outcome.winner is not None and outcome.winner.success

    def test_complex_ambiguous_task_votes(self) -> None:
        """Score >= 70 y confidence < 0.7 -> N=3 variantes."""
        provider = FakeProvider()
        router = FakeRouter(score=80.0, confidence=0.5)
        ex = ParallelExecutor(provider=provider, router=router)
        outcome = ex.vote_on_task(ParallelTask(id="t1", prompt="ambigua"))
        assert outcome.gate_applied is True
        assert len(provider.calls) == 3

    def test_custom_n(self) -> None:
        """n configurable (default 3)."""
        provider = FakeProvider()
        router = FakeRouter(score=80.0, confidence=0.5)
        ex = ParallelExecutor(provider=provider, router=router)
        ex.vote_on_task(ParallelTask(id="t1", prompt="ambigua"), n=5)
        assert len(provider.calls) == 5

    def test_budget_cap_respected(self) -> None:
        """Tokens totales <= MAX_TOKENS_BY_AGENT[rol] * budget_factor."""
        provider = FakeProvider()
        router = FakeRouter(score=80.0, confidence=0.5)
        ex = ParallelExecutor(provider=provider, router=router, budget_factor=3.0)
        outcome = ex.vote_on_task(
            ParallelTask(id="t1", prompt="ambigua", agent_role="builder")
        )
        # 3 llamadas x 100 tokens = 300 <= 3072*3
        assert outcome.total_tokens <= 3072 * 3.0
        assert outcome.total_tokens == 300


class TestVoteLogic:
    """Mecanica de votacion: mayoria, empates, sin mayoria."""

    def _mk(self, output: str, duration: float = 1.0) -> ParallelResult:
        return ParallelResult(
            task_id="x", success=True, output=output, model="frontier",
            provider="fake", tokens_used=100, duration_ms=duration,
        )

    def test_majority_wins(self) -> None:
        """2 iguales + 1 distinto -> gana el par igual."""
        ex = ParallelExecutor(provider=FakeProvider())
        results = [
            self._mk("solucion A"), self._mk("solucion A"), self._mk("solucion B"),
        ]
        outcome = ex.vote(results)
        assert outcome.winner is not None
        assert outcome.winner.output == "solucion A"

    def test_tie_breaks_by_speed(self) -> None:
        """Empate 1-1 -> gana el de menor duration_ms."""
        ex = ParallelExecutor(provider=FakeProvider())
        results = [
            self._mk("solucion A", duration=5.0),
            self._mk("solucion B", duration=1.0),
        ]
        outcome = ex.vote(results)
        assert outcome.winner is not None
        assert outcome.winner.output == "solucion B"

    def test_no_majority_picks_fastest(self) -> None:
        """Sin mayoria (3 distintas) -> el mas rapido como ganador."""
        ex = ParallelExecutor(provider=FakeProvider())
        results = [
            self._mk("A", duration=3.0), self._mk("B", duration=1.0), self._mk("C", duration=2.0),
        ]
        outcome = ex.vote(results)
        assert outcome.winner is not None
        assert outcome.winner.output == "B"

    def test_empty_results_no_winner(self) -> None:
        """Sin resultados -> winner None."""
        ex = ParallelExecutor(provider=FakeProvider())
        outcome = ex.vote([])
        assert outcome.winner is None


# ---------------------------------------------------------------------------
# Stats / metricas
# ---------------------------------------------------------------------------

class TestStats:
    """Metricas para token economics (fan_out_factor, tokens por agente)."""

    def test_stats_after_parallel(self) -> None:
        """get_stats reporta fan_out_factor y tokens."""
        provider = FakeProvider()
        ex = ParallelExecutor(provider=provider)
        ex.run_parallel(
            [ParallelTask(id=f"t{i}", prompt=f"p{i}") for i in range(4)]
        )
        stats = ex.get_stats()
        assert stats["fan_out_factor"] == 1.0  # 4 tasks / 4 attempts
        assert stats["total_tokens"] == 400
        assert stats["total_duration_ms"] >= 0

    def test_stats_after_voting(self) -> None:
        """Voting incrementa fan_out_factor y cuenta voting_events."""
        provider = FakeProvider()
        router = FakeRouter(score=80.0, confidence=0.5)
        ex = ParallelExecutor(provider=provider, router=router)
        ex.vote_on_task(ParallelTask(id="t1", prompt="ambigua"))
        stats = ex.get_stats()
        assert stats["fan_out_factor"] == 3.0  # 3 attempts / 1 task
        assert stats["voting_events"] == 1
        assert stats["tokens_per_parallel_agent"] == 100

    def test_reset_stats(self) -> None:
        """reset_stats limpia las metricas acumuladas."""
        provider = FakeProvider()
        ex = ParallelExecutor(provider=provider)
        ex.run_parallel([ParallelTask(id="t1", prompt="p")])
        ex.reset_stats()
        stats = ex.get_stats()
        assert stats["total_tokens"] == 0
        assert stats["total_attempts"] == 0


# ---------------------------------------------------------------------------
# Integracion (sin mocks: provider real sin keys -> graceful)
# ---------------------------------------------------------------------------

class TestIntegration:
    """Sin proveedores registrados el executor no crashea (failover)."""

    def test_no_providers_graceful_failure(self) -> None:
        """Provider real sin API keys -> ParallelResult fallido con error."""
        ex = ParallelExecutor()  # provider real vacio
        results = ex.run_parallel([ParallelTask(id="t1", prompt="hola")])
        assert len(results) == 1
        assert results[0].success is False
        assert "WHY" in (results[0].error or "")  # error accionable

    def test_vote_returns_voting_outcome_type(self) -> None:
        """vote_on_task retorna VotingOutcome siempre."""
        ex = ParallelExecutor()
        outcome = ex.vote_on_task(ParallelTask(id="t1", prompt="simple"))
        assert isinstance(outcome, VotingOutcome)
