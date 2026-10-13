"""Tests de la ruta async de debate (consensus paralelo PaCoRe).

Cubre:
  - ``_run_async_dispatch``: pasa el ``context`` correcto a ``dispatch_fn``
    con la firma real ``DispatchFn(agent, task, context)``.
  - ``_execute_consensus_async``: convergencia temprana, confianza derivada
    del acuerdo real, umbral configurable y tolerancia a fallos de dispatch.
  - ``DebateOrchestrator.debate_async``: ruta async publica (consensus
    paralelo; critique/deliberation via ``asyncio.to_thread``).
  - ``DebateRunner.run_debate_async`` y ``TaskOrchestrator.run_debate_async``.

Sin LLM real: todos los dispatchers son mocks deterministas. La ruta sync
(``DebateOrchestrator.debate``) no se modifica y sigue cubierta por
``test_debate.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.orchestrator.debate_orchestrator import (
    CONVERGENCE_THRESHOLD,
    DEFAULT_CONSENSUS_CONFIDENCE,
    DebateOrchestrator,
    DebateResult,
    DebateStrategy,
)

# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator() -> DebateOrchestrator:
    """DebateOrchestrator en memoria (sin vector store)."""
    return DebateOrchestrator(vector_store=None)


class _FakeSubtask:
    """Subtask minima con solo el atributo ``agent`` usado por DebateRunner."""

    def __init__(self, agent: str) -> None:
        self.agent = agent


class _FakePlan:
    """Plan minimo con la lista de subtasks."""

    def __init__(self, agents: list[str]) -> None:
        self.subtasks = [_FakeSubtask(a) for a in agents]


class _FakeSession:
    """Sesion minima con un plan de subtasks."""

    def __init__(self, agents: list[str]) -> None:
        self.plan = _FakePlan(agents)


def _capturing_dispatch(records: list[tuple[str, str, dict[str, Any]]]):
    """Factory de dispatch que registra ``(agent, task, context)`` y responde igual."""

    def _dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
        records.append((agent, task, context))
        return "respuesta consensuada"

    return _dispatch


# ---------------------------------------------------------------------------
# _run_async_dispatch: el context DEBE llegar a dispatch_fn
# ---------------------------------------------------------------------------


class TestRunAsyncDispatch:
    """Verifica el fix del bug: dispatch_fn recibe (agent, task, context)."""

    async def test_pasa_context_a_dispatch_fn(self, orchestrator):
        """dispatch_fn de 3 argumentos recibe el context sin TypeError."""
        captured: dict[str, Any] = {}

        def _dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
            captured["agent"] = agent
            captured["task"] = task
            captured["context"] = context
            return "ok"

        context = {"phase": "independent_answer", "round": 1}
        output = await orchestrator._run_async_dispatch(
            "builder", "tarea x", _dispatch, context,
        )

        assert output == "ok"
        assert captured["agent"] == "builder"
        assert captured["task"] == "tarea x"
        assert captured["context"] == context


# ---------------------------------------------------------------------------
# _execute_consensus_async
# ---------------------------------------------------------------------------


class TestConsensusAsync:
    """Verifica la estrategia de consenso paralela."""

    async def test_pasa_context_en_cada_dispatch(self, orchestrator):
        """Cada agente recibe un context con strategy/round/phase."""
        records: list[tuple[str, str, dict[str, Any]]] = []
        await orchestrator._execute_consensus_async(
            task="elegir stack",
            agents=["builder", "scientist"],
            max_rounds=1,
            dispatch_fn=_capturing_dispatch(records),
            session_id="s-ctx",
        )

        assert len(records) == 2
        for agent, task, context in records:
            assert agent in ("builder", "scientist")
            assert task == "elegir stack"
            assert isinstance(context, dict)
            assert context["strategy"] == DebateStrategy.CONSENSUS.value
            assert context["round"] == 1
            assert context["phase"] == "independent_answer"
            assert "previous_outputs" in context

    async def test_converge_temprano_y_confianza_derivada(self, orchestrator):
        """Acuerdo total -> converge en ronda 1 con confianza 1.0 (derivada)."""
        result = await orchestrator._execute_consensus_async(
            task="tarea",
            agents=["builder", "scientist", "guardian"],
            max_rounds=5,
            dispatch_fn=lambda a, t, c: "respuesta identica para todos",
            session_id="s-conv",
        )

        assert isinstance(result, DebateResult)
        assert len(result.rounds) == 1  # early stop: agreement 1.0 > 0.9
        assert result.confidence == pytest.approx(1.0)
        assert result.agent_agreement == pytest.approx(1.0)
        assert result.metadata["async"] is True

    async def test_no_hardcode_confianza_baja(self, orchestrator):
        """Desacuerdo total -> confianza derivada baja (no 0.85 fijo)."""
        respuestas = {"builder": "rust", "scientist": "python", "guardian": "golang"}

        result = await orchestrator._execute_consensus_async(
            task="elegir stack",
            agents=["builder", "scientist", "guardian"],
            max_rounds=1,
            dispatch_fn=lambda a, t, c: respuestas[a],
            session_id="s-low",
        )

        assert result.confidence < DEFAULT_CONSENSUS_CONFIDENCE
        assert result.confidence == pytest.approx(result.agent_agreement)

    async def test_umbral_convergencia_configurable(self, orchestrator):
        """Con threshold=1.0 nunca se supera -> usa todas las rondas pedidas."""
        result = await orchestrator._execute_consensus_async(
            task="tarea",
            agents=["builder", "scientist"],
            max_rounds=3,
            dispatch_fn=lambda a, t, c: "respuesta identica",
            session_id="s-th",
            convergence_threshold=1.0,
        )

        assert len(result.rounds) == 3
        assert result.metadata["convergence_threshold"] == 1.0

    async def test_fallback_confidence_sin_rondas(self, orchestrator):
        """max_rounds=0 -> sin rondas; confianza = DEFAULT_CONSENSUS_CONFIDENCE."""
        result = await orchestrator._execute_consensus_async(
            task="tarea",
            agents=["builder", "scientist"],
            max_rounds=0,
            dispatch_fn=lambda a, t, c: "respuesta",
            session_id="s-empty",
        )

        assert result.rounds == []
        assert result.final_answer == ""
        assert result.confidence == pytest.approx(DEFAULT_CONSENSUS_CONFIDENCE)

    async def test_tolera_dispatch_que_falla(self, orchestrator):
        """Un dispatch que lanza excepcion no rompe el consensus (partial)."""
        def _flaky(agent: str, task: str, context: dict[str, Any]) -> str:
            if agent == "scientist":
                raise RuntimeError("dispatch simulado caido")
            return "respuesta valida"

        result = await orchestrator._execute_consensus_async(
            task="tarea",
            agents=["builder", "scientist", "guardian"],
            max_rounds=1,
            dispatch_fn=_flaky,
            session_id="s-flaky",
        )

        assert "scientist" not in result.rounds[0].agent_outputs
        assert "builder" in result.rounds[0].agent_outputs
        assert "guardian" in result.rounds[0].agent_outputs
        assert result.final_answer != ""

    async def test_no_cuelga(self, orchestrator):
        """La ruta async completa dentro de un timeout acotado."""
        result = await asyncio.wait_for(
            orchestrator._execute_consensus_async(
                task="tarea",
                agents=["builder", "scientist"],
                max_rounds=2,
                dispatch_fn=lambda a, t, c: "respuesta estable",
                session_id="s-timeout",
            ),
            timeout=5.0,
        )
        assert result.final_answer != ""

    async def test_final_answer_es_sintesis(self, orchestrator):
        """final_answer proviene de la sintesis de la ultima ronda."""
        result = await orchestrator._execute_consensus_async(
            task="tarea",
            agents=["builder", "scientist"],
            max_rounds=1,
            dispatch_fn=lambda a, t, c: f"respuesta de {a}",
            session_id="s-final",
        )
        assert result.final_answer == result.rounds[-1].synthesis


# ---------------------------------------------------------------------------
# DebateOrchestrator.debate_async (ruta async publica)
# ---------------------------------------------------------------------------


class TestDebateAsyncPublic:
    """Verifica el metodo publico debate_async."""

    async def test_consensus_usa_ruta_paralela(self, orchestrator):
        """CONSENSUS async marca metadata['async']=True (ruta paralela)."""
        result = await orchestrator.debate_async(
            task="decidir enfoque",
            agents=["builder", "scientist"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=lambda a, t, c: "respuesta comun",
        )
        assert result.strategy == DebateStrategy.CONSENSUS
        assert result.metadata.get("async") is True

    async def test_critique_delega_en_thread(self, orchestrator):
        """CRITIQUE async delega en la ruta sync (no marca async=True)."""
        result = await orchestrator.debate_async(
            task="revisar diseno",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CRITIQUE,
            max_rounds=2,
            dispatch_fn=lambda a, t, c: "respuesta",
        )
        assert result.strategy == DebateStrategy.CRITIQUE
        assert result.metadata.get("async") is None

    async def test_validacion_tarea_vacia(self, orchestrator):
        """Tarea vacia -> ValueError (misma validacion que la ruta sync)."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await orchestrator.debate_async(
                task="",
                agents=["builder", "scientist"],
                dispatch_fn=lambda a, t, c: "x",
            )

    async def test_validacion_pocos_agentes(self, orchestrator):
        """Menos de 2 agentes -> ValueError."""
        with pytest.raises(ValueError, match="at least 2 agents"):
            await orchestrator.debate_async(
                task="tarea",
                agents=["builder"],
                dispatch_fn=lambda a, t, c: "x",
            )


