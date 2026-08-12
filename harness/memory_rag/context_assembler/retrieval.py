"""Mixin de retrieval RAG para ``ContextAssembler``.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene extraccion de keywords, re-ranking por rol,
construccion de query vector, busqueda RAG con adaptive-k y fetch de
task context.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np

from harness.common import fallback_embedding

from .constants import (
    _ADAPTIVE_K_DEFAULT,
    _ADAPTIVE_K_GAP_THRESHOLD,
    _ADAPTIVE_K_HIGH_CONFIDENCE,
    _ADAPTIVE_K_MAX,
    _ADAPTIVE_K_MIN,
    _EMBEDDING_DIM,
)

logger = logging.getLogger("harness.memory_rag.context_assembler")


class _RetrievalMixin:
    """Metodos de busqueda, extraccion y re-ranking de contexto."""

    def extract_keywords(self, message: str) -> list[str]:
        """
        Extract meaningful keywords from a message.

        Performs basic cleaning, removes stopwords, and returns unique
        lower-cased terms longer than 2 characters.
        """
        STOPWORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "because",
            "but", "and", "or", "if", "while", "about", "up", "it", "its",
            "this", "that", "these", "those", "i", "me", "my", "we", "you",
            "he", "she", "they", "him", "her", "his", "their", "them",
        }

        # Lowercase and split on non-alphanumeric
        tokens = re.findall(r"[a-zA-Z]\w{2,}", message.lower())
        keywords = sorted({t for t in tokens if t not in STOPWORDS})
        return keywords

    def prioritize_chunks(
        self,
        chunks: list[dict[str, Any]],
        agent_role: str,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Re-rank chunks by relevance to a specific agent role.

        Boosts chunks whose metadata ``domain`` or ``tags`` match terms
        extracted from the agent role string. If ``filters`` are provided,
        chunks that match the filter values get an additional boost.

        Args:
            chunks: List of result dicts from the vector store.
            agent_role: Agent role identifier.
            filters: Optional metadata filters used during search.

        Returns:
            Re-ranked list of result dicts.
        """
        if not chunks:
            return chunks

        role_terms = set(
            re.findall(r"[a-zA-Z]\w*", agent_role.lower().replace("_", " "))
        )

        filter_values = set((filters or {}).values())

        def _role_score(chunk: dict[str, Any]) -> float:
            meta = chunk.get("metadata", {})
            domain = str(meta.get("domain", "")).lower()
            tipo = str(meta.get("tipo_doc", "")).lower()
            tags = [str(t).lower() for t in meta.get("tags", [])]
            chunk_text = f"{domain} {tipo} {' '.join(tags)}"
            matches = sum(1 for term in role_terms if term in chunk_text)
            base = matches / max(len(role_terms), 1)
            if filter_values and (domain in filter_values or tipo in filter_values):
                base += 0.2
            return min(base, 1.0)

        # Blend: 70 % vector score + 30 % role-match score
        scored = []
        for c in chunks:
            vector_score = c.get("score", 0.0)
            role_score = _role_score(c)
            scored.append((c, 0.7 * vector_score + 0.3 * role_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored]

    def _default_embedding(self, text: str) -> np.ndarray:
        """Fallback embedding: delega en harness.common.fallback_embedding."""
        return fallback_embedding(text)

    def _make_query_vector(
        self, message: str, keywords: list[str]
    ) -> np.ndarray:
        """Build a single query embedding from message + keywords."""
        text = f"{message} {' '.join(keywords)}"
        return self._embedding_fn(text)

    def _search_rag_chunks(
        self,
        query_vec: np.ndarray,
        keywords: list[str],
        top_k: int = 20,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search ``rag_chunks`` collection with adaptive-k retrieval.

        En lugar de usar siempre el mismo top_k, adapta dinamicamente
        la cantidad de chunks recuperados segun la distribucion de scores:

        - Si el top-1 tiene score > HIGH_CONFIDENCE, solo devolver 1 chunk.
        - Si hay un gap grande entre scores consecutivos, cortar ahi.
        - Si los scores son uniformes, mantener el maximo.

        Ahorro estimado: 35-50% de tokens de contexto RAG sin perder accuracy.
        """
        try:
            if filters:
                kw = " ".join(keywords) if keywords else ""
                results = self.store.search(
                    "rag_chunks", query_vec, top_k=top_k, filters=filters
                )
                if kw.strip():
                    hybrid = self.store.hybrid_search(
                        "rag_chunks", query_vec, kw, top_k=top_k
                    )
                    existing_ids = {r["id"] for r in results}
                    for h in hybrid:
                        if h["id"] not in existing_ids:
                            results.append(h)
            else:
                kw = " ".join(keywords) if keywords else ""
                if kw.strip():
                    results = self.store.hybrid_search(
                        "rag_chunks", query_vec, kw, top_k=top_k
                    )
                else:
                    results = self.store.search(
                        "rag_chunks", query_vec, top_k=top_k
                    )

            # --- Adaptive-k: reducir chunks basado en score distribution ---
            if results:
                results = self._adaptive_k_rerank(results)

            return results
        except Exception:
            logger.exception("RAG chunk search failed; returning empty.")
            return []

    def _adaptive_k_rerank(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Aplicar adaptive-k: reducir chunks basado en distribucion de scores.

        Estrategia:
        1. Si el top-1 tiene score > HIGH_CONFIDENCE, devolver solo ese.
        2. Si hay gap > GAP_THRESHOLD entre scores consecutivos, cortar ahi.
        3. Si no hay gaps significativos y hay menos de MAX resultados, mantenerlos.
        4. Siempre devolver al menos MIN resultados.

        Returns:
            Lista reducida de resultados.
        """
        if not results:
            return results

        # Extraer scores (normalizar a 0-1 si _distance de LanceDB)
        scores = []
        for r in results:
            s = r.get("score", 0.0)
            # LanceDB a veces devuelve _distance (menor = mejor)
            # Si el score es > 1, probablemente es distancia, no similitud
            if s > 1.0:
                s = 1.0 / (1.0 + s)  # convertir distancia a similitud
            scores.append(max(0.0, min(1.0, s)))

        if not scores:
            return results

        # Caso 1: High confidence - solo el top-1
        if scores[0] >= _ADAPTIVE_K_HIGH_CONFIDENCE:
            logger.debug(
                "Adaptive-k: high confidence (%.4f), returning 1/%d chunks",
                scores[0], len(results),
            )
            return results[:_ADAPTIVE_K_MIN]

        # Caso 2: Detectar gap mas grande en la distribucion
        gaps = []
        for i in range(len(scores) - 1):
            gap = scores[i] - scores[i + 1]
            if gap > 0:  # solo gaps positivos (score decreciente)
                gaps.append((gap, i))

        if gaps:
            max_gap, max_gap_idx = max(gaps, key=lambda x: x[0])
            if max_gap > _ADAPTIVE_K_GAP_THRESHOLD:
                # Cortar despues del gap mas grande
                k = max(_ADAPTIVE_K_MIN, min(max_gap_idx + 1, _ADAPTIVE_K_MAX))
                logger.debug(
                    "Adaptive-k: gap=%.4f at idx=%d, returning %d/%d chunks",
                    max_gap, max_gap_idx, k, len(results),
                )
                return results[:k]

        # Caso 3: Scores uniformes, mantener maximo pero limitado
        k = min(len(results), _ADAPTIVE_K_DEFAULT)
        logger.debug(
            "Adaptive-k: uniform scores, returning %d/%d chunks",
            k, len(results),
        )
        return results[:k]

    def _fetch_task_context(
        self,
        agent_role: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent task assignments for the given agent role."""
        try:
            filters = {"agent": agent_role} if agent_role else None
            results = self.store.search(
                "tasks_board",
                query_vector=np.zeros(_EMBEDDING_DIM, dtype=np.float32),
                top_k=top_k,
                filters=filters,
            )
            return results
        except Exception:  # noqa: BLE001
            logger.debug("Task context fetch returned no results.")
            return []

    def _build_instructions(
        self, agent_role: str, message: str
    ) -> str:
        """Build role-specific system instructions."""
        role_prompts = {
            "quant_dev": (
                "You are a quantitative developer implementing trading strategies. "
                "Use Python, ONNX, and broker APIs.  Ensure orders always include "
                "bracket OCO (stop loss + take profit).  Log context_score in every signal."
            ),
            "quant_analyst": (
                "You are a quantitative analyst designing market models. "
                "Evaluate signal quality, context scores, and regime detection. "
                "Base your analysis on the retrieved context below."
            ),
            "data_architect": (
                "You are a data architect designing database schemas and ETL pipelines. "
                "Use Pydantic for validation, PostgreSQL for persistence, and Redis for caching."
            ),
            "devops_sre": (
                "You are a DevOps/SRE engineer ensuring system reliability. "
                "Configure Docker, CI/CD, monitoring, and auto-recovery. "
                "Focus on observability and deployment automation."
            ),
            "security_engineer": (
                "You are a security engineer hardening the trading system. "
                "Enforce AppSec, DevSecOps, threat modeling, and regulatory compliance."
            ),
            "project_manager": (
                "You are a project manager orchestrating multi-agent work. "
                "Track progress, identify blockers, and ensure timely delivery using "
                "the F.R.A.M.E. framework."
            ),
        }

        base = role_prompts.get(
            agent_role,
            "You are an expert AI agent in the trading-bot system. "
            "Respond accurately using the provided context.",
        )

        return f"{base}\n\nUser request: {message}"
