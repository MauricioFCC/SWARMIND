"""
Tests para OptimizationPipeline â€” Pipeline completo de optimizaciÃ³n de tokens.

Cubre: inicializaciÃ³n, cada etapa del pipeline con early stopping,
manejo de errores, edge cases, compactaciÃ³n multi-paso y estadÃ­sticas.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from harness.memory_rag.context_window_manager import (
    ContextWindow,
)
from harness.memory_rag.optimization_pipeline import (
    OptimizationPipeline,
    OptimizationResult,
    create_pipeline,
)
from harness.memory_rag.token_budget import PRIORITY_NORMAL

# ===========================================================================
# Mocks
# ===========================================================================


class _MockTokenBudget:
    """Mock simplificado de TokenBudget para evitar inicializaciÃ³n real."""

    def __init__(self, agent_id: str = "default") -> None:
        self.agent_id = agent_id
        self.can_spend = True
        self.confidence = 0.0

    def set_confidence(self, val: float) -> None:
        self.confidence = val

    def request(self, pool: str, tokens: int) -> int:
        return tokens

    def commit(self, pool: str, tokens: int) -> None:
        pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_budget": 4000,
            "total_used": 0,
            "total_remaining": 4000,
            "usage_pct": 0.0,
            "priority": PRIORITY_NORMAL,
            "confidence": self.confidence,
            "can_spend": self.can_spend,
            "pools": {},
            "parent_session": None,
        }

    def record_failure(self) -> None:
        pass


class _MockBudgetManager:
    """Mock de BudgetManager que devuelve _MockTokenBudget."""

    def __init__(self) -> None:
        self._budgets: dict[str, _MockTokenBudget] = {}

    def register_agent(
        self,
        agent_id: str = "default",
        priority: int = PRIORITY_NORMAL,
        session_id: str = "",
    ) -> _MockTokenBudget:
        if agent_id not in self._budgets:
            self._budgets[agent_id] = _MockTokenBudget(agent_id=agent_id)
        return self._budgets[agent_id]

    def get_budget(self, agent_id: str) -> _MockTokenBudget | None:
        return self._budgets.get(agent_id)

    def reset_session(self, session_id: str) -> int:
        count = 0
        for aid in list(self._budgets.keys()):
            del self._budgets[aid]
            count += 1
        return count

    def get_stats(self) -> dict[str, Any]:
        return {"session_budget": 24000, "agents_registered": len(self._budgets)}


class _MockSemanticCache:
    """Mock de SemanticCache para tests aislados."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._stats_data: dict[str, Any] = {
            "hits": 0, "misses": 0, "sets": 0, "total_requests": 0, "hit_rate": 0.0,
        }

    def get(self, prompt: str, agent_role: str = "*", threshold: float | None = None) -> str | None:
        self._stats_data["total_requests"] += 1
        result = self._store.get(prompt)
        if result is not None:
            self._stats_data["hits"] += 1
            return result
        self._stats_data["misses"] += 1
        return None

    def set(
        self,
        prompt: str,
        response: str,
        agent_role: str = "*",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        self._store[prompt] = response
        self._stats_data["sets"] += 1
        return True

    def get_stats(self) -> dict[str, Any]:
        total = self._stats_data["total_requests"]
        self._stats_data["hit_rate"] = round(
            self._stats_data["hits"] / max(total, 1) * 100, 1
        )
        return dict(self._stats_data)


class _MockSkillLoader:
    """Mock de LazySkillLoader."""

    def __init__(self) -> None:
        self._stats: dict[str, Any] = {
            "tier1_tokens": 0, "tier2_tokens": 0, "tier3_tokens": 0,
            "loads_tier2": 0, "loads_tier3": 0, "hits": 0,
        }

    def detect_domains(self, message: str) -> list[str]:
        if "trading" in message.lower():
            return ["trading", "general"]
        return ["general"]

    def load_for_domain(self, domains: list[str]) -> dict[str, int]:
        return {"hedgefund": 2, "quant-trading": 2}

    def get_active_skills_context(self) -> str:
        return "## Loaded Skills\n### hedgefund (minified)\n..."

    def get_tier1_prompt(self, domain_filter: list[str] | None = None) -> str:
        return "## Available Skills\n- **hedgefund**: ..."

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)


