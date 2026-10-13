"""Tests de wiring de memoria — cierre de gaps de integracion (TDD RED->GREEN).

Cubre el gap 2: ``HybridRetriever`` (RRF) y ``CorrectiveRetriever`` (CRAG)
existian sin callers, y ``ContextAssembler`` ensamblaba contexto pero nadie lo
inyectaba en un prompt de forma canonica.

Casos:
  (d) El retrieval usa ``hybrid_retriever`` si se inyecta (spy); si no, la ruta
      legacy. CRAG tiene prioridad y se normalizan ``HybridResult``.
  (e) ``inject_into_prompt`` contiene el contexto con marcadores y respeta el
      orden estatico -> dinamico -> solicitud.
  (f) Mutacion de la estrategia de retrieval y del flag de sentinel rompen el
      contrato (tests discriminantes).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.context_assembler.constants import _EMBEDDING_DIM
from harness.memory_rag.context_assembler.core import (
    _PROMPT_SECTION_DYNAMIC,
    _PROMPT_SECTION_REQUEST,
    _PROMPT_SECTION_STATIC,
)
from harness.memory_rag.context_assembler.models import ContextAssembly

# ---------------------------------------------------------------------------
# Dobles de prueba
# ---------------------------------------------------------------------------


class _SpyStore:
    """Vector store falso que cuenta llamadas a la ruta legacy."""

    def __init__(self) -> None:
        self.search_calls = 0
        self.hybrid_calls = 0

    def search(
        self, collection: str, vector: Any, top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Ruta legacy densa (registra la llamada)."""
        self.search_calls += 1
        return [{"id": "legacy", "score": 0.4, "metadata": {}}]

    def hybrid_search(
        self, collection: str, query_vector: Any, keyword_filter: str, top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Ruta legacy hibrida (registra la llamada)."""
        self.hybrid_calls += 1
        return [{"id": "legacy-hybrid", "score": 0.4, "metadata": {}}]


class _SpyHybrid:
    """Spy de ``HybridRetriever`` (registra llamadas y devuelve items fijos)."""

    def __init__(self, items: list[Any] | None = None) -> None:
        """Configura los items que devolvera ``retrieve``."""
        self.calls: list[tuple[str, int]] = []
        self._items = items if items is not None else [
            {"id": "h1", "score": 0.4, "metadata": {"chunk": "hybrid"}},
        ]

    def retrieve(self, query: str, top_k: int = 5) -> list[Any]:
        """Registra la llamada y devuelve los items configurados."""
        self.calls.append((query, top_k))
        return list(self._items)


class _SpyCorrective:
    """Spy de ``CorrectiveRetriever`` (devuelve un ``CorrectiveResult`` fijo)."""

    def __init__(self, result: Any) -> None:
        """Configura el ``CorrectiveResult`` a devolver."""
        self.calls: list[tuple[str, int]] = []
        self._result = result

    def retrieve(self, query: str, top_k: int = 5) -> Any:
        """Registra la llamada y devuelve el resultado configurado."""
        self.calls.append((query, top_k))
        return self._result


def _embed(text: str) -> np.ndarray:
    """Embedding determinista de ceros (sin modelo externo)."""
    return np.zeros(_EMBEDDING_DIM, dtype=np.float32)


def _assembler(**kwargs: Any) -> ContextAssembler:
    """Construye un assembler con store falso y embedding determinista."""
    return ContextAssembler(vector_store=_SpyStore(), embedding_fn=_embed, **kwargs)


# ---------------------------------------------------------------------------
# (d) retrieval avanzado
# ---------------------------------------------------------------------------


class TestRetrievalWiring:
    """El retrieval usa los retrievers inyectados; legacy si no hay DI."""

    def test_usa_hybrid_si_inyectado(self) -> None:
        """(d) Con hybrid_retriever inyectado, se usa y NO la ruta legacy."""
        store = _SpyStore()
        spy = _SpyHybrid()
        asm = ContextAssembler(vector_store=store, embedding_fn=_embed, hybrid_retriever=spy)

        chunks = asm._retrieve_chunks("consulta", _embed("q"), ["consulta"], top_k=5)

        assert spy.calls == [("consulta", 5)]
        assert [c["id"] for c in chunks] == ["h1"]
        assert store.search_calls == 0
        assert store.hybrid_calls == 0

    def test_legacy_sin_inyeccion(self) -> None:
        """(d) Sin retrievers inyectados, rige la busqueda legacy."""
        store = _SpyStore()
        asm = ContextAssembler(vector_store=store, embedding_fn=_embed)

        chunks = asm._retrieve_chunks("consulta", _embed("q"), ["consulta"], top_k=5)

        assert store.hybrid_calls == 1
        assert store.search_calls == 0
        assert chunks and chunks[0]["id"] == "legacy-hybrid"

    def test_corrective_tiene_prioridad(self) -> None:
        """(d) CRAG (corrective) tiene prioridad sobre hybrid."""
        from harness.memory_rag.corrective_retriever import CorrectiveResult

        corrective = _SpyCorrective(CorrectiveResult(
            items=[{"id": "c1", "score": 0.4, "metadata": {}}],
            action="none", quality_score=0.9, corrected_query="q",
        ))
        hybrid = _SpyHybrid()
        asm = _assembler(hybrid_retriever=hybrid, corrective_retriever=corrective)

        chunks = asm._retrieve_chunks("q", _embed("q"), ["q"], top_k=3)

        assert corrective.calls == [("q", 3)]
        assert hybrid.calls == []
        assert chunks[0]["id"] == "c1"

    def test_normaliza_hybrid_result(self) -> None:
        """(d) Los ``HybridResult`` se normalizan al formato interno de chunks."""
        from harness.memory_rag.hybrid_retriever import HybridResult

        spy = _SpyHybrid(items=[HybridResult(doc_id="hr", score=0.4, metadata={"chunk": "x"})])
        asm = _assembler(hybrid_retriever=spy)

        chunks = asm._retrieve_chunks("q", _embed("q"), ["q"], top_k=3)

        assert chunks[0]["id"] == "hr"
        assert chunks[0]["metadata"] == {"chunk": "x"}

    def test_fallo_de_retriever_degrada_a_legacy(self) -> None:
        """(d) Un retriever inyectado que falla degrada a la ruta legacy."""

        class _Boom:
            def retrieve(self, query: str, top_k: int = 5) -> list[Any]:
                raise RuntimeError("boom")

        store = _SpyStore()
        asm = ContextAssembler(
            vector_store=store, embedding_fn=_embed, hybrid_retriever=_Boom(),
        )

        chunks = asm._retrieve_chunks("q", _embed("q"), ["q"], top_k=3)

        assert store.hybrid_calls == 1
        assert chunks and chunks[0]["id"] == "legacy-hybrid"


# ---------------------------------------------------------------------------
# (e) inject_into_prompt
# ---------------------------------------------------------------------------


class TestInjectIntoPrompt:
    """El contexto ensamblado se inyecta en el prompt con marcadores y orden."""

    def test_contiene_marcadores_y_orden(self) -> None:
        """(e) Marcadores presentes y orden estatico < dinamico < solicitud."""
        asm = _assembler()
        assembly = ContextAssembly(
            instructions="Eres el guardian de calidad.",
            relevant_docs=[{"id": "d1", "content": "chunk relevante uno"}],
            task_context=[{"agent": "builder", "content": "tarea previa"}],
        )

        out = asm.inject_into_prompt("resuelve el bug", assembly)

        assert _PROMPT_SECTION_STATIC in out
        assert _PROMPT_SECTION_DYNAMIC in out
        assert _PROMPT_SECTION_REQUEST in out
        assert (
            out.index(_PROMPT_SECTION_STATIC)
            < out.index(_PROMPT_SECTION_DYNAMIC)
            < out.index(_PROMPT_SECTION_REQUEST)
        )
        assert "chunk relevante uno" in out
        assert "Eres el guardian de calidad." in out
        assert "tarea previa" in out
        assert "builder" in out
        assert "resuelve el bug" in out

    def test_omite_secciones_vacias(self) -> None:
        """(e) Sin contexto, solo se emite la seccion de solicitud."""
        asm = _assembler()

        out = asm.inject_into_prompt("solo solicitud", ContextAssembly())

        assert _PROMPT_SECTION_STATIC not in out
        assert _PROMPT_SECTION_DYNAMIC not in out
        assert out == f"{_PROMPT_SECTION_REQUEST}\nsolo solicitud"

    def test_cache_shape_estable_primero(self) -> None:
        """(e) El bloque estable (rol) precede al dinamico (cache-shape)."""
        asm = _assembler()
        assembly = ContextAssembly(
            instructions="ROL ESTABLE",
            relevant_docs=[{"id": "d1", "content": "DINAMICO"}],
        )

        out = asm.inject_into_prompt("PEDIDO", assembly)

        assert out.index("ROL ESTABLE") < out.index("DINAMICO") < out.index("PEDIDO")


# ---------------------------------------------------------------------------
# (f) mutaciones discriminatorias
# ---------------------------------------------------------------------------


class TestMutationDiscriminators:
    """Sentinela de mutacion: los contratos (b)/(d) son observables."""

    def test_mutacion_estrategia_retrieval_rompe_contrato(self) -> None:
        """(f) Saltar el DI y usar legado cambia el resultado (rompe (d))."""
        store = _SpyStore()
        spy = _SpyHybrid()
        asm = ContextAssembler(vector_store=store, embedding_fn=_embed, hybrid_retriever=spy)

        # Correcto: el DI consulta el hybrid y no toca el store legacy.
        asm._retrieve_chunks("q", _embed("q"), ["q"], top_k=2)
        assert spy.calls and store.hybrid_calls == 0

        # Mutante: forzar la ruta legacy ignora el retriever inyectado.
        spy.calls.clear()
        asm._search_rag_chunks(_embed("q"), ["q"], 2, None)
        assert spy.calls == []
        assert store.hybrid_calls == 1

    def test_mutacion_flag_sentinel_rompe_contrato(self, monkeypatch: Any) -> None:
        """(f) Un ``_sentinel_enabled`` mutante que ignora el env rompe (b)."""
        from harness.orchestrator import debate_runner as dr

        monkeypatch.setenv(dr.ENV_MINORITY_SENTINEL, "0")

        # Correcto: el flag OFF desactiva el sentinel.
        assert dr._resolve_sentinel(dr._UNSET) is None

        # Mutante: `_sentinel_enabled` que ignora el env reintroduce el sentinel.
        monkeypatch.setattr(dr, "_sentinel_enabled", lambda: True)
        assert dr._resolve_sentinel(dr._UNSET) is not None
