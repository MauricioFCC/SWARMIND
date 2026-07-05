"""
Optimization Pipeline — Punto de integracion de todas las optimizaciones de tokens.

Orquesta:
  1. TokenBudget: presupuesto por agente/sesion con redistribucion dinamica
  2. SemanticCache: cache semantico de respuestas LLM
  3. LazySkillLoader: carga progresiva de skills (3 tiers)
  4. ContextWindowManager: ventana de contexto adaptativa
  5. PromptCacheBuilder: prompts optimizados para cache de proveedores
  6. SkillMinifier: compresion offline de skills
  7. TrajectoryCompressor: compresion de historial conversacional

Ahorro combinado estimado: 60-80% de tokens totales.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from harness.memory_rag.semantic_cache import SemanticCache
from harness.memory_rag.token_budget import (
    BudgetManager, TokenBudget,
    PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW,
)
from harness.memory_rag.skill_loader import LazySkillLoader, SkillInfo
from harness.memory_rag.context_window_manager import ContextWindowManager, ContextWindow
from harness.memory_rag.prompt_cache_builder import PromptCacheBuilder
from harness.memory_rag.trajectory_compressor import TrajectoryCompressor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Resultado de la optimizacion de una llamada LLM."""
    original_prompt: str = ""
    optimized_prompt: str = ""
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    compression_pct: float = 0.0
    cache_hit: bool = False
    cached_response: str = ""
    skills_loaded: List[str] = field(default_factory=list)
    budget_snapshot: Dict[str, Any] = field(default_factory=dict)
    context_window: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Optimization Pipeline
# ---------------------------------------------------------------------------

class OptimizationPipeline:
    """
    Pipeline completo de optimizacion para llamadas LLM.

    Orden de operaciones:
      1. Domain Detection → determinar dominios relevantes
      2. Lazy Skill Loading → cargar solo skills necesarios
      3. Budget Check → verificar presupuesto de tokens
      4. Semantic Cache Lookup → buscar respuesta cacheada
      5. Context Assembly → ensamblar contexto optimizado
      6. Context Window Management → comprimir a budget
      7. Prompt Cache Structure → reorganizar para cache provider
      8. Output → prompt optimizado listo para LLM

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
        vector_store: Optional[Any] = None,
        enable_cache: bool = True,
        enable_budget: bool = True,
        enable_lazy_skills: bool = True,
        enable_context_window: bool = True,
        enable_prompt_cache: bool = True,
        enable_trajectory_compression: bool = True,
        total_budget: int = 12000,
    ) -> None:
        # Cache
        self._semantic_cache: Optional[SemanticCache] = None
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

        self._stats: Dict[str, Any] = {
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
            "(cache=%s, budget=%s, lazy_skills=%s, ctx_window=%s, prompt_cache=%s, traj_compress=%s)",
            enable_cache, enable_budget, enable_lazy_skills,
            enable_context_window, enable_prompt_cache, enable_trajectory_compression,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        *,
        agent_id: str = "default",
        session_id: str = "",
        system_parts: Optional[Dict[str, str]] = None,
        user_message: str = "",
        rag_context: str = "",
        conversation_history: Optional[List[Dict[str, Any]]] = None,
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
        budget: Optional[TokenBudget] = None
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

        # --- 5. Optimize Context Window ---
        if self._context_manager:
            window = self._context_manager.optimize(window)
        result.context_window = window.to_dict()

        # --- 6. Compress conversation history ---
        if self._trajectory_compressor and conversation_history:
            conversation_history = self._trajectory_compressor.compress(conversation_history)

        # --- 7. Build Cache-friendly Prompt ---
        if self._prompt_cache_builder:
            # Extract sections from window
            sections = self._extract_sections(window)
            optimized = self._prompt_cache_builder.build(
                **sections,
                user_message=user_message,
            )
        else:
            optimized = window.to_prompt(format="labeled")

        # --- 8. Request budget tokens ---
        token_estimate = len(optimized) // 4
        if self._budget_manager and budget:
            granted = budget.request("system", token_estimate)
            if granted < token_estimate:
                # Truncate to granted budget
                max_chars = granted * 4
                if len(optimized) > max_chars:
                    optimized = optimized[:max_chars] + "\n[... truncated to budget ...]"

        # --- 9. Store in cache for future ---
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

        # --- 10. Build result ---
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

    def get_stats(self) -> Dict[str, Any]:
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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_context_window(
        self,
        agent_id: str,
        system_parts: Dict[str, str],
        user_message: str,
        rag_context: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        tool_outputs: str,
        domains: List[str],
    ) -> ContextWindow:
        """Build initial context window from all parts."""
        window = ContextWindow()

        # System sections (critical, frozen)
        for section_name, content in system_parts.items():
            window.add_section(
                name=section_name,
                content=content,
                frozen=True,
            )

        # Skill context (if lazy loader enabled)
        if self._skill_loader:
            skill_context = self._skill_loader.get_active_skills_context()
            if skill_context:
                window.add_section(
                    name="skill_context",
                    content=skill_context,
                    max_tokens=2000,
                )

            # Tier 1 catalog (always included, compact)
            tier1 = self._skill_loader.get_tier1_prompt(domain_filter=domains)
            window.add_section(
                name="skill_catalog",
                content=tier1,
                frozen=True,
                max_tokens=500,
            )

        # RAG context
        if rag_context:
            window.add_section(
                name="rag_context",
                content=rag_context,
                max_tokens=2000,
            )

        # Conversation history
        if conversation_history:
            # First compress trajectory
            if self._trajectory_compressor:
                conversation_history = self._trajectory_compressor.compress(
                    conversation_history
                )

            history_text = self._format_history(conversation_history)
            window.add_section(
                name="conversation_history",
                content=history_text,
                max_tokens=3000,
            )

        # Tool outputs
        if tool_outputs:
            window.add_section(
                name="tool_outputs",
                content=tool_outputs,
                max_tokens=2000,
            )

        return window

    def _extract_sections(self, window: ContextWindow) -> Dict[str, str]:
        """Extract sections from context window for prompt cache builder."""
        sections = {}
        for name, section in window.sections.items():
            sections[name] = section.content
        return sections

    @staticmethod
    def _format_history(history: List[Dict[str, Any]]) -> str:
        """Format conversation history as text."""
        parts = []
        for msg in history:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    @staticmethod
    def _build_cache_key(
        agent_id: str,
        system_parts: Optional[Dict[str, str]],
        user_message: str,
        domains: List[str],
    ) -> str:
        """Build a deterministic cache key from non-user parts."""
        parts = [f"agent:{agent_id}", f"domains:{','.join(domains)}"]
        if system_parts:
            for key, value in system_parts.items():
                parts.append(f"{key}:{value[:200]}")
        if user_message:
            parts.append(f"msg:{user_message}")
        return "|".join(parts)

    def _update_stats(self, result: OptimizationResult) -> None:
        """Update global stats."""
        self._stats["optimizations"] += 1
        self._stats["tokens_before"] += result.tokens_before
        self._stats["tokens_after"] += result.tokens_after
        self._stats["tokens_saved"] += result.tokens_saved
        self._stats["total_duration_ms"] += result.duration_ms


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def create_pipeline(**kwargs) -> OptimizationPipeline:
    """Create a pre-configured optimization pipeline."""
    return OptimizationPipeline(**kwargs)
