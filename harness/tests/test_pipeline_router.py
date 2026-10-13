"""Tests TDD para PipelineRouter — integracion del triage SLM + cascada (FR-1).

RED primero (ADR-0103, WS-A/WS-C -> pipeline real): fija el contrato de
``PipelineRouter``/``RoutingDecision``/``TelemetryGate`` ANTES de la
implementacion en ``harness/orchestrator/pipeline_router.py``.

Cascada de frontera (RouteLLM/cascade 2026): clasificador barato (triage SLM)
decide primero; solo en el caso "timido" (complexity == 3) se consulta el
``DifficultyRouter`` heuristico para desempatar, y solo entonces la fuente es
``"fallback"``.

Criterios (AAA, 1 test = 1 criterio):
  (a) complexity <= 2 -> pipeline small (SHALLOW), source "slm", sin fallback.
  (b) complexity == 3 -> consulta el fallback; source "fallback".
  (c) complexity >= 4 -> pipeline frontier (DEEP), source "slm".
  (d) triage lanza -> fallback directo, source "fallback", NUNCA lanza.
  (e) telemetria: ``record_usage`` invocada con role "router".
  (f) ``TelemetryGate.check``: 0.9 -> ok; 0.5 -> cache-buster.
  (g) mutacion: la rama "timido -> fallback" es discriminante.
  (h) ``prompt_blocks`` en orden canonico (tools antes que dynamic).

0 LLM real: los callables son ``MagicMock`` (NF-3, determinismo).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from harness.observability.token_telemetry import TokenTelemetry
from harness.orchestrator.agent_dispatcher import AgentDispatcher
from harness.orchestrator.difficulty_router import (
    ComplexityFeatures,
    ComplexityLevel,
    PipelineType,
)
from harness.orchestrator.difficulty_router import (
    RoutingDecision as DifficultyRoutingDecision,
)
from harness.orchestrator.pipeline_router import (
    FRONTIER_COMPLEXITY,
    SMALL_COMPLEXITY,
    TENTATIVE_COMPLEXITY,
    PipelineRouter,
    TelemetryGate,
)
from harness.orchestrator.prompt_cache_shape import ORDER
from harness.orchestrator.triage_slm import TriageResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _triage_result(complexity: int, intent: str = "task") -> TriageResult:
    """Construye un ``TriageResult`` determinista.

    Args:
        complexity: Complejidad 1..5 a simular.
        intent: Intencion asociada.

    Returns:
        ``TriageResult`` con ``raw`` vacio.
    """
    return TriageResult(intent=intent, complexity=complexity, raw="")


def _router_decision(level: ComplexityLevel, pipeline: PipelineType) -> DifficultyRoutingDecision:
    """Construye un ``DifficultyRouter.RoutingDecision`` determinista.

    Args:
        level: Nivel de complejidad heuristico.
        pipeline: Pipeline seleccionado por la heuristica.

    Returns:
        ``RoutingDecision`` del ``difficulty_router`` listo para inyectar.
    """
    return DifficultyRoutingDecision(
        message="t",
        complexity=level,
        pipeline=pipeline,
        score=0.9,
        features=ComplexityFeatures(),
    )


def _triage_mock(complexity: int) -> MagicMock:
    """Crea un mock de triage que devuelve ``complexity``.

    Args:
        complexity: Complejidad simulada del SLM.

    Returns:
        ``MagicMock`` cuyo ``triage`` retorna un ``TriageResult`` fijo.
    """
    triage = MagicMock()
    triage.triage.return_value = _triage_result(complexity)
    return triage


# ===========================================================================
# (a) complexity <= 2 -> small pipeline (SHALLOW)
# ===========================================================================


class TestSmallComplexity:
    """Complejidad trivial/simple: pipeline small sin consultar el fallback."""

    def test_complexity_1_routes_small_without_fallback(self) -> None:
        """complexity=1 -> SHALLOW, source 'slm' y fallback NO consultado."""
        triage = _triage_mock(1)
        fallback = MagicMock()
        router = PipelineRouter(triage=triage, fallback_router=fallback, telemetry=TokenTelemetry())

        decision = router.route("saluda al usuario")

        assert decision.pipeline == PipelineType.SHALLOW
        assert decision.source == "slm"
        assert decision.complexity == 1
        fallback.route.assert_not_called()

    def test_complexity_boundary_two_routes_small(self) -> None:
        """Borde superior de SMALL_COMPLEXITY (2) -> SHALLOW, sin fallback."""
        triage = _triage_mock(SMALL_COMPLEXITY)
        fallback = MagicMock()
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("tarea simple")

        assert decision.pipeline == PipelineType.SHALLOW
        assert decision.source == "slm"
        fallback.route.assert_not_called()


# ===========================================================================
# (b) complexity == 3 -> desempate por el fallback heuristico
# ===========================================================================


class TestTentativeComplexity:
    """Complejidad timida (3): se consulta el ``DifficultyRouter``."""

    def test_tentative_consults_fallback_very_complex(self) -> None:
        """Fallback VERY_COMPLEX -> DEEP, complexity 5 y source 'fallback'."""
        triage = _triage_mock(TENTATIVE_COMPLEXITY)
        fallback = MagicMock()
        fallback.route.return_value = _router_decision(
            ComplexityLevel.VERY_COMPLEX, PipelineType.DEEP
        )
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("tarea ambigua")

        assert decision.source == "fallback"
        assert decision.pipeline == PipelineType.DEEP
        assert decision.complexity == 5
        fallback.route.assert_called_once_with("tarea ambigua")

    def test_tentative_fallback_moderate_stays_three(self) -> None:
        """Fallback MODERATE -> STANDARD y complexity se mantiene en 3."""
        triage = _triage_mock(TENTATIVE_COMPLEXITY)
        fallback = MagicMock()
        fallback.route.return_value = _router_decision(
            ComplexityLevel.MODERATE, PipelineType.STANDARD
        )
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("tarea intermedia")

        assert decision.source == "fallback"
        assert decision.complexity == TENTATIVE_COMPLEXITY
        assert decision.pipeline == PipelineType.STANDARD


# ===========================================================================
# (c) complexity >= 4 -> frontier pipeline (DEEP)
# ===========================================================================


class TestFrontierComplexity:
    """Complejidad alta: pipeline frontier sin consultar el fallback."""

    def test_complexity_4_routes_frontier(self) -> None:
        """complexity=4 -> DEEP, source 'slm' y fallback NO consultado."""
        triage = _triage_mock(4)
        fallback = MagicMock()
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("integrar arquitectura hexagonal")

        assert decision.pipeline == PipelineType.DEEP
        assert decision.source == "slm"
        assert decision.complexity == 4
        fallback.route.assert_not_called()

    def test_complexity_five_routes_frontier(self) -> None:
        """Borde de FRONTIER_COMPLEXITY >= 4 (5) -> DEEP sin fallback."""
        triage = _triage_mock(5)
        fallback = MagicMock()
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("migrar plataforma distribuida")

        assert decision.pipeline == PipelineType.DEEP
        assert decision.complexity == 5
        assert FRONTIER_COMPLEXITY == 4


# ===========================================================================
# (d) triage lanza -> fallback directo (route NUNCA lanza)
# ===========================================================================


class TestTriageFailure:
    """Un fallo del triage no propaga: se usa el fallback directo."""

    def test_triage_raises_uses_fallback_and_never_raises(self) -> None:
        """RuntimeError del triage -> source 'fallback' y sin excepcion."""
        triage = MagicMock()
        triage.triage.side_effect = RuntimeError("SLM down")
        fallback = MagicMock()
        fallback.route.return_value = _router_decision(
            ComplexityLevel.VERY_COMPLEX, PipelineType.DEEP
        )
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("cualquier tarea")

        assert decision.source == "fallback"
        assert decision.pipeline == PipelineType.DEEP
        assert decision.complexity == 5
        fallback.route.assert_called_once_with("cualquier tarea")

    def test_triage_and_fallback_fail_still_returns_decision(self) -> None:
        """Si ambos fallan, devuelve una decision valida (nunca lanza)."""
        triage = MagicMock()
        triage.triage.side_effect = RuntimeError("SLM down")
        fallback = MagicMock()
        fallback.route.side_effect = RuntimeError("router down")
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("tarea")

        assert decision.source == "fallback"
        assert decision.pipeline == PipelineType.STANDARD
        assert 1 <= decision.complexity <= 5


# ===========================================================================
# (e) telemetria: record_usage(role="router", ...)
# ===========================================================================


class TestRouterTelemetry:
    """``route`` registra el uso de tokens con rol 'router'."""

    def test_record_usage_called_with_router_role(self) -> None:
        """record_usage recibe role='router' con conteos de bloques."""
        triage = _triage_mock(1)
        telemetry = TokenTelemetry()
        with patch.object(telemetry, "record_usage", wraps=telemetry.record_usage) as spy:
            router = PipelineRouter(triage=triage, telemetry=telemetry)
            router.route("hola")

        spy.assert_called_once()
        assert spy.call_args.args[0] == "router"
        assert spy.call_args.kwargs["cached"] >= 0
        assert spy.call_args.kwargs["input"] >= 0
        assert spy.call_args.kwargs["output"] == 1

    def test_telemetry_report_reflects_usage(self) -> None:
        """Tras ``route``, el reporte contiene el rol 'router'."""
        triage = _triage_mock(5)
        telemetry = TokenTelemetry()
        router = PipelineRouter(triage=triage, telemetry=telemetry)

        decision = router.route("tarea compleja")

        assert telemetry.report()["roles"]["router"]["records"] == 1
        assert isinstance(decision.telemetry, dict)

    def test_default_telemetry_is_created(self) -> None:
        """Sin telemetry inyectada, el router crea una propia (DI con default)."""
        triage = _triage_mock(1)
        router = PipelineRouter(triage=triage)

        decision = router.route("hola")

        assert isinstance(decision.telemetry, dict)


# ===========================================================================
# (f) TelemetryGate.check
# ===========================================================================


class TestTelemetryGate:
    """``TelemetryGate.check`` evalua el umbral MIN_HIT_RATE (0.80)."""

    def test_above_threshold_returns_ok(self) -> None:
        """hit_rate 0.9 >= 0.80 -> (True, mensaje de exito)."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("router", cached=90, input=10, output=1)

        ok, message = TelemetryGate().check(telemetry)

        assert ok is True
        assert "0.90" in message

    def test_below_threshold_flags_cache_buster(self) -> None:
        """hit_rate 0.5 < 0.80 -> (False, mensaje 'cache-buster')."""
        telemetry = TokenTelemetry()
        telemetry.record_usage("router", cached=50, input=50, output=1)

        ok, message = TelemetryGate().check(telemetry)

        assert ok is False
        assert "cache-buster" in message

    def test_empty_telemetry_is_flagged(self) -> None:
        """Sin registros hit_rate=0.0 -> gate en False (cache-buster)."""
        ok, message = TelemetryGate().check(TokenTelemetry())

        assert ok is False
        assert "cache-buster" in message


