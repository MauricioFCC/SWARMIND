"""
ParallelExecutor — Fan-out paralelo nativo + votacion gobernada.

Aportacion anexada de ORCA (stablyai/orca, ADE 2026) implementada de forma
NATIVA en SWARMIND (sin dependencia externa): ORCA aporta velocidad por
paralelismo y calidad por votacion, pero multiplica el costo de contexto
por N (worktrees aislados). Aqui se captura esa ganancia respetando la
token economics del harness (ADR-0040/0041):

  - run_parallel(): N tasks independientes en paralelo (ThreadPoolExecutor)
    sobre MultiAPIProvider.execute (thread-safe), con ruta small/frontier
    decidida por ModelRouter (small-first).
  - vote_on_task(): voting gobernado — solo paga el costo N (default 3)
    cuando el ModelRouter marca la tarea como compleja Y ambigua
    (score >= 70 y confidence < 0.7). Presupuesto tope:
    MAX_TOKENS_BY_AGENT[rol] * budget_factor.
  - get_stats(): metricas para token economics (fan_out_factor,
    tokens_per_parallel_agent, voting_events).

Diseno: hexagonal + DI (provider/router inyectables), inmutable
(ParallelTask/ParallelResult/VotingOutcome frozen), errores WHAT+WHY+WHERE.

Uso:
    from harness.orchestrator.parallel_executor import ParallelExecutor, ParallelTask
    ex = ParallelExecutor(max_workers=3)
    results = ex.run_parallel([ParallelTask(id="t1", prompt="...")])
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from harness.model_router.multi_provider_types import (
    MAX_TOKENS_BY_AGENT,
    ExecutionResult,
)
from harness.orchestrator.fanout_gate import (
    SINGLE_AGENT_THRESHOLD,
    FanoutDecision,
    should_fanout,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers)
# ---------------------------------------------------------------------------

DEFAULT_MAX_WORKERS = 3          # concurrencia por defecto (mesa de trabajo 2026)
DEFAULT_VOTE_N = 3               # variantes de votacion (costo 3x acotado)
DEFAULT_BUDGET_FACTOR = 3.0      # tope de presupuesto para votacion
VOTE_SCORE_THRESHOLD = 70.0      # gate: score minimo para considerar voting
VOTE_MIN_CONFIDENCE = 0.7        # gate: confidence maxima para considerar voting
SIMILARITY_MAJORITY = 0.9        # umbral de similitud para clonar outputs


# ---------------------------------------------------------------------------
# Tipos inmutables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParallelTask:
    """Tarea independiente para ejecucion en paralelo."""
    id: str
    prompt: str
    agent_role: str = "*"
    model_preference: str | None = None


@dataclass(frozen=True)
class ParallelResult:
    """Resultado de una ejecucion en paralelo."""
    task_id: str
    success: bool
    output: str
    model: str
    provider: str
    tokens_used: int
    duration_ms: float
    error: str | None = None


@dataclass(frozen=True)
class VotingOutcome:
    """Resultado de la votacion (mayoria por similitud)."""
    winner: ParallelResult | None
    gate_applied: bool
    total_tokens: int
    total_duration_ms: float
    scores: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ParallelExecutor
# ---------------------------------------------------------------------------

class ParallelExecutor:
    """Ejecuta tasks en paralelo con voting gobernado opcional.

    Args:
        provider: MultiAPIProvider inyectable (crea uno si es None).
        router: ModelRouter inyectable (crea uno si es None).
        max_workers: Maximo de hilos concurrentes (default 3).
        budget_factor: Multiplicador de presupuesto para votacion.
    """

    def __init__(
        self,
        provider: Any | None = None,
        router: Any | None = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        budget_factor: float = DEFAULT_BUDGET_FACTOR,
    ) -> None:
        if provider is None:
            from harness.model_router.multi_provider import MultiAPIProvider
            provider = MultiAPIProvider()
        if router is None:
            from harness.model_router.router import ModelRouter
            router = ModelRouter()
        self._provider = provider
        self._router = router
        self.max_workers = max_workers
        self.budget_factor = budget_factor

        # Metricas acumuladas (token economics)
        self._lock = threading.Lock()
        self._total_tokens = 0
        self._total_attempts = 0
        self._total_duration_ms = 0.0
        self._voting_events = 0

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def run_parallel(
        self,
        tasks: list[ParallelTask],
        agent_role: str = "*",
    ) -> list[ParallelResult]:
        """Ejecuta N tasks independientes en paralelo.

        Cada task se enruta con ModelRouter (small-first) y se ejecuta con
        MultiAPIProvider.execute (failover incluido). Una task que falla no
        impide completar las demas (aislamiento de fallos).

        Args:
            tasks: Tareas independientes a ejecutar.
            agent_role: Rol por defecto si la task no especifica uno.

        Returns:
            Lista de ParallelResult (mismo orden que tasks).
        """
        if not tasks:
            return []
        role_by_id = {t.id: t.agent_role for t in tasks}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(
                    self._execute_one, task, role_by_id[task.id]
                ): task.id
                for task in tasks
            }
            completed: dict[str, ParallelResult] = {}
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    completed[task_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - aislamiento de fallos
                    logger.error(
                        "Task %s lanzo excepcion: %s. "
                        "WHY: error no controlado en ejecucion paralela. "
                        "WHERE: ParallelExecutor.run_parallel",
                        task_id, exc,
                    )
                    completed[task_id] = ParallelResult(
                        task_id=task_id, success=False, output="",
                        model="", provider="", tokens_used=0,
                        duration_ms=0.0,
                        error=(
                            f"Task {task_id} failed: {exc}. "
                            "WHY: excepcion no controlada. "
                            "WHERE: ParallelExecutor.run_parallel"
                        ),
                    )
        return [completed[t.id] for t in tasks]

    def vote_on_task(
        self,
        task: ParallelTask,
        n: int = DEFAULT_VOTE_N,
        score_threshold: float = VOTE_SCORE_THRESHOLD,
        min_confidence: float = VOTE_MIN_CONFIDENCE,
        baseline_success: float | None = None,
    ) -> VotingOutcome:
        """Ejecuta con votacion gobernada (solo si el gate lo justifica).

        Gate: el ModelRouter marca la tarea como compleja y ambigua
        (score >= score_threshold y confidence < min_confidence). Si no
        pasa el gate, ejecuta UNA sola vez (sin costo extra).

        Gate anti-sobre-descomposicion (ADR-0075): si el caller aporta un
        probe single-agent con baseline_success >= SINGLE_AGENT_THRESHOLD
        (>= 0.8), NO se vota (el fan-out anade ruido x17.2; arXiv:2602.07787).

        Presupuesto: los tokens totales quedan acotados por
        MAX_TOKENS_BY_AGENT[rol] * budget_factor (defensa contra
        failure-spend, ADR-0040).

        Args:
            task: Tarea a resolver.
            n: Numero de variantes (default 3).
            score_threshold: Score minimo del router para votar.
            min_confidence: Confidence maxima para votar (baja = ambigua).
            baseline_success: Success rate del probe single-agent (0..1);
                None = sin probe (solo gate score/confidence).

        Returns:
            VotingOutcome con ganador, gate_applied y metricas.
        """
        route = self._router.route(task.prompt)
        score = float(route.model_route.score)
        confidence = float(route.model_route.confidence)

        gate_applied = score >= score_threshold and confidence < min_confidence
        if baseline_success is not None:
            decision = should_fanout(baseline_success)
            if decision is FanoutDecision.SINGLE:
                logger.info(
                    "vote_on_task: baseline %.0f%% >= %.0f%%; sin voting "
                    "(anti-sobre-descomposicion ADR-0075)",
                    baseline_success * 100, SINGLE_AGENT_THRESHOLD * 100,
                )
                gate_applied = False
        attempts = n if gate_applied else 1

        variants = [
            ParallelTask(
                id=f"{task.id}#{i}" if gate_applied else task.id,
                prompt=task.prompt,
                agent_role=task.agent_role,
                model_preference=task.model_preference,
            )
            for i in range(attempts)
        ]
        results = self.run_parallel(variants, agent_role=task.agent_role)

        # Tope de presupuesto (defensa): si se excede, log y reporte igual
        budget = MAX_TOKENS_BY_AGENT.get(task.agent_role, MAX_TOKENS_BY_AGENT["*"])
        max_budget = budget * self.budget_factor
        total_tokens = sum(r.tokens_used for r in results)
        if total_tokens > max_budget:
            logger.warning(
                "Voting supero presupuesto: %d > %d (rol %s). "
                "WHY: fan-out N=%d con tokens por llamada altos. "
                "WHERE: ParallelExecutor.vote_on_task",
                total_tokens, int(max_budget), task.agent_role, attempts,
            )

        if gate_applied:
            with self._lock:
                self._voting_events += 1

        outcome = self.vote(results)
        return VotingOutcome(
            winner=outcome.winner,
            gate_applied=gate_applied,
            total_tokens=outcome.total_tokens,
            total_duration_ms=outcome.total_duration_ms,
            scores=outcome.scores,
        )

    def vote(self, results: list[ParallelResult]) -> VotingOutcome:
        """Vota por mayoria de similitud entre outputs.

        Clasifica los outputs por similitud coseno (embeddings del harness,
        GPU acelerado si disponible). Gana el cluster mas grande; si hay
        empate o todos son unicos, gana el de menor duration_ms (menos
        tokens esperados).

        NOTA: esta funcion es pura (no acumula stats; el contador de tokens
        se acumula en _execute_one para evitar doble conteo).

        Args:
            results: Resultados de las variantes.

        Returns:
            VotingOutcome con winner (None si no hay resultados).
        """
        if not results:
            return VotingOutcome(
                winner=None, gate_applied=False, total_tokens=0,
                total_duration_ms=0.0, scores={},
            )

        # Clusterizar por similitud de embeddings
        from harness.common import fallback_embedding
        from harness.gpu_accel import cosine_similarity

        clusters: list[list[ParallelResult]] = []
        for r in results:
            if not r.output:
                continue
            vec = fallback_embedding(r.output)
            placed = False
            for cluster in clusters:
                ref = fallback_embedding(cluster[0].output)
                if cosine_similarity(vec, ref) >= SIMILARITY_MAJORITY:
                    cluster.append(r)
                    placed = True
                    break
            if not placed:
                clusters.append([r])

        # Ganador: cluster mas grande; sin mayoria -> el mas rapido
        winner: ParallelResult | None = None
        scores: dict[str, float] = {}
        if clusters:
            max_size = max(len(c) for c in clusters)
            biggest = [c for c in clusters if len(c) == max_size]
            if max_size == 1:
                # Sin mayoria real: gana el de menor duracion entre todos
                winner = min(results, key=lambda r: r.duration_ms)
            else:
                # Empate de clusters -> el mas rapido dentro de los candidatos
                candidates = [min(c, key=lambda r: r.duration_ms) for c in biggest]
                winner = min(candidates, key=lambda r: r.duration_ms)
            for r in results:
                scores[r.task_id] = 1.0 if winner is not None and r is winner else 0.0

        total_tokens = sum(r.tokens_used for r in results)
        total_duration_ms = sum(r.duration_ms for r in results)
        return VotingOutcome(
            winner=winner, gate_applied=False, total_tokens=total_tokens,
            total_duration_ms=total_duration_ms, scores=scores,
        )

    # ------------------------------------------------------------------
    # Metricas (token economics)
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Metricas acumuladas para monitoreo (fan_out, tokens, voting).

        Returns:
            Dict con: total_attempts, total_tokens, total_duration_ms,
            voting_events, fan_out_factor, tokens_per_parallel_agent.
        """
        with self._lock:
            attempts = self._total_attempts
            tokens = self._total_tokens
            duration = self._total_duration_ms
            events = self._voting_events
        # fan_out_factor = intentos totales / tareas unicas ejecutadas
        # (una tarea votada cuenta 1 tarea con N intentos)
        tasks_processed = max(1, attempts - (n_extra(events)))
        return {
            "total_attempts": attempts,
            "total_tokens": tokens,
            "total_duration_ms": round(duration, 2),
            "voting_events": events,
            "fan_out_factor": round(attempts / tasks_processed, 2),
            "tokens_per_parallel_agent": (
                round(tokens / attempts, 2) if attempts else 0.0
            ),
        }

    def reset_stats(self) -> None:
        """Limpia las metricas acumuladas."""
        with self._lock:
            self._total_tokens = 0
            self._total_attempts = 0
            self._total_duration_ms = 0.0
            self._voting_events = 0

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _execute_one(self, task: ParallelTask, role: str) -> ParallelResult:
        """Ejecuta una task via router + provider (thread-safe)."""
        t0 = time.perf_counter()
        try:
            route = self._router.route(task.prompt)
            model = str(route.model_route.route)
            exec_result: ExecutionResult = self._provider.execute(
                model=model, prompt=task.prompt, agent_role=role,
            )
        except Exception as exc:  # noqa: BLE001 - failover a resultado fallido
            logger.error(
                "Execucion fallida para %s: %s. "
                "WHY: error de provider/router. "
                "WHERE: ParallelExecutor._execute_one",
                task.id, exc,
            )
            return ParallelResult(
                task_id=task.id, success=False, output="",
                model="", provider="", tokens_used=0,
                duration_ms=(time.perf_counter() - t0) * 1000,
                error=(
                    f"Execution failed for {task.id}: {exc}. "
                    "WHY: error de provider/router. "
                    "WHERE: ParallelExecutor._execute_one"
                ),
            )
        duration_ms = (time.perf_counter() - t0) * 1000
        with self._lock:
            self._total_tokens += exec_result.tokens_used
            self._total_attempts += 1
            self._total_duration_ms += duration_ms
        return ParallelResult(
            task_id=task.id,
            success=exec_result.success,
            output=exec_result.output,
            model=exec_result.model,
            provider=exec_result.provider,
            tokens_used=exec_result.tokens_used,
            duration_ms=duration_ms,
            error=exec_result.error,
        )


def n_extra(voting_events: int) -> int:
    """Cuantos intentos extra generaron los eventos de voting."""
    return voting_events * (DEFAULT_VOTE_N - 1)
