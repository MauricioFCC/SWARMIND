"""
Tests de ModelRouter (harness/model_router/router.py).

Verifica:
  - Route heuristica: empty -> small, simple -> small, complejo -> frontier.
  - Cache de decisiones (O(1) para tareas repetidas).
  - route_with_fallback: small first, escala a frontier si falla o baja confianza.
  - execute() sin proveedores registrados: error diagnostico WHAT+WHY+WHERE.
  - Compatibilidad backward: propiedades source/model, re-exports legacy.
  - Sugerencia de proveedor y estimacion de ahorro de costo.

Reglas: API publica, sin magic numbers, errores accionables.
"""
from __future__ import annotations

from harness.model_router.router import (
    MAX_TOKENS_BY_AGENT,
    ExecutionResult,
    ModelRoute,
    ModelRouter,
    MultiAPIProvider,
    ProviderConfig,
    ProviderTier,
    RoutingDecision,
    create_model_router,
)

SIMPLE_TASK = "suma 2 numeros"
# Tarea media con confidence >= 0.7 (score ~45) que habilita el camino small
MEDIUM_TASK = "primero analiza los datos y luego implementa la solucion"
COMPLEX_TASK = (
    "Analiza la complejidad computacional del algoritmo de PageRank "
    "y disena una arquitectura optimizada para grafos distribuidos "
    "con multiples restricciones de dominio"
)


# ---------------------------------------------------------------------------
# Route basica
# ---------------------------------------------------------------------------

class TestRouteBasic:
    """Routing heurístico small vs frontier."""

    def test_route_empty_task_routes_small(self) -> None:
        """Tarea vacía -> small con score 0 y confianza maxima."""
        router = ModelRouter()
        result = router.route("")
        assert result.model_route.route == "small"
        assert result.model_route.score == 0.0
        assert result.model_route.confidence == 1.0

    def test_route_simple_task_routes_small(self) -> None:
        """Tarea corta y simple -> small."""
        result = ModelRouter().route(SIMPLE_TASK)
        assert result.model_route.route == "small"
        assert result.model_route.confidence >= 0.5

    def test_route_complex_task_routes_frontier(self) -> None:
        """Tarea larga con keywords de razonamiento -> frontier."""
        result = ModelRouter().route(COMPLEX_TASK)
        assert result.model_route.route == "frontier"

    def test_route_returns_model_route_with_confidence(self) -> None:
        """model_route es un ModelRoute completo con confidence (bug fix)."""
        result = ModelRouter().route(COMPLEX_TASK)
        assert isinstance(result.model_route, ModelRoute)
        assert 0.0 <= result.model_route.confidence <= 1.0

    def test_route_model_preference_frontier_forces_route(self) -> None:
        """model_preference='frontier' fuerza la ruta."""
        result = ModelRouter().route(SIMPLE_TASK, model_preference="frontier")
        assert result.model_route.route == "frontier"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TestRouteCache:
    """Cache de decisiones para overhead O(1)."""

    def test_cache_hit_returns_same_route(self) -> None:
        """Misma tarea dos veces -> misma decision (cache)."""
        router = ModelRouter()
        first = router.route(SIMPLE_TASK)
        second = router.route(SIMPLE_TASK)
        assert first.model_route.route == second.model_route.route
        assert first.model_route.score == second.model_route.score
        assert first.suggested_provider == second.suggested_provider

    def test_different_tasks_not_shared(self) -> None:
        """Tareas distintas no comparten decision en cache."""
        router = ModelRouter()
        small = router.route(SIMPLE_TASK)
        complex_result = router.route(COMPLEX_TASK)
        assert small.model_route.route == "small"
        assert complex_result.model_route.route == "frontier"


# ---------------------------------------------------------------------------
# route_with_fallback
# ---------------------------------------------------------------------------

class TestRouteWithFallback:
    """Ejecuta small primero; escala a frontier si falla o baja confianza."""

    def test_fallback_small_first(self) -> None:
        """Tarea media con confianza alta -> se ejecuta small_fn."""
        calls: list[str] = []

        def small_fn(task: str) -> str:
            calls.append("small")
            return "ok"

        def frontier_fn(task: str) -> str:
            calls.append("frontier")
            return "big"

        out = ModelRouter().route_with_fallback(MEDIUM_TASK, small_fn, frontier_fn)
        assert out == "ok"
        assert calls == ["small"]

    def test_fallback_escalates_for_complex(self) -> None:
        """Tarea compleja -> se ejecuta frontier_fn."""
        calls: list[str] = []

        def small_fn(task: str) -> str:
            calls.append("small")
            return "ok"

        def frontier_fn(task: str) -> str:
            calls.append("frontier")
            return "big"

        out = ModelRouter().route_with_fallback(COMPLEX_TASK, small_fn, frontier_fn)
        assert out == "big"
        assert calls == ["frontier"]


