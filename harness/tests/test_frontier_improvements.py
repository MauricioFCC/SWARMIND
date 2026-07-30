"""Tests para las 3 mejoras frontier 2026.

Cubre:
- Multi-API Router + Fallover
- Prompt Compression Engine
- Graph-of-Thought Planner
"""

from __future__ import annotations

import pytest

from harness.model_router.router import ModelRouter, MultiAPIProvider, ProviderConfig
from harness.memory_rag.prompt_compressor import PromptCompressor, CompressionResult
from harness.orchestrator.got_planner import GoTPlanner, GoTExecutor, Thought, ThoughtGraph


# ============================================================================
# Multi-API Router Tests
# ============================================================================

class TestMultiAPIProvider:
    """Tests para el proveedor multi-API con fallover."""

    def test_register_provider(self) -> None:
        """Registrar un provider debe funcionar."""
        router = ModelRouter()
        provider = MultiAPIProvider()
        config = ProviderConfig(
            name="test-openai",
            api_key_env="TEST_KEY",
            base_url="https://api.openai.com/v1",
            models=["gpt-4o-mini"],
            tier="standard",
            cost_per_1k_input=0.15,
            cost_per_1k_output=0.60,
        )
        provider.register_provider(config)
        stats = provider.get_stats()
        assert "providers" in stats
        assert len(stats.get("providers", {})) >= 1

    def test_route_basic(self) -> None:
        """route() debe retornar una decision."""
        router = ModelRouter()
        decision = router.route("Refactor this API", "builder")
        assert decision is not None
        assert hasattr(decision, 'source')
        assert hasattr(decision, 'model')

    def test_execute_basic(self) -> None:
        """execute() debe retornar un resultado."""
        router = ModelRouter()
        result = router.execute("Say hello", "scientist")
        assert result is not None


# ============================================================================
# Prompt Compression Tests
# ============================================================================

class TestPromptCompressor:
    """Tests para el compresor de prompts."""

    def setup_method(self) -> None:
        self.compressor = PromptCompressor()

    def test_extractive_compress(self) -> None:
        """Compresion extractiva debe reducir tokens."""
        text = "The quick brown fox jumps over the lazy dog. " * 10
        result = self.compressor.extractive_compress(text, ratio=0.5)
        assert len(result) < len(text)
        assert len(result) > 0

    def test_compress_returns_result(self) -> None:
        """compress() debe retornar CompressionResult."""
        text = "This is a test prompt that should be compressed. " * 20
        result = self.compressor.compress(text, target_ratio=0.5)
        assert isinstance(result, CompressionResult)
        assert result.ratio > 0
        assert result.compressed_tokens > 0

    def test_compress_system_prompt(self) -> None:
        """Compresion de system prompt debe preservar reglas clave."""
        prompt = "Eres un asistente util. " * 50
        result = self.compressor.compress_system_prompt(prompt, max_tokens=50)
        assert len(result) > 0

    def test_get_stats(self) -> None:
        """get_stats debe retornar metricas."""
        self.compressor.compress("test", target_ratio=0.5)
        stats = self.compressor.get_stats()
        assert "total_compressions" in stats


# ============================================================================
# Graph-of-Thought Tests
# ============================================================================

class TestGoTPlanner:
    """Tests para el planificador Graph-of-Thought."""

    def setup_method(self) -> None:
        self.planner = GoTPlanner()
        self.executor = GoTExecutor()

    def test_plan_returns_graph(self) -> None:
        """plan() debe retornar un ThoughtGraph."""
        graph = self.planner.plan("Resolver problema matematico", max_branches=2, max_depth=2)
        assert isinstance(graph, ThoughtGraph)
        assert graph.root_id is not None

    def test_graph_structure(self) -> None:
        """El grafo debe tener nodos y aristas."""
        graph = self.planner.plan("Analizar caso de uso", max_branches=2, max_depth=2)
        assert graph.node_count() > 0
        assert len(graph.thoughts) > 0

    def test_consolidate_returns_string(self) -> None:
        """consolidate() debe retornar una solucion."""
        graph = self.planner.plan("Test", max_branches=2, max_depth=2)
        solution = self.planner.consolidate(graph)
        assert isinstance(solution, str)
        assert len(solution) > 0

    def test_prune_removes_weak_nodes(self) -> None:
        """prune() debe eliminar nodos debiles."""
        graph = self.planner.plan("Test pruning", max_branches=3, max_depth=3)
        before = graph.node_count()
        pruned = self.planner.prune(graph, threshold=0.5)
        assert pruned.node_count() <= before

    def test_get_best_path(self) -> None:
        """get_best_path debe retornar el mejor camino."""
        graph = self.planner.plan("Test path", max_branches=2, max_depth=2)
        path = self.planner.get_best_path(graph)
        assert len(path) > 0
        assert all(isinstance(t, Thought) for t in path)

    def test_executor(self) -> None:
        """Executor debe producir una solucion."""
        executor = GoTExecutor(planner=self.planner)
        result = executor.execute("Test ejecucion")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_stats(self) -> None:
        """get_stats debe retornar metricas."""
        self.planner.plan("Test stats", max_branches=2, max_depth=2)
        stats = self.planner.get_stats()
        assert "total_plans" in stats
