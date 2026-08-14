"""Clase principal ``OptimizationPipeline`` para el paquete homonimo.

Extraido mecanicamente de ``optimization_pipeline.py`` (regla AGR < 500
lineas). Contiene la API publica (``__init__``, ``optimize``,
``record_response``, ``end_session``, ``get_stats``) y la funcion de
conveniencia ``create_pipeline``. Los helpers de compactacion y de
construccion de contexto se componen via mixins.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ..context_window_manager import ContextWindowManager
from ..prompt_cache_builder import PromptCacheBuilder
from ..semantic_cache import SemanticCache
from ..skill_loader import LazySkillLoader
from ..token_budget import (
    PRIORITY_NORMAL,
    BudgetManager,
    TokenBudget,
)
from ..trajectory_compressor import TrajectoryCompressor
from .compaction import _CompactionPipelineMixin
from .context_builder import _ContextBuilderMixin
from .models import OptimizationResult

logger = logging.getLogger("harness.memory_rag.optimization_pipeline")


# ---------------------------------------------------------------------------
# Optimization Pipeline
# ---------------------------------------------------------------------------

class OptimizationPipeline(_CompactionPipelineMixin, _ContextBuilderMixin):
    """
    Pipeline completo de optimizacion para llamadas LLM.

    Orden de operaciones:
      1. Domain Detection -> determinar dominios relevantes
      2. Lazy Skill Loading -> cargar solo skills necesarios
      3. Budget Check -> verificar presupuesto de tokens
      4. Semantic Cache Lookup -> buscar respuesta cacheada
      5. Context Assembly -> ensamblar contexto optimizado
      6. Multi-Pass Compaction -> pipeline multi-etapa (Microsoft 2026)
      7. Context Window Management -> comprimir a budget
      8. Prompt Cache Structure -> reorganizar para cache provider
      9. Output -> prompt optimizado listo para LLM

    Uso:
        pipeline = OptimizationPipeline()
        result = pipeline.optimize(
            agent_id="quant_dev",
            system_parts={...},
            user_message="analyze this...",
            rag_context=...,
        )
        if result.cache_hit:
            return result.cached_response
        # else: send result.optimized_prompt to LLM
    """

    def __init__(
        self,
        skills_dir: str = ".opencode/skills",
        vector_store: Any | None = None,
        enable_cache: bool = True,
        enable_budget: bool = True,
        enable_lazy_skills: bool = True,
        enable_context_window: bool = True,
        enable_prompt_cache: bool = True,
        enable_trajectory_compression: bool = True,
        enable_multi_pass_compaction: bool = True,
        total_budget: int = 12000,
    ) -> None:
        # Cache
        self._semantic_cache: SemanticCache | None = None
        if enable_cache and vector_store:
            self._semantic_cache = SemanticCache(vector_store=vector_store)

        # Budget
        self._budget_manager = BudgetManager(
            session_budget=total_budget * 2,
            default_agent_budget=total_budget // 3,
        ) if enable_budget else None

        # Skills
        self._skill_loader = LazySkillLoader(
            skills_dir=skills_dir, auto_discover=True
        ) if enable_lazy_skills else None

        # Context window
        self._context_manager = ContextWindowManager(
            total_budget=total_budget,
        ) if enable_context_window else None

        # Prompt cache
        self._prompt_cache_builder = PromptCacheBuilder(
            min_cache_prefix=1024,
        ) if enable_prompt_cache else None

        # Trajectory compression
        self._trajectory_compressor = TrajectoryCompressor() if enable_trajectory_compression else None

        # Multi-pass compaction
        self._enable_multi_pass_compaction = enable_multi_pass_compaction

        self._stats: dict[str, Any] = {
            "optimizations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "tokens_saved": 0,
            "total_duration_ms": 0,
        }

        logger.info(
            "OptimizationPipeline initialized "
            "(cache=%s, budget=%s, lazy_skills=%s, ctx_window=%s, "
            "prompt_cache=%s, traj_compress=%s, multi_pass=%s)",
            enable_cache, enable_budget, enable_lazy_skills,
            enable_context_window, enable_prompt_cache,
            enable_trajectory_compression, enable_multi_pass_compaction,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        *,
        agent_id: str = "default",
        session_id: str = "",
        system_parts: dict[str, str] | None = None,
        user_message: str = "",
        rag_context: str = "",
        conversation_history: list[dict[str, Any]] | None = None,
        tool_outputs: str = "",
        agent_priority: int = PRIORITY_NORMAL,
        force_no_cache: bool = False,
        **kwargs,
    ) -> OptimizationResult:
        """
        Optimize a complete LLM call.

        Args:
            agent_id: ID del agente que hace la llamada.
            session_id: ID de sesion para tracking de budget.
            system_parts: Dict de secciones del system prompt.
            user_message: Mensaje del usuario.
            rag_context: Contexto recuperado de RAG.
            conversation_history: Historial de conversacion.
            tool_outputs: Resultados de tool calls.
            agent_priority: Prioridad del agente para budget.
            force_no_cache: Forzar no usar cache.
            **kwargs: Extra sections for prompt builder.

        Returns:
            OptimizationResult con el prompt optimizado.
        """
        start_time = time.time()
        result = OptimizationResult()

        # --- 1. Domain Detection & Skill Loading ---
        domains = ["general"]
        if self._skill_loader and user_message:
            domains = self._skill_loader.detect_domains(user_message)
            loaded = self._skill_loader.load_for_domain(domains)
            result.skills_loaded = list(loaded.keys())
            logger.debug("Domains: %s, skills loaded: %s", domains, list(loaded.keys()))

        # --- 2. Token Budget Check ---
        budget: TokenBudget | None = None
        if self._budget_manager:
            budget = self._budget_manager.register_agent(
                agent_id=agent_id,
                priority=agent_priority,
                session_id=session_id,
            )
            if not budget.can_spend:
                result.metadata["budget_blocked"] = True
                result.metadata["reason"] = "Token budget exhausted or high confidence"
                result.optimized_prompt = ""
                result.duration_ms = (time.time() - start_time) * 1000
                self._update_stats(result)
                return result

        # --- 3. Semantic Cache Lookup ---
        if self._semantic_cache and not force_no_cache:
            full_prompt = self._build_cache_key(
                agent_id=agent_id,
                system_parts=system_parts,
                user_message=user_message,
                domains=domains,
            )
            cached = self._semantic_cache.get(
                prompt=full_prompt,
                agent_role=agent_id,
            )
            if cached:
                # Cache hit! No need to build LLM prompt
                result.cache_hit = True
                result.cached_response = cached
                result.optimized_prompt = ""
                result.tokens_saved = len(full_prompt) // 4  # estimated
                result.duration_ms = (time.time() - start_time) * 1000

                # Update budget confidence
                if budget:
                    budget.set_confidence(0.95)  # High confidence on cache hit

                self._stats["cache_hits"] += 1
                self._update_stats(result)
                logger.debug("Cache HIT for agent '%s'", agent_id)
                return result

            self._stats["cache_misses"] += 1

        # --- 4. Build Context Window ---
        window = self._build_context_window(
            agent_id=agent_id,
            system_parts=system_parts or {},
            user_message=user_message,
            rag_context=rag_context,
            conversation_history=conversation_history,
            tool_outputs=tool_outputs,
            domains=domains,
        )

        # --- 5. Multi-Pass Compaction Pipeline (Microsoft Agent Framework 2026) ---
        if self._context_manager and self._enable_multi_pass_compaction:
            window = self._run_compaction_pipeline(window, window.total_budget)

        # --- 6. Optimize Context Window ---
        if self._context_manager:
            window = self._context_manager.optimize(window)
        result.context_window = window.to_dict()

        # --- 7. Compress conversation history ---
        if self._trajectory_compressor and conversation_history:
            conversation_history = self._trajectory_compressor.compress(conversation_history)

        # --- 8. Build Cache-friendly Prompt ---
        if self._prompt_cache_builder:
            # Extract sections from window
            sections = self._extract_sections(window)
            optimized = self._prompt_cache_builder.build(
                **sections,
                user_message=user_message,
            )
        else:
            optimized = window.to_prompt(format="labeled")

        # --- 9. Request budget tokens ---
        token_estimate = len(optimized) // 4
        if self._budget_manager and budget:
            granted = budget.request("system", token_estimate)
            if granted < token_estimate:
                # Truncate to granted budget
                max_chars = granted * 4
                if len(optimized) > max_chars:
                    optimized = optimized[:max_chars] + "\n[... truncated to budget ...]"

        # --- 10. Store in cache for future ---
        if self._semantic_cache and not force_no_cache:
            # Store key without user message for prefix caching
            cache_key = self._build_cache_key(
                agent_id=agent_id,
                system_parts=system_parts,
                user_message=user_message,
                domains=domains,
            )
            self._semantic_cache.set(
                prompt=cache_key,
                response="[PENDING]",  # Will be updated after LLM call
                agent_role=agent_id,
                metadata={
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "domains": domains,
                    "skills_loaded": result.skills_loaded,
                },
            )

        # --- 11. Build result ---
        result.original_prompt = window.to_prompt(format="labeled")
        result.optimized_prompt = optimized
        result.tokens_before = token_estimate
        result.tokens_after = len(optimized) // 4
        result.tokens_saved = result.tokens_before - result.tokens_after
        result.compression_pct = round(
            (1 - result.tokens_after / max(result.tokens_before, 1)) * 100, 1
        )
        result.duration_ms = (time.time() - start_time) * 1000

        if budget:
            result.budget_snapshot = budget.snapshot()

        self._update_stats(result)
        return result

    def record_response(
        self,
        agent_id: str,
        prompt: str,
        response: str,
        session_id: str = "",
        success: bool = True,
    ) -> None:
        """
        Record an LLM response for cache updating and budget tracking.

        Call this AFTER the LLM call completes.

        Args:
            agent_id: Agent that made the call.
            prompt: The prompt that was sent.
            response: The LLM response.
            session_id: Session ID for tracking.
            success: Whether the call was successful.
        """
        # Update cache with actual response
        if self._semantic_cache and prompt:
            self._semantic_cache.set(
                prompt=prompt,
                response=response,
                agent_role=agent_id,
                metadata={"session_id": session_id, "success": success},
            )

        # Update budget
        budget = self._budget_manager.get_budget(agent_id) if self._budget_manager else None
        if budget:
            if success:
                budget.set_confidence(min(1.0, budget.confidence + 0.1))
                budget.commit("system", len(prompt) // 4)
            else:
                budget.set_confidence(max(0.0, budget.confidence - 0.2))
                budget.record_failure() if hasattr(budget, 'record_failure') else None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def end_session(self, session_id: str) -> None:
        """Clean up resources for a session."""
        if self._budget_manager:
            count = self._budget_manager.reset_session(session_id)
            logger.debug("Session '%s' ended: %d budgets reset", session_id, count)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return pipeline statistics."""
        stats = dict(self._stats)

        # Collect sub-system stats
        if self._semantic_cache:
            stats["semantic_cache"] = self._semantic_cache.get_stats()
        if self._budget_manager:
            stats["budget_manager"] = self._budget_manager.get_stats()
        if self._skill_loader:
            stats["skill_loader"] = self._skill_loader.get_stats()
        if self._context_manager:
            stats["context_window"] = self._context_manager.get_stats()
        if self._prompt_cache_builder:
            stats["prompt_cache"] = self._prompt_cache_builder.get_stats()

        avg_duration = stats.get("total_duration_ms", 0) / max(stats.get("optimizations", 1), 1)
        stats["avg_duration_ms"] = round(avg_duration, 1)

        total_before = stats.get("tokens_before", 1)
        if total_before > 0:
            stats["avg_compression_pct"] = round(
                stats["tokens_saved"] / total_before * 100, 1
            )
        else:
            stats["avg_compression_pct"] = 0.0

        total_requests = stats.get("cache_hits", 0) + stats.get("cache_misses", 1)
        stats["cache_hit_rate"] = round(
            stats.get("cache_hits", 0) / max(total_requests, 1) * 100, 1
        )

        return stats


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_pipeline(**kwargs) -> OptimizationPipeline:
    """Create a pre-configured optimization pipeline."""
    return OptimizationPipeline(**kwargs)