# ---------------------------------------------------------------------------
# execute (compat legacy)
# ---------------------------------------------------------------------------

class TestExecute:
    """execute() delega en MultiAPIProvider con failover."""

    def test_execute_without_providers_returns_diagnostic(self) -> None:
        """Sin proveedores registrados -> ExecutionResult fallido con WHAT+WHY+WHERE."""
        result = ModelRouter().execute("tarea de prueba", agent_role="builder")
        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert "WHY" in result.error and "WHERE" in result.error


# ---------------------------------------------------------------------------
# Compatibilidad backward (API legacy)
# ---------------------------------------------------------------------------

class TestLegacyCompat:
    """Propiedades source/model y re-exports de la API legacy."""

    def test_source_local_for_small_route(self) -> None:
        """Route small -> source 'local' (compat legacy)."""
        result = ModelRouter().route(SIMPLE_TASK)
        assert result.source == "local"

    def test_source_frontier_for_frontier_route(self) -> None:
        """Route frontier -> source 'frontier' (compat legacy)."""
        result = ModelRouter().route(COMPLEX_TASK)
        assert result.source == "frontier"

    def test_model_property_returns_route(self) -> None:
        """Propiedad model devuelve la ruta seleccionada."""
        result = ModelRouter().route(SIMPLE_TASK)
        assert result.model == "small"

    def test_legacy_reexports_available(self) -> None:
        """Re-exports legacy importables desde router.py (compat imports)."""
        assert callable(MultiAPIProvider)
        assert callable(ProviderConfig)
        assert callable(ExecutionResult)
        assert RoutingDecision is not None
        assert ProviderTier is not None
        assert isinstance(MAX_TOKENS_BY_AGENT, dict)


# ---------------------------------------------------------------------------
# Sugerencia de proveedor
# ---------------------------------------------------------------------------

class TestProviderSuggestion:
    """Sugerencia de proveedor segun ruta y complejidad."""

    def test_suggested_provider_frontier_with_preference(self) -> None:
        """Frontier + preferred_provider -> sugiere ese proveedor."""
        result = ModelRouter().route(COMPLEX_TASK, preferred_provider="openai")
        assert result.suggested_provider == "openai"

    def test_suggested_provider_small_is_none(self) -> None:
        """Route small -> sin proveedor sugerido."""
        result = ModelRouter().route(SIMPLE_TASK, preferred_provider="anthropic")
        assert result.suggested_provider is None

    def test_get_provider_for_route_small_none(self) -> None:
        """Route small -> sin proveedor."""
        assert ModelRouter().get_provider_for_route("small") is None

    def test_get_provider_for_route_complex_anthropic(self) -> None:
        """Route frontier + complejidad complex -> anthropic."""
        assert ModelRouter().get_provider_for_route("frontier", "complex") == "anthropic"

    def test_get_provider_for_route_reasoning_openai(self) -> None:
        """Route frontier + complejidad reasoning -> openai."""
        assert ModelRouter().get_provider_for_route("frontier", "reasoning") == "openai"


# ---------------------------------------------------------------------------
# Estimacion de ahorro de costo
# ---------------------------------------------------------------------------

class TestCostReduction:
    """Estimacion de ahorro basada en el score de complejidad."""

    def test_estimate_low_score_is_max(self) -> None:
        """Score < 30 -> factor 3.0."""
        assert ModelRouter._estimate_cost_reduction(10.0) == 3.0

    def test_estimate_medium_score_is_mid(self) -> None:
        """30 <= score < 70 -> factor 1.5."""
        assert ModelRouter._estimate_cost_reduction(50.0) == 1.5

    def test_estimate_high_score_is_min(self) -> None:
        """Score >= 70 -> factor 1.0."""
        assert ModelRouter._estimate_cost_reduction(90.0) == 1.0

    def test_cost_reduction_simple_gt_complex(self) -> None:
        """Tarea simple ahorra mas que una compleja (monotono)."""
        simple = ModelRouter().route(SIMPLE_TASK)
        complex_result = ModelRouter().route(COMPLEX_TASK)
        assert (
            simple.estimated_cost_reduction
            >= complex_result.estimated_cost_reduction
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    """Factory function create_model_router."""

    def test_factory_returns_model_router(self) -> None:
        """Factory crea ModelRouter con threshold configurable."""
        router = create_model_router(threshold=40.0)
        assert isinstance(router, ModelRouter)
        assert router._router.threshold == 40.0

    def test_factory_default_threshold(self) -> None:
        """Factory sin args usa umbral por defecto (50)."""
        assert create_model_router()._router.threshold == 50.0