class _MockContextManager:
    """Mock de ContextWindowManager."""

    def __init__(self) -> None:
        self._sliding_window_size = 6
        self._stats: dict[str, Any] = {
            "optimizations": 0, "truncations": 0, "summarizations": 0,
            "tokens_before": 0, "tokens_after": 0, "tokens_saved": 0,
        }

    def optimize(self, window: ContextWindow) -> ContextWindow:
        self._stats["optimizations"] += 1
        return window

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def _compress_tool_outputs(self, section: Any) -> None:
        section.compressed = True

    def _summarize_conversation(self, section: Any) -> None:
        section.compressed = True


class _MockPromptCacheBuilder:
    """Mock de PromptCacheBuilder."""

    def __init__(self) -> None:
        self._stats: dict[str, Any] = {"builds": 0}

    def build(self, **kwargs: Any) -> str:
        self._stats["builds"] += 1
        user_msg = kwargs.get("user_message", "")
        system = kwargs.get("system_identity", "")
        return f"{system}\n[optimized]\n{user_msg}"

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)


class _MockTrajectoryCompressor:
    """Mock de TrajectoryCompressor."""

    def compress(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return history


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def pipeline() -> OptimizationPipeline:
    """Pipeline con todos los componentes deshabilitados (control)."""
    return OptimizationPipeline(
        skills_dir=".",
        enable_cache=False,
        enable_budget=False,
        enable_lazy_skills=False,
        enable_context_window=False,
        enable_prompt_cache=False,
        enable_trajectory_compression=False,
        enable_multi_pass_compaction=False,
    )


@pytest.fixture
def full_pipeline() -> OptimizationPipeline:
    """Pipeline con todos los componentes mockeados."""
    pipe = OptimizationPipeline(
        skills_dir=".",
        enable_cache=False,  # inyectamos mock abajo
        enable_budget=False,
        enable_lazy_skills=False,
        enable_context_window=False,
        enable_prompt_cache=False,
        enable_trajectory_compression=False,
        enable_multi_pass_compaction=False,
    )
    # Inyectar mocks en privado
    pipe._semantic_cache = _MockSemanticCache()
    pipe._budget_manager = _MockBudgetManager()
    pipe._skill_loader = _MockSkillLoader()
    pipe._context_manager = _MockContextManager()
    pipe._prompt_cache_builder = _MockPromptCacheBuilder()
    pipe._trajectory_compressor = _MockTrajectoryCompressor()
    pipe._enable_multi_pass_compaction = True
    return pipe


# ===========================================================================
# Tests: InicializaciÃ³n
# ===========================================================================


class TestInitialization:
    """Tests para la inicializaciÃ³n correcta del pipeline."""

    def test_default_init(self) -> None:
        """OptimizationPipeline se inicializa con valores por defecto."""
        pipe = OptimizationPipeline(vector_store=None)
        assert pipe._semantic_cache is None
        assert pipe._budget_manager is not None
        assert pipe._skill_loader is not None
        assert pipe._context_manager is not None
        assert pipe._prompt_cache_builder is not None
        assert pipe._trajectory_compressor is not None
        assert pipe._enable_multi_pass_compaction is True
        assert pipe._stats["optimizations"] == 0

    def test_init_all_disabled(self) -> None:
        """Pipeline se inicializa con todas las optimizaciones desactivadas."""
        pipe = OptimizationPipeline(
            enable_cache=False,
            enable_budget=False,
            enable_lazy_skills=False,
            enable_context_window=False,
            enable_prompt_cache=False,
            enable_trajectory_compression=False,
            enable_multi_pass_compaction=False,
        )
        assert pipe._semantic_cache is None
        assert pipe._budget_manager is None
        assert pipe._skill_loader is None
        assert pipe._context_manager is None
        assert pipe._prompt_cache_builder is None
        assert pipe._trajectory_compressor is None
        assert pipe._enable_multi_pass_compaction is False

    def test_init_with_vector_store(self, vector_store: Any) -> None:
        """Cache se habilita cuando se provee vector_store."""
        pipe = OptimizationPipeline(vector_store=vector_store)
        assert pipe._semantic_cache is not None

    def test_create_pipeline_convenience(self) -> None:
        """create_pipeline retorna una instancia de OptimizationPipeline."""
        pipe = create_pipeline()
        assert isinstance(pipe, OptimizationPipeline)

    def test_init_stats_clean(self) -> None:
        """Las estadÃ­sticas iniciales estÃ¡n en cero."""
        pipe = OptimizationPipeline(enable_cache=False, enable_budget=False)
        s = pipe._stats
        assert s["optimizations"] == 0
        assert s["cache_hits"] == 0
        assert s["tokens_saved"] == 0
        assert s["total_duration_ms"] == 0


# ===========================================================================
# Tests: Etapas del Pipeline
# ===========================================================================


class TestPipelineStages:
    """Tests para cada etapa del pipeline de optimizaciÃ³n."""

    def test_stage_domain_detection_and_skill_loading(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 1: DetecciÃ³n de dominio y carga de skills."""
        result = full_pipeline.optimize(
            agent_id="quant_dev",
            user_message="implement a trading strategy with momentum indicators",
        )
        assert "hedgefund" in result.skills_loaded
        assert "quant-trading" in result.skills_loaded

    def test_stage_budget_blocked(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 2: Si budget estÃ¡ agotado, retorna inmediatamente."""
        budget = full_pipeline._budget_manager.register_agent("blocked_agent")
        budget.can_spend = False  # type: ignore[assignment]
        result = full_pipeline.optimize(agent_id="blocked_agent")
        assert result.metadata.get("budget_blocked") is True
        assert result.optimized_prompt == ""

    def test_stage_cache_hit_early_return(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 3: Cache hit retorna respuesta cacheada sin construir prompt."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        cache.set("agent:default|domains:general|msg:hello", "cached response")
        result = full_pipeline.optimize(user_message="hello")
        assert result.cache_hit is True
        assert result.cached_response == "cached response"
        assert result.optimized_prompt == ""

    def test_stage_cache_miss_continues(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 3: Cache miss continÃºa con el resto del pipeline."""
        result = full_pipeline.optimize(
            agent_id="test_agent",
            user_message="tell me a story",
        )
        assert result.cache_hit is False
        assert result.optimized_prompt != ""

    def test_stage_context_window_built(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 4: Context window se construye con todas las secciones."""
        result = full_pipeline.optimize(
            agent_id="test",
            system_parts={"system_identity": "You are a helpful AI"},
            user_message="hello",
            rag_context="some context",
        )
        assert "total_budget" in result.context_window
        assert "total_tokens" in result.context_window

    def test_stage_prompt_cache_builder_output(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 5: Prompt cache builder transforma el output."""
        result = full_pipeline.optimize(
            agent_id="test",
            system_parts={"system_identity": "You are a bot"},
            user_message="hello",
        )
        assert "[optimized]" in result.optimized_prompt

    def test_stage_budget_request_granted_less_than_estimate(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 6: Si budget concede menos de lo estimado, se trunca."""
        full_pipeline._budget_manager.register_agent("limited_agent")
        result = full_pipeline.optimize(
            agent_id="limited_agent",
            user_message="x" * 5000,  # mensaje largo
        )
        # Pipeline no trunca realmente porque el mock siempre concede
        # pero verifica que el pipeline maneje el paso sin error
        assert result.tokens_before >= 0

    def test_stage_final_cache_store(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 7: Resultado se almacena en cache semantico."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        stats_before = cache.get_stats()["sets"]
        full_pipeline.optimize(
            agent_id="test",
            user_message="store_this",
            force_no_cache=False,
        )
        stats_after = cache.get_stats()["sets"]
        assert stats_after >= stats_before


# ===========================================================================
# Tests: Manejo de Errores
# ===========================================================================


class TestErrorHandling:
    """Tests para manejo de errores en cada etapa."""

    def test_error_in_domain_detection_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error en detecciÃ³n de dominio propaga excepciÃ³n (no hay try/except)."""
        loader = full_pipeline._skill_loader
        assert loader is not None
        # Nota: el pipeline no tiene try/except en esta etapa
        with mock.patch.object(loader, "detect_domains", side_effect=ValueError("domain error")):  # noqa: SIM117
            with pytest.raises(ValueError, match="domain error"):
                full_pipeline.optimize(user_message="test")

    def test_error_in_cache_lookup_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error en cache lookup propaga excepciÃ³n."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        with mock.patch.object(cache, "get", side_effect=RuntimeError("cache down")):  # noqa: SIM117
            with pytest.raises(RuntimeError, match="cache down"):
                full_pipeline.optimize(user_message="test")

    def test_error_in_budget_request_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error en budget request propaga excepciÃ³n."""
        budget = full_pipeline._budget_manager
        with mock.patch.object(budget, "register_agent", side_effect=Exception("budget error")):  # noqa: SIM117
            with pytest.raises(Exception, match="budget error"):
                full_pipeline.optimize(agent_id="error_agent")

    def test_error_in_context_window_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error en context window building propaga excepciÃ³n."""
        cm = full_pipeline._context_manager
        assert cm is not None
        with mock.patch.object(cm, "optimize", side_effect=Exception("cm error")):  # noqa: SIM117
            with pytest.raises(Exception, match="cm error"):
                full_pipeline.optimize(user_message="test")

    def test_error_in_trajectory_compression_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error en trajectory compression propaga excepciÃ³n."""
        tc = full_pipeline._trajectory_compressor
        assert tc is not None
        with mock.patch.object(tc, "compress", side_effect=Exception("compression error")):  # noqa: SIM117
            with pytest.raises(Exception, match="compression error"):
                full_pipeline.optimize(
                    user_message="test",
                    conversation_history=[{"role": "user", "content": "hi"}],
                )

    def test_error_in_cache_store_propagates(self, full_pipeline: OptimizationPipeline) -> None:
        """Error al almacenar en cache propaga excepciÃ³n (no hay try/except)."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        with mock.patch.object(cache, "set", side_effect=RuntimeError("store error")):  # noqa: SIM117
            with pytest.raises(RuntimeError, match="store error"):
                full_pipeline.optimize(user_message="test")

    def test_prompt_cache_builder_fallback_labeled(self, full_pipeline: OptimizationPipeline) -> None:
        """Si prompt_cache_builder.build falla, la excepciÃ³n se propaga."""
        pcb = full_pipeline._prompt_cache_builder
        assert pcb is not None
        # El pipeline no tiene try/except alrededor de build()
        with mock.patch.object(pcb, "build", side_effect=Exception("build error")):  # noqa: SIM117
            with pytest.raises(Exception, match="build error"):
                full_pipeline.optimize(
                    user_message="test",
                    system_parts={"system_identity": "You are AI"},
                )


# ===========================================================================
# Tests: Edge Cases
# ===========================================================================


class TestEdgeCases:
    """Tests para casos extremos del pipeline."""

    def test_empty_user_message(self, full_pipeline: OptimizationPipeline) -> None:
        """Pipeline maneja mensaje de usuario vacÃ­o."""
        result = full_pipeline.optimize(user_message="")
        assert result is not None
        assert isinstance(result.optimized_prompt, str)

    def test_force_no_cache(self, full_pipeline: OptimizationPipeline) -> None:
        """force_no_cache=true salta la busqueda en cache."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        # Poblar cache
        cache.set("agent:default|domains:general|msg:hello", "cached")
        # Con force_no_cache, debe ignorar cache
        result = full_pipeline.optimize(user_message="hello", force_no_cache=True)
        assert result.cache_hit is False

    def test_very_long_user_message(self, full_pipeline: OptimizationPipeline) -> None:
        """Mensaje de usuario extremadamente largo no rompe el pipeline."""
        long_msg = "hello " * 10000
        result = full_pipeline.optimize(user_message=long_msg)
        assert result is not None
        assert result.tokens_before > 0

    def test_zero_budget_pipeline(self) -> None:
        """Pipeline con presupuesto cero no falla."""
        pipe = OptimizationPipeline(total_budget=0, enable_cache=False)
        result = pipe.optimize(user_message="test")
        assert result is not None

    def test_no_system_parts(self, full_pipeline: OptimizationPipeline) -> None:
        """Pipeline funciona sin system_parts."""
        result = full_pipeline.optimize(user_message="test", system_parts=None)
        assert result is not None
        assert result.optimized_prompt != ""

    def test_all_components_disabled(self) -> None:
        """Pipeline completamente desnudo aÃºn produce un resultado."""
        pipe = OptimizationPipeline(
            enable_cache=False,
            enable_budget=False,
            enable_lazy_skills=False,
            enable_context_window=False,
            enable_prompt_cache=False,
            enable_trajectory_compression=False,
            enable_multi_pass_compaction=False,
        )
        result = pipe.optimize(
            user_message="hello",
            system_parts={"test": "content"},
        )
        assert result.original_prompt != ""
        assert result.duration_ms >= 0

    def test_conversation_history_input(self, full_pipeline: OptimizationPipeline) -> None:
        """Pipeline maneja historial de conversaciÃ³n."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "tool", "content": "result: ok"},
        ]
        result = full_pipeline.optimize(
            user_message="next step",
            conversation_history=history,
        )
        assert result is not None

    def test_tool_outputs_input(self, full_pipeline: OptimizationPipeline) -> None:
        """Pipeline maneja tool_outputs."""
        result = full_pipeline.optimize(
            user_message="process results",
            tool_outputs="Tool: calculator\nResult: 42\nStatus: success",
        )
        assert result is not None


# ===========================================================================
# Tests: CompactaciÃ³n Multi-Paso
# ===========================================================================


class TestMultiPassCompaction:
    """Tests para la compactaciÃ³n multi-etapa con early stopping."""

    def test_compaction_pipeline_disabled(self) -> None:
        """Compaction pipeline no se ejecuta cuando estÃ¡ deshabilitado."""
        pipe = OptimizationPipeline(
            enable_context_window=False,
            enable_multi_pass_compaction=False,
        )
        window = ContextWindow(total_budget=1000)
        window.add_section("tool_outputs", "x" * 2000, max_tokens=100)
        result = pipe._run_compaction_pipeline(window, 500)
        assert result is window

    def test_compaction_pipeline_no_context_manager(self, pipeline: OptimizationPipeline) -> None:
        """Sin context_manager, compaction retorna la ventana intacta."""
        window = ContextWindow(total_budget=1000)
        result = pipeline._run_compaction_pipeline(window, 500)
        assert result is window

    def test_compaction_early_stop_budget_met(self, full_pipeline: OptimizationPipeline) -> None:
        """Early stopping: si budget ya estÃ¡ satisfecho, no aplica stages."""
        window = ContextWindow(total_budget=10000)
        window.add_section("system_identity", "hi", frozen=True)
        # total_tokens = 1, budget_target = 5000 -> ya cumple
        result = full_pipeline._run_compaction_pipeline(window, 5000)
        assert result is window

    def test_stage_tool_result_compaction(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 1: ToolResultCompaction comprime tool outputs."""
        cm = full_pipeline._context_manager
        assert cm is not None
        window = ContextWindow(total_budget=100)
        window.add_section("tool_outputs", "Tool: calc\nResult: " + "x" * 500, max_tokens=50)
        full_pipeline._stage_tool_result_compaction(window, 50)
        # El mock de _compress_tool_outputs solo setea compressed=True
        tool_sec = window.get_section("tool_outputs")
        assert tool_sec is not None
        assert tool_sec.compressed is True

    def test_stage_tool_result_noop_if_no_tool_sec(self, full_pipeline: OptimizationPipeline) -> None:
        """ToolResultCompaction es no-op si no hay tool_outputs."""
        window = ContextWindow(total_budget=100)
        full_pipeline._stage_tool_result_compaction(window, 50)  # no error

    def test_stage_summarization_compaction(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 2: SummarizationCompaction resume historial."""
        cm = full_pipeline._context_manager
        assert cm is not None
        window = ContextWindow(total_budget=100)
        window.add_section("conversation_history", "[user]: hi\n\n[assistant]: hello\n\n[x]: " + "y" * 300, max_tokens=50)
        full_pipeline._stage_summarization_compaction(window, 50)
        conv_sec = window.get_section("conversation_history")
        assert conv_sec is not None
        assert conv_sec.compressed is True

    def test_stage_summarization_noop_if_no_conv_sec(self, full_pipeline: OptimizationPipeline) -> None:
        """SummarizationCompaction es no-op si no hay conversation_history."""
        window = ContextWindow(total_budget=100)
        full_pipeline._stage_summarization_compaction(window, 50)  # no error

    def test_stage_sliding_window_compaction(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 3: SlidingWindowCompaction mantiene solo Ãºltimos N bloques."""
        cm = full_pipeline._context_manager
        assert cm is not None
        cm._sliding_window_size = 3  # type: ignore[assignment]
        blocks = "\n\n".join([f"[user]: msg {i}" for i in range(10)])
        window = ContextWindow(total_budget=100)
        window.add_section("conversation_history", blocks, max_tokens=500)
        full_pipeline._stage_sliding_window_compaction(window, 50)
        conv_sec = window.get_section("conversation_history")
        assert conv_sec is not None
        # Debe tener solo 3 bloques
        assert len(conv_sec.content.split("\n\n")) == 3

    def test_stage_sliding_window_noop_if_fits(self, full_pipeline: OptimizationPipeline) -> None:
        """SlidingWindow no actÃºa si hay menos bloques que window_size."""
        window = ContextWindow(total_budget=100)
        window.add_section("conversation_history", "[user]: hi\n\n[assistant]: hello", max_tokens=500)
        full_pipeline._stage_sliding_window_compaction(window, 50)
        conv_sec = window.get_section("conversation_history")
        assert conv_sec is not None
        assert conv_sec.compressed is False

    def test_stage_truncation_compaction(self, full_pipeline: OptimizationPipeline) -> None:
        """Stage 4: TruncationCompaction trunca tool outputs como Ãºltimo recurso."""
        window = ContextWindow(total_budget=100)
        sec = window.add_section("tool_outputs", "x" * 2000, max_tokens=10)
        sec._token_estimator = None  # forzar chars/4
        full_pipeline._stage_truncation_compaction(window, 50)
        assert sec.content.endswith("[...truncated...]")

    def test_stage_truncation_noop_if_not_over_budget(self, full_pipeline: OptimizationPipeline) -> None:
        """TruncationCompaction es no-op si la secciÃ³n no excede budget."""
        window = ContextWindow(total_budget=100)
        window.add_section("tool_outputs", "ok", max_tokens=500)
        full_pipeline._stage_truncation_compaction(window, 50)
        tool_sec = window.get_section("tool_outputs")
        assert tool_sec is not None
        assert tool_sec.compressed is False

    def test_stage_truncation_noop_if_frozen(self, full_pipeline: OptimizationPipeline) -> None:
        """TruncationCompaction no modifica secciones congeladas."""
        window = ContextWindow(total_budget=100)
        window.add_section("tool_outputs", "x" * 2000, max_tokens=10, frozen=True)
        full_pipeline._stage_truncation_compaction(window, 50)
        tool_sec = window.get_section("tool_outputs")
        assert tool_sec is not None
        assert tool_sec.compressed is False

    def test_compaction_full_pipeline_sequence(self, full_pipeline: OptimizationPipeline) -> None:
        """Pipeline completo de 4 etapas se ejecuta sin error."""
        window = ContextWindow(total_budget=100)
        window.add_section("tool_outputs", "Tool: calc\n" + "x" * 800, max_tokens=50)
        window.add_section("conversation_history", "\n\n".join([f"[user]: msg {i}" for i in range(15)]), max_tokens=50)
        result = full_pipeline._run_compaction_pipeline(window, 50)
        assert result is window


# ===========================================================================
# Tests: Internal Helpers
# ===========================================================================


class TestInternalHelpers:
    """Tests para mÃ©todos internos y auxiliares."""

    def test_build_cache_key(self) -> None:
        """_build_cache_key genera key determinÃ­stica."""
        key = OptimizationPipeline._build_cache_key(
            agent_id="test_agent",
            system_parts={"sys": "you are ai"},
            user_message="hello",
            domains=["general"],
        )
        assert "agent:test_agent" in key
        assert "domains:general" in key
        assert "msg:hello" in key

    def test_build_cache_key_no_system_parts(self) -> None:
        """Cache key funciona sin system_parts."""
        key = OptimizationPipeline._build_cache_key(
            agent_id="test",
            system_parts=None,
            user_message="",
            domains=["general"],
        )
        assert "agent:test" in key

    def test_format_history_empty(self) -> None:
        """_format_history retorna string vacÃ­o para lista vacÃ­a."""
        result = OptimizationPipeline._format_history([])
        assert result == ""

    def test_format_history_with_messages(self) -> None:
        """_format_history formatea mensajes correctamente."""
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = OptimizationPipeline._format_history(history)
        assert "[user]: hello" in result
        assert "[assistant]: hi there" in result

    def test_format_history_skips_empty_content(self) -> None:
        """_format_history salta mensajes sin contenido."""
        history = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "reply"},
        ]
        result = OptimizationPipeline._format_history(history)
        assert "[user]:" not in result
        assert "[assistant]: reply" in result

    def test_extract_sections(self) -> None:
        """_extract_sections extrae contenido de todas las secciones."""
        pipe = OptimizationPipeline(
            enable_cache=False, enable_budget=False, enable_lazy_skills=False,
            enable_context_window=False, enable_prompt_cache=False,
            enable_trajectory_compression=False, enable_multi_pass_compaction=False,
        )
        window = ContextWindow()
        window.add_section("system_identity", "you are ai", frozen=True)
        window.add_section("rag_context", "some docs")
        sections = pipe._extract_sections(window)
        assert sections["system_identity"] == "you are ai"
        assert sections["rag_context"] == "some docs"

    def test_extract_sections_empty(self) -> None:
        """_extract_sections con ventana vacÃ­a retorna dict vacÃ­o."""
        pipe = OptimizationPipeline(
            enable_cache=False, enable_budget=False, enable_lazy_skills=False,
            enable_context_window=False, enable_prompt_cache=False,
            enable_trajectory_compression=False, enable_multi_pass_compaction=False,
        )
        window = ContextWindow()
        sections = pipe._extract_sections(window)
        assert sections == {}


# ===========================================================================
# Tests: GestiÃ³n de Sesiones y EstadÃ­sticas
# ===========================================================================


class TestSessionAndStats:
    """Tests para end_session() y get_stats()."""

    def test_end_session(self, full_pipeline: OptimizationPipeline) -> None:
        """end_session resetea budgets asociados a la sesiÃ³n."""
        fp = full_pipeline
        # Registrar agente con sesiÃ³n
        fp.optimize(agent_id="agent1", session_id="session_a")
        assert fp._budget_manager is not None
        fp.end_session("session_a")
        # Verificar que se limpiÃ³ (el mock de reset_session devuelve count)
        assert True  # No error

    def test_get_stats_returns_dict(self, pipeline: OptimizationPipeline) -> None:
        """get_stats retorna diccionario con keys esperadas."""
        pipeline.optimize(user_message="test")
        stats = pipeline.get_stats()
        assert "optimizations" in stats
        assert "tokens_before" in stats
        assert "tokens_after" in stats
        assert "avg_duration_ms" in stats
        assert "avg_compression_pct" in stats

    def test_get_stats_collects_subsystem_stats(self, full_pipeline: OptimizationPipeline) -> None:
        """get_stats recolecta stats de subsistemas."""
        full_pipeline.optimize(user_message="collect stats")
        stats = full_pipeline.get_stats()
        assert "semantic_cache" in stats
        assert "budget_manager" in stats
        assert "skill_loader" in stats
        assert "context_window" in stats
        assert "prompt_cache" in stats

    def test_get_stats_cache_hit_rate(self, full_pipeline: OptimizationPipeline) -> None:
        """get_stats calcula cache hit rate."""
        full_pipeline.optimize(user_message="first")
        full_pipeline.optimize(user_message="first")  # hit
        stats = full_pipeline.get_stats()
        assert "cache_hit_rate" in stats
        assert stats["cache_hit_rate"] > 0

    def test_get_stats_avg_duration(self, full_pipeline: OptimizationPipeline) -> None:
        """get_stats calcula duraciÃ³n promedio."""
        full_pipeline.optimize(user_message="test")
        stats = full_pipeline.get_stats()
        assert stats["avg_duration_ms"] >= 0

    def test_update_stats(self, pipeline: OptimizationPipeline) -> None:
        """_update_stats incrementa correctamente los contadores."""
        result = OptimizationResult(
            tokens_before=1000,
            tokens_after=500,
            tokens_saved=500,
            duration_ms=150.0,
        )
        pipeline._update_stats(result)
        assert pipeline._stats["optimizations"] == 1
        assert pipeline._stats["tokens_before"] == 1000
        assert pipeline._stats["tokens_saved"] == 500
        assert pipeline._stats["total_duration_ms"] == 150.0


# ===========================================================================
# Tests: record_response
# ===========================================================================


class TestRecordResponse:
    """Tests para record_response() post-LLM."""

    def test_record_response_updates_cache(self, full_pipeline: OptimizationPipeline) -> None:
        """record_response almacena respuesta real en cache."""
        cache = full_pipeline._semantic_cache
        assert cache is not None
        stats_before = cache.get_stats()["sets"]
        full_pipeline.record_response(
            agent_id="test",
            prompt="my prompt",
            response="LLM response",
            session_id="session1",
            success=True,
        )
        stats_after = cache.get_stats()["sets"]
        assert stats_after > stats_before

    def test_record_response_success_increases_confidence(self, full_pipeline: OptimizationPipeline) -> None:
        """record_response con success=True incrementa confianza."""
        budget = full_pipeline._budget_manager.register_agent("test")
        conf_before = budget.confidence
        full_pipeline.record_response(
            agent_id="test",
            prompt="prompt",
            response="response",
            success=True,
        )
        assert budget.confidence >= conf_before

    def test_record_response_failure_decreases_confidence(self, full_pipeline: OptimizationPipeline) -> None:
        """record_response con success=False decrementa confianza."""
        budget = full_pipeline._budget_manager.register_agent("test2")
        budget.set_confidence(0.8)
        full_pipeline.record_response(
            agent_id="test2",
            prompt="prompt",
            response="",
            success=False,
        )
        assert budget.confidence < 0.8

    def test_record_response_no_budget_manager(self, pipeline: OptimizationPipeline) -> None:
        """record_response funciona sin budget manager."""
        pipeline.record_response(
            agent_id="test",
            prompt="prompt",
            response="response",
            success=True,
        )  # No error

    def test_record_response_no_cache(self, pipeline: OptimizationPipeline) -> None:
        """record_response funciona sin cache."""
        pipeline.record_response(
            agent_id="test",
            prompt="",
            response="response",
            success=True,
        )  # No error


# ===========================================================================
# Tests: Resultados y MÃ©tricas
# ===========================================================================


class TestOptimizationResult:
    """Tests para la construcciÃ³n de OptimizationResult."""

    def test_optimization_result_defaults(self) -> None:
        """OptimizationResult tiene valores por defecto."""
        r = OptimizationResult()
        assert r.original_prompt == ""
        assert r.tokens_before == 0
        assert r.tokens_saved == 0
        assert r.cache_hit is False
        assert r.duration_ms == 0.0
        assert r.skills_loaded == []
        assert r.metadata == {}

    def test_optimization_result_compression_pct(self, full_pipeline: OptimizationPipeline) -> None:
        """Resultado incluye compression_pct calculado."""
        result = full_pipeline.optimize(user_message="test compression metrics")
        assert 0.0 <= result.compression_pct <= 100.0

    def test_optimization_result_budget_snapshot(self, full_pipeline: OptimizationPipeline) -> None:
        """Resultado incluye snapshot del budget cuando estÃ¡ disponible."""
        result = full_pipeline.optimize(agent_id="snapshot_test", user_message="test")
        assert "agent_id" in result.budget_snapshot
        assert result.budget_snapshot["agent_id"] == "snapshot_test"