# ---------------------------------------------------------------------------
# DebateRunner.run_debate_async
# ---------------------------------------------------------------------------


class TestDebateRunnerAsync:
    """Verifica la ruta async del DebateRunner."""

    async def test_run_debate_async_ok(self):
        """run_debate_async produce un DebateResult async valido."""
        from harness.orchestrator.debate_runner import DebateRunner

        session_ctx = MagicMock()
        session_ctx.get_session.return_value = _FakeSession(["builder", "scientist"])
        runner = DebateRunner(store=None, session_ctx=session_ctx, bus=MagicMock())

        result = await runner.run_debate_async(
            session_id="sess-runner",
            task="debate runner async",
            agents=["builder", "scientist"],
            strategy="consensus",
            dispatch_fn=lambda a, t, c: "respuesta consensuada",
        )

        assert isinstance(result, DebateResult)
        assert result.metadata.get("async") is True
        assert result.final_answer != ""

    async def test_run_debate_async_extrae_agentes(self):
        """agents=None extrae los agentes del plan (excluye coordinator)."""
        from harness.orchestrator.debate_runner import DebateRunner

        session_ctx = MagicMock()
        session_ctx.get_session.return_value = _FakeSession(
            ["coordinator", "builder", "scientist"]
        )
        runner = DebateRunner(store=None, session_ctx=session_ctx, bus=MagicMock())

        result = await runner.run_debate_async(
            session_id="sess-extract",
            task="debate runner async",
            dispatch_fn=lambda a, t, c: "respuesta",
        )

        assert set(result.metadata["agents"]) == {"builder", "scientist"}

    async def test_run_debate_async_session_no_encontrada(self):
        """Sesion inexistente -> ValueError."""
        from harness.orchestrator.debate_runner import DebateRunner

        session_ctx = MagicMock()
        session_ctx.get_session.return_value = None
        runner = DebateRunner(store=None, session_ctx=session_ctx, bus=MagicMock())

        with pytest.raises(ValueError, match="not found"):
            await runner.run_debate_async("missing", "tarea")

    def test_run_debate_sync_sigue_funcionando(self):
        """Backward-compat: la ruta sync de DebateRunner no cambia."""
        from harness.orchestrator.debate_runner import DebateRunner

        session_ctx = MagicMock()
        session_ctx.get_session.return_value = _FakeSession(["builder", "scientist"])
        runner = DebateRunner(store=None, session_ctx=session_ctx, bus=MagicMock())

        result = runner.run_debate(
            session_id="sess-sync",
            task="debate runner sync",
            agents=["builder", "scientist"],
            strategy="consensus",
            dispatch_fn=lambda a, t, c: "respuesta",
        )

        assert isinstance(result, DebateResult)
        assert result.metadata.get("async") is None


