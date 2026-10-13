"""Clase principal ``ContextAssembler`` para el paquete homonimo.

Extraido mecanicamente de ``context_assembler.py`` (regla AGR < 500
lineas). Contiene la API publica (``__init__``, ``assemble``,
``assemble_async``). Los helpers de retrieval, instrucciones y
presupuesto se componen via mixins.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from harness.memory_rag.lance_vector_store import LanceVectorStore

from .budget import _TokenBudgetMixin
from .models import ContextAssembly
from .retrieval import _RetrievalMixin

logger = logging.getLogger("harness.memory_rag.context_assembler")

# ---------------------------------------------------------------------------
# Marcadores canonicos de seccion del prompt (cache-shape friendly)
# ---------------------------------------------------------------------------
# WHY marcadores: separan el contenido estable (rol/instrucciones) del
# dinamico (RAG + task context) y de la solicitud final; el bloque estable
# va primero para maximizar el prefijo cacheable del prompt.

#: Encabezado del bloque estable (rol/instrucciones).
_PROMPT_SECTION_STATIC = "### CONTEXTO ESTATICO (rol)"
#: Encabezado del bloque dinamico (chunks RAG + task context).
_PROMPT_SECTION_DYNAMIC = "### CONTEXTO DINAMICO (recuperado)"
#: Encabezado de la solicitud del usuario (ultimo bloque, mas variable).
_PROMPT_SECTION_REQUEST = "### SOLICITUD"

#: Campos donde puede vivir el texto de un chunk/item (orden de prioridad).
_TEXT_FIELDS = ("content", "text", "chunk", "description")


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
        hybrid_retriever: Any | None = None,
        corrective_retriever: Any | None = None,
    ) -> None:
        """
        Args:
            vector_store: A ``LanceVectorStore`` instance.  If ``None``, a
                default one is created.
            embedding_fn: Optional callable that maps ``str -> np.ndarray``.
                If omitted, a simple TF-IDF-like bag-of-characters fallback
                is used so that the assembler works without an external model.
            hybrid_retriever: ``HybridRetriever`` opcional (DI) que fusiona
                denso+BM25 con RRF. Si se inyecta mejora el recall; si es
                ``None`` rige la busqueda legacy (backward-compat).
            corrective_retriever: ``CorrectiveRetriever`` opcional (DI, CRAG)
                que valida y corrige la recuperacion. Tiene prioridad sobre
                ``hybrid_retriever``. ``None`` lo desactiva.
        """
        self.store = vector_store or LanceVectorStore()
        self._embedding_fn = embedding_fn or self._default_embedding
        self._hybrid_retriever = hybrid_retriever
        self._corrective_retriever = corrective_retriever

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
        # El recall avanzado (CRAG/hybrid) se resuelve por DI dentro de
        # ``_retrieve_chunks``; sin retrievers inyectados rige la ruta legacy.
        chunks_task = asyncio.to_thread(
            self._retrieve_chunks, message, query_vec, keywords, 20, filters
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

    # ------------------------------------------------------------------
    # Prompt injection (cache-shape friendly)
    # ------------------------------------------------------------------

    def inject_into_prompt(
        self,
        base_prompt: str,
        assembled: ContextAssembly,
    ) -> str:
        """Inyecta el contexto ensamblado en un prompt canonico por secciones.

        WHAT: compone un prompt con tres bloques marcados y estables:
        ``ESTATICO`` (instrucciones de rol), ``DINAMICO`` (chunks RAG + task
        context) y ``SOLICITUD`` (``base_prompt``). WHY: el assembler producia
        contexto pero nadie lo insertaba en un prompt en una forma canonica;
        ademas, poner primero el contenido estable maximiza el prefijo
        cacheable (Cache-Shape Discipline). WHERE: call sites que construyen el
        prompt del agente a partir del ``ContextAssembly``.

        Orden garantizado (estatico -> dinamico -> solicitud): el contenido mas
        estable va delante para que el cache de prefijo sea efectivo; el bloque
        mas variable (la solicitud del usuario) queda al final.

        Args:
            base_prompt: Prompt/solicitud base del usuario.
            assembled: Contexto ya ensamblado (``ContextAssembly``).

        Returns:
            Prompt con el contexto inyectado en secciones marcadas. Las
            secciones sin contenido se omiten (sin bloques vacios).
        """
        static_block = self._render_section(
            _PROMPT_SECTION_STATIC,
            [assembled.instructions] if assembled.instructions else [],
        )
        dynamic_parts = [self._format_doc(doc) for doc in assembled.relevant_docs]
        dynamic_parts += [self._format_task(item) for item in assembled.task_context]
        dynamic_block = self._render_section(_PROMPT_SECTION_DYNAMIC, dynamic_parts)
        request_block = self._render_section(_PROMPT_SECTION_REQUEST, [base_prompt])

        return "\n\n".join(
            block for block in (static_block, dynamic_block, request_block) if block
        )

    @staticmethod
    def _render_section(marker: str, parts: list[str]) -> str:
        """Renderiza una seccion marcada; vacia si no hay contenido.

        Args:
            marker: Encabezado de la seccion (constante ``_PROMPT_SECTION_*``).
            parts: Lineas de contenido de la seccion.

        Returns:
            La seccion con encabezado, o cadena vacia si todas las partes son
            vacias.
        """
        rendered = [part for part in parts if part]
        if not rendered:
            return ""
        return marker + "\n" + "\n".join(rendered)

    @staticmethod
    def _format_doc(doc: dict[str, Any]) -> str:
        """Formatea un chunk recuperado como linea estable del prompt.

        Args:
            doc: Chunk con ``id`` y texto (directo o en ``metadata``).

        Returns:
            Linea ``[id] texto`` (o la parte disponible).
        """
        doc_id = str(doc.get("id", "") or "")
        snippet = ContextAssembler._text_of(doc)
        prefix = f"[{doc_id}] " if doc_id else ""
        return f"{prefix}{snippet}" if snippet else prefix.strip()

    @staticmethod
    def _format_task(item: dict[str, Any]) -> str:
        """Formatea una entrada de task context como linea del prompt.

        Args:
            item: Entrada de task context (``agent`` + texto).

        Returns:
            Linea ``- [agent] texto`` (o la parte disponible).
        """
        agent = str(item.get("agent", "") or "")
        text = ContextAssembler._text_of(item)
        prefix = f"- [{agent}] " if agent else "- "
        return f"{prefix}{text}" if text else ""

    @staticmethod
    def _text_of(item: dict[str, Any]) -> str:
        """Extrae el texto de un item (campo directo o dentro de metadata).

        Args:
            item: Chunk o entrada de task context.

        Returns:
            El primer texto no vacio encontrado en ``_TEXT_FIELDS`` (o "").
        """
        for field in _TEXT_FIELDS:
            value = item.get(field)
            if value:
                return str(value)
        meta = item.get("metadata", {}) or {}
        for field in _TEXT_FIELDS:
            value = meta.get(field)
            if value:
                return str(value)
        return ""