# ===========================================================================
# (g) mutacion: la rama "timido -> fallback" es discriminante
# ===========================================================================


class TestMutationGuard:
    """Guarda de mutacion: eliminar la rama timida rompe estos asserts."""

    def test_tentative_branch_is_required(self) -> None:
        """Si se quita la rama 'complexity==3 -> fallback', este test falla.

        Dos asserts discriminantes: la fuente debe ser 'fallback' Y el
        fallback debe haberse consultado exactamente una vez.
        """
        triage = _triage_mock(TENTATIVE_COMPLEXITY)
        fallback = MagicMock()
        fallback.route.return_value = _router_decision(
            ComplexityLevel.VERY_COMPLEX, PipelineType.DEEP
        )
        router = PipelineRouter(triage=triage, fallback_router=fallback)

        decision = router.route("tarea timida")

        assert decision.source == "fallback"
        assert fallback.route.call_count == 1


# ===========================================================================
# (h) prompt_blocks en orden canonico (tools antes que dynamic)
# ===========================================================================


class TestPromptBlocksOrder:
    """``prompt_blocks`` respeta el orden canonico de ``prompt_cache_shape``."""

    def test_frontier_blocks_tools_before_dynamic(self) -> None:
        """Pipeline frontier: 'tools' precede a 'dynamic' y orden canonico."""
        triage = _triage_mock(5)
        router = PipelineRouter(triage=triage)

        decision = router.route("tarea compleja")

        kinds = [block["kind"] for block in decision.prompt_blocks]
        assert "tools" in kinds
        assert "dynamic" in kinds
        assert kinds.index("tools") < kinds.index("dynamic")
        assert kinds == sorted(kinds, key=ORDER.index)

    def test_small_blocks_are_minimal(self) -> None:
        """Pipeline small: bloques minimales (sin tools), dynamic al final."""
        triage = _triage_mock(1)
        router = PipelineRouter(triage=triage)

        decision = router.route("hola")

        kinds = [block["kind"] for block in decision.prompt_blocks]
        assert "tools" not in kinds
        assert kinds[-1] == "dynamic"

    def test_routing_decision_is_frozen(self) -> None:
        """``RoutingDecision`` es inmutable (IMM: frozen dataclass)."""
        import dataclasses

        triage = _triage_mock(1)
        decision = PipelineRouter(triage=triage).route("hola")

        assert dataclasses.is_dataclass(decision)
        try:
            decision.complexity = 99  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("RoutingDecision deberia ser frozen")


