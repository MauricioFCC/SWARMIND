"""Clase principal ``ContextAssembler`` para el paquete homonimo.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene la API publica (``__init__``, ``assemble``,
``assemble_async``). Los helpers de retrieval, instrucciones y
presupuesto se componen via mixins.
"""
from __future__ import annotations

import asyncio
import logging

from harness.memory_rag.lance_vector_store import LanceVectorStore

from .budget import _TokenBudgetMixin
from .models import ContextAssembly
from .retrieval import _RetrievalMixin

logger = logging.getLogger("harness.memory_rag.context_assembler")


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------


class ContextAssembler(_RetrievalMixin, _TokenBudgetMixin):
    """
    Assembles structured context for agents by fusing RAG results,
    task history, and conversation state.

    Typical usage::

        store = LanceVectorStore()
        assembler = ContextAssembler(store)
        ctx = assembler.assemble(
            message="What is the current market regime?",
            agent_role="quant_analyst",
            max_tokens=2000,
        )
    """

    def __init__(
        self,
        vector_store: LanceVectorStore | None = None,
        embedding_fn: callable | None = None,
    ) -> None:
        """
        Args:
            vector_store: A ``LanceVectorStore`` instance.  If ``None``, a
                default one is created.
            embedding_fn: Optional callable that maps ``str -> np.ndarray``.
                If omitted, a simple TF-IDF-like bag-of-characters fallback
                is used so that the assembler works without an external model.
        """
        self.store = vector_store or LanceVectorStore()
        self._embedding_fn = embedding_fn or self._default_embedding

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(
        self,
        message: str,
        agent_role: str,
        max_tokens: int = 2000,
        domain_filter: str | None = None,
        tipo_doc_filter: str | None = None,
    ) -> ContextAssembly:
        """
        Build a structured context from a user message and agent role.

        Wrapper sync que delega en ``assemble_async()``. La version async
        ejecuta RAG + task context en PARALELO para reducir latencia.

        Args:
            message: The user's input message.
            agent_role: Role identifier (e.g. ``"quant_dev"``, ``"data_architect"``).
            max_tokens: Maximum token budget for the assembled context.
            domain_filter: Optional domain to filter by.
            tipo_doc_filter: Optional doc type filter.

        Returns:
            A ``ContextAssembly`` instance.
        """
        return asyncio.run(
            self.assemble_async(
                message=message,
                agent_role=agent_role,
                max_tokens=max_tokens,
                domain_filter=domain_filter,
                tipo_doc_filter=tipo_doc_filter,
            )
        )

    async def assemble_async(
        self,
        message: str,
        agent_role: str,
        max_tokens: int = 2000,
        domain_filter: str | None = None,
        tipo_doc_filter: str | None = None,
    ) -> ContextAssembly:
        """
        Version async de assemble(). Ejecuta RAG + task context en PARALELO.

        La latencia tipica se reduce de (T_rag + T_tasks) a max(T_rag, T_tasks).

        Args:
            message: The user's input message.
            agent_role: Role identifier.
            max_tokens: Maximum token budget.
            domain_filter: Optional domain filter.
            tipo_doc_filter: Optional doc type filter.

        Returns:
            A ``ContextAssembly`` instance.
        """
        # 1. Extract search terms
        keywords = self.extract_keywords(message)

        # 2. Build query embedding
        query_vec = self._make_query_vector(message, keywords)
        filters = {}
        if domain_filter:
            filters["domain"] = domain_filter
        if tipo_doc_filter:
            filters["tipo_doc"] = tipo_doc_filter

        # 3. Ejecutar busquedas en PARALELO via asyncio.gather
        chunks_task = asyncio.to_thread(
            self._search_rag_chunks, query_vec, keywords, 20, filters
        )
        tasks_task = asyncio.to_thread(
            self._fetch_task_context, agent_role, 10
        )

        raw_chunks, task_context = await asyncio.gather(chunks_task, tasks_task)

        # 4. Prioritise / re-rank chunks by agent role
        ranked_chunks = self.prioritize_chunks(raw_chunks, agent_role, filters=filters)

        # 5. Build role-specific instructions
        instructions = self._build_instructions(agent_role, message)

        # 6. Assemble
        assembly = ContextAssembly(
            instructions=instructions,
            relevant_docs=ranked_chunks,
            task_context=task_context,
            metadata={
                "agent_role": agent_role,
                "keywords": keywords,
                "max_tokens": max_tokens,
                "total_chunks_retrieved": len(raw_chunks),
                "domain_filter": domain_filter,
                "tipo_doc_filter": tipo_doc_filter,
                "parallel_execution": True,
            },
        )

        # 7. Truncate to budget (con 10% de margen de seguridad)
        safe_budget = int(max_tokens * 0.9)
        assembly = self._apply_token_budget(assembly, safe_budget)

        return assembly
