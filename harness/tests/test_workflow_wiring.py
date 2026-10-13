"""Tests TDD del cableado de frontera del flujo real (gap #1 de integracion).

WHAT: fija el contrato del cableado (con DI y feature flags) de tres
componentes de frontera que existian standalone y no estaban unidos al
pipeline real: ``TokenTelemetry`` (telemetria activa por defecto, opt-out),
``PipelineRouter`` (cascada de triage, opt-in) y ``LibraryDriftManager``
(retiro por outcome, inyectado en ``AgentDispatcher`` desde ``_dispatch_task``).
WHY: sin un call site real la telemetria no mide, la cascada no clasifica y el
tracker de utilidad nunca acumula evidencia (el gap #1 segun el mapa de
workflows). WHERE: entry real ``TaskOrchestrator.process_message`` +
``harness/run_support._dispatch_task``.

Criterios (AAA, 1 test = 1 criterio):
  (a) TaskOrchestrator sin DI activa telemetria por defecto y registra
      ``record_usage(role="orchestrator")`` en el dispatch del plan.
  (b) ``SWARMIND_TELEMETRY_DISABLE=1`` -> ``_telemetry is None`` (opt-out).
  (c) ``SWARMIND_PIPELINE_ROUTER=1`` -> se usa ``PipelineRouter.route``;
      sin la env (o ``=0``) -> comportamiento legacy (``TaskPlanner``).
  (d) ``_dispatch_task`` cablea ``drift_manager`` + ``telemetry`` en
      ``AgentDispatcher`` y cierra el outcome del skill (hook best-effort).
  (e) guarda de mutacion: el flag de telemetria es discriminante.

0 LLM real: ``MagicMock`` para router, planner y dispatcher (NF-3).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from harness.evolve_loop.library_drift import LibraryDriftManager
from harness.observability.token_telemetry import TokenTelemetry
from harness.orchestrator.task_orchestrator import TaskOrchestrator
from harness.orchestrator.task_orchestrator.wiring import (
    ENV_PIPELINE_ROUTER,
    ENV_TELEMETRY_DISABLE,
    ORCHESTRATOR_ROLE,
)

#: Mensaje largo, sin keywords de continuacion y sin duplicarse (dedup).
_TASK = "implementar endpoint REST de integracion con cableado DI y evidencia"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _routing_decision_mock() -> MagicMock:
    """Construye una decision de ruteo simulada (shape de ``RoutingDecision``).

    Returns:
        ``MagicMock`` con los campos que ``process_message`` inspecciona.
    """
    decision = MagicMock()
    decision.pipeline = "standard"
    decision.complexity = 3
    decision.source = "slm"
    decision.intent = "coding"
    decision.prompt_blocks = []
    decision.telemetry = {}
    return decision


def _orch_result_mock() -> MagicMock:
    """Construye un ``OrchestratorResult`` simulado para ``_dispatch_task``.

    Returns:
        ``MagicMock`` con los atributos consumidos por ``_dispatch_task``.
    """
    result = MagicMock()
    result.target_agent = "builder"
    result.session_id = "s1"
    result.session_status = "ok"
    result.current_level = []
    result.previous_results = []
    result.communication_log = []
    result.is_complete = False
    return result


# ===========================================================================
# (a) Telemetria activa por defecto
# ===========================================================================


class TestTelemetryEnabledByDefault:
    """El orquestador activa la telemetria por defecto y registra el uso."""

    def test_default_telemetry_is_a_token_telemetry(self, vector_store) -> None:
        """Sin DI, ``_telemetry`` es un ``TokenTelemetry`` (default ON)."""
        orch = TaskOrchestrator(vector_store=vector_store)

        assert isinstance(orch._telemetry, TokenTelemetry)

    async def test_process_message_records_orchestrator_usage(self, vector_store) -> None:
        """``process_message`` registra usage con role='orchestrator' (spy)."""
        orch = TaskOrchestrator(vector_store=vector_store)
        with patch.object(
            orch._telemetry, "record_usage", wraps=orch._telemetry.record_usage
        ) as spy:
            await orch.process_message(_TASK)

        spy.assert_called_once()
        assert spy.call_args.args[0] == ORCHESTRATOR_ROLE
        assert spy.call_args.kwargs["cached"] >= 0
        assert spy.call_args.kwargs["input"] >= 0
        assert spy.call_args.kwargs["output"] >= 1

    def test_injected_telemetry_takes_precedence(self, vector_store) -> None:
        """La telemetria inyectada por DI se respeta (no se reemplaza)."""
        injected = TokenTelemetry()
        orch = TaskOrchestrator(vector_store=vector_store, telemetry=injected)

        assert orch._telemetry is injected


# ===========================================================================
# (b) Opt-out por variable de entorno
# ===========================================================================


class TestTelemetryOptOut:
    """``SWARMIND_TELEMETRY_DISABLE=1`` desactiva la telemetria."""

    def test_disable_env_sets_telemetry_none(self, monkeypatch, vector_store) -> None:
        """Con la env de disable, ``_telemetry`` queda en ``None``."""
        monkeypatch.setenv(ENV_TELEMETRY_DISABLE, "1")

        orch = TaskOrchestrator(vector_store=vector_store)

        assert orch._telemetry is None

    async def test_disabled_does_not_record(self, monkeypatch, vector_store) -> None:
        """Con la telemetria apagada, ``process_message`` no falla ni registra."""
        monkeypatch.setenv(ENV_TELEMETRY_DISABLE, "1")
        orch = TaskOrchestrator(vector_store=vector_store)

        result = await orch.process_message(_TASK)

        assert orch._telemetry is None
        assert result.session_id != "error"


# ===========================================================================
# (c) PipelineRouter opt-in
# ===========================================================================


class TestPipelineRouterWiring:
    """La cascada de ``PipelineRouter`` se usa solo con la env activada."""

    async def test_router_enabled_classifies_message(
        self, monkeypatch, vector_store
    ) -> None:
        """``SWARMIND_PIPELINE_ROUTER=1`` -> ``route`` clasifica el mensaje."""
        monkeypatch.setenv(ENV_PIPELINE_ROUTER, "1")
        router = MagicMock()
        router.route.return_value = _routing_decision_mock()
        orch = TaskOrchestrator(vector_store=vector_store, pipeline_router=router)

        await orch.process_message(_TASK)

        router.route.assert_called_once_with(_TASK)

    async def test_router_disabled_uses_legacy_planner(
        self, monkeypatch, vector_store
    ) -> None:
        """Sin la env, el router NO se consulta y manda el ``TaskPlanner``."""
        monkeypatch.delenv(ENV_PIPELINE_ROUTER, raising=False)
        router = MagicMock()
        orch = TaskOrchestrator(vector_store=vector_store, pipeline_router=router)
        with patch.object(
            orch._planner, "decompose", wraps=orch._planner.decompose
        ) as planner_spy:
            await orch.process_message(_TASK)

        router.route.assert_not_called()
        planner_spy.assert_called_once_with(_TASK)

    async def test_router_env_zero_uses_legacy_planner(
        self, monkeypatch, vector_store
    ) -> None:
        """``SWARMIND_PIPELINE_ROUTER=0`` explicito -> comportamiento legacy."""
        monkeypatch.setenv(ENV_PIPELINE_ROUTER, "0")
        router = MagicMock()
        orch = TaskOrchestrator(vector_store=vector_store, pipeline_router=router)
        with patch.object(
            orch._planner, "decompose", wraps=orch._planner.decompose
        ) as planner_spy:
            await orch.process_message(_TASK)

        router.route.assert_not_called()
        planner_spy.assert_called_once_with(_TASK)


# ===========================================================================
# (d) Cableado de drift + telemetry en _dispatch_task
# ===========================================================================


class TestDispatchTaskWiring:
    """``_dispatch_task`` inyecta ``LibraryDriftManager`` y telemetria."""

    def test_constructor_receives_drift_and_telemetry(self) -> None:
        """El ``AgentDispatcher`` recibe drift_manager y telemetry (spy ctor)."""
        from harness.run_support import _dispatch_task

        store = MagicMock()
        dispatcher = MagicMock()

        async def fake_dispatch(target, task, plan_context=None):
            return {
                "used_skill": True,
                "skill_name": "rest-api",
                "rag_context": {},
                "execution_plan": None,
            }

        dispatcher.dispatch_async = fake_dispatch

        with patch(
            "harness.orchestrator.agent_dispatcher.AgentDispatcher",
            return_value=dispatcher,
        ) as ctor:
            routing = _dispatch_task(store, _orch_result_mock(), "mi tarea")

        assert routing == "builder"
        kwargs = ctor.call_args.kwargs
        assert kwargs["vector_store"] is store
        assert isinstance(kwargs["drift_manager"], LibraryDriftManager)
        assert kwargs["telemetry"] is not None

    def test_records_skill_outcome_when_skill_present(self) -> None:
        """Con skill en el resultado, cierra el outcome (best-effort)."""
        from harness.run_support import _dispatch_task

        dispatcher = MagicMock()

        async def fake_dispatch(target, task, plan_context=None):
            return {
                "used_skill": True,
                "skill_name": "rest-api",
                "rag_context": {},
                "execution_plan": None,
            }

        dispatcher.dispatch_async = fake_dispatch

        with patch(
            "harness.orchestrator.agent_dispatcher.AgentDispatcher",
            return_value=dispatcher,
        ):
            _dispatch_task(MagicMock(), _orch_result_mock(), "mi tarea")

        dispatcher.record_skill_outcome.assert_called_once_with(
            "rest-api", success=True
        )

    def test_no_outcome_call_without_skill(self) -> None:
        """Sin skill recuperado, el hook NO fabrica un outcome."""
        from harness.run_support import _dispatch_task

        dispatcher = MagicMock()

        async def fake_dispatch(target, task, plan_context=None):
            return {
                "used_skill": False,
                "skill_name": "",
                "rag_context": {},
                "execution_plan": None,
            }

        dispatcher.dispatch_async = fake_dispatch

        with patch(
            "harness.orchestrator.agent_dispatcher.AgentDispatcher",
            return_value=dispatcher,
        ):
            _dispatch_task(MagicMock(), _orch_result_mock(), "mi tarea")

        dispatcher.record_skill_outcome.assert_not_called()


# ===========================================================================
# (e) Guarda de mutacion: el flag de telemetria es discriminante
# ===========================================================================


class TestTelemetryMutationGuard:
    """El flag de telemetria debe ser load-bearing (no decorativo)."""

    def test_flag_is_load_bearing(self, monkeypatch, vector_store) -> None:
        """Default ON y disable OFF: quitar el flag rompe este assert.

        Si un mutante borra la rama 'default -> TokenTelemetry()', el assert
        de default falla; si borra la rama de la env, el assert de disable
        falla. Ambos discrminan el comportamiento.
        """
        monkeypatch.delenv(ENV_TELEMETRY_DISABLE, raising=False)
        enabled = TaskOrchestrator(vector_store=vector_store)

        monkeypatch.setenv(ENV_TELEMETRY_DISABLE, "1")
        disabled = TaskOrchestrator(vector_store=vector_store)

        assert enabled._telemetry is not None
        assert disabled._telemetry is None

    def test_env_constants_are_stable(self) -> None:
        """Los nombres de las env son contrato estable (sin magic strings)."""
        assert ENV_TELEMETRY_DISABLE == "SWARMIND_TELEMETRY_DISABLE"
        assert ENV_PIPELINE_ROUTER == "SWARMIND_PIPELINE_ROUTER"
        assert ORCHESTRATOR_ROLE == "orchestrator"