# ===========================================================================
# FR-2 — TokenTelemetry en un call site real (AgentDispatcher)
# ===========================================================================


class TestFR2AgentDispatchTelemetry:
    """FR-2: ``AgentDispatcher.dispatch`` registra telemetria con DI opcional."""

    def test_dispatch_with_skill_records_telemetry(self) -> None:
        """Con skill inyectado, registra 'agent_dispatch' con cached > 0."""
        telemetry = TokenTelemetry()
        dispatcher = AgentDispatcher(telemetry=telemetry)
        skill = {"name": "s", "content": "skill " * 100, "similarity": 0.9}
        with patch.object(dispatcher, "find_skill_for_task", return_value=skill):
            dispatcher.dispatch("software-engineer", "build a rest api")

        roles = telemetry.report()["roles"]
        assert "agent_dispatch" in roles
        assert roles["agent_dispatch"]["records"] == 1
        assert roles["agent_dispatch"]["cached_tokens"] > 0

    def test_dispatch_without_skill_records_usage(self) -> None:
        """Sin skill, registra 'agent_dispatch' con cached == 0 (input > 0)."""
        telemetry = TokenTelemetry()
        dispatcher = AgentDispatcher(telemetry=telemetry)
        with patch.object(dispatcher, "find_skill_for_task", return_value=None):
            dispatcher.dispatch("software-engineer", "say hello world")

        roles = telemetry.report()["roles"]
        assert roles["agent_dispatch"]["cached_tokens"] == 0
        assert roles["agent_dispatch"]["input_tokens"] > 0

    def test_backward_compat_without_telemetry(self) -> None:
        """Sin telemetry (default None), el contrato previo no cambia."""
        dispatcher = AgentDispatcher()
        with patch.object(dispatcher, "find_skill_for_task", return_value=None):
            result = dispatcher.dispatch("software-engineer", "say hello")

        assert result["agent"] == "software-engineer"
        assert result["used_skill"] is False
        assert result["reasoning_mode"] == "from_scratch"