# ---------------------------------------------------------------------------
# TaskOrchestrator.run_debate_async
# ---------------------------------------------------------------------------


class TestTaskOrchestratorAsync:
    """Verifica la ruta async expuesta por TaskOrchestrator."""

    async def test_run_debate_async_delega(self):
        """run_debate_async delega en la ruta paralela del DebateRunner."""
        from harness.orchestrator.task_orchestrator import TaskOrchestrator

        orch = TaskOrchestrator()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = _FakeSession(
            ["builder", "scientist"]
        )

        result = await orch.run_debate_async(
            session_id="sess-task",
            task="debate async task orchestrator",
            agents=["builder", "scientist"],
            strategy="consensus",
            dispatch_fn=lambda a, t, c: "respuesta consensuada",
        )

        assert isinstance(result, DebateResult)
        assert result.metadata.get("async") is True

    async def test_run_debate_sync_compat(self):
        """Backward-compat: TaskOrchestrator.run_debate (sync-in-thread) intacto."""
        from harness.orchestrator.task_orchestrator import TaskOrchestrator

        orch = TaskOrchestrator()
        orch._session_ctx = MagicMock()
        orch._session_ctx.get_session.return_value = _FakeSession(
            ["builder", "scientist"]
        )

        result = await orch.run_debate(
            session_id="sess-task-sync",
            task="debate sync task orchestrator",
            agents=["builder", "scientist"],
            strategy="consensus",
            dispatch_fn=lambda a, t, c: "respuesta",
        )

        assert isinstance(result, DebateResult)
        assert result.metadata.get("async") is None


# ---------------------------------------------------------------------------
# Constantes nombrables (sin magic numbers)
# ---------------------------------------------------------------------------


class TestNamedConstants:
    """Verifica que los hardcodes quedaron como constantes nombradas."""

    def test_default_consensus_confidence(self):
        """DEFAULT_CONSENSUS_CONFIDENCE preserva el valor 0.85."""
        assert DEFAULT_CONSENSUS_CONFIDENCE == pytest.approx(0.85)

    def test_convergence_threshold(self):
        """CONVERGENCE_THRESHOLD preserva el valor 0.9."""
        assert CONVERGENCE_THRESHOLD == pytest.approx(0.9)
