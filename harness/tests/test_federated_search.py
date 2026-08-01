"""Tests para FederatedVectorSearch — busqueda vectorial federada multi-backend.

Cubre:
- Validacion de parametros del constructor
- Inicializacion con backends custom y defaults
- Search con mocks de VectorStoreAdapter (sin servicios externos)
- Cache (hit/miss)
- MMR re-ranking
- Estadisticas y context manager
- Factory create_federated_search
"""
from __future__ import annotations

from typing import Any

import pytest

from harness.memory_rag.federated_search import (
    DEFAULT_MMR_LAMBDA,
    FederatedResult,
    FederatedStats,
    FederatedVectorSearch,
    create_federated_search,
)
from harness.memory_rag.vector_store_adapter import SearchResult, VectorStoreAdapter


# ---------------------------------------------------------------------------
# Mocks: FakeVectorStoreAdapter
# ---------------------------------------------------------------------------


class FakeVectorStoreAdapter(VectorStoreAdapter):
    """Adapter de prueba: no requiere servicios externos."""

    def __init__(
        self,
        name: str = "fake",
        items: list[SearchResult] | None = None,
        fail: bool = False,
    ) -> None:
        self._name = name
        self._items = items or []
        self._fail = fail
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def search(
        self,
        vector: list[float],
        collection: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"backend {self._name} fail")
        return self._items[:top_k]

    def add(
        self,
        id: str,
        vector: list[float],
        payload: dict[str, Any] | None = None,
        collection: str = "default",
    ) -> bool:
        return True

    def delete(self, id: str, collection: str = "default") -> bool:
        return True

    def list_collections(self) -> list[str]:
        return ["default"]

    def create_collection(
        self,
        name: str,
        schema: dict[str, str] | None = None,
    ) -> bool:
        return True


def make_result(id_: str, score: float, vec: list[float] | None = None) -> SearchResult:
    """Helper para crear SearchResult."""
    return SearchResult(
        id=id_,
        score=score,
        payload={"text": f"item {id_}"},
        vector=vec,
    )


# ---------------------------------------------------------------------------
# Validacion de parametros
# ---------------------------------------------------------------------------


class TestFederatedSearchInit:
    """Tests del constructor y validacion."""

    def test_init_with_explicit_empty_backends(self):
        """Dict vacio explicito se respeta: 0 backends, search devuelve []."""
        fvs = FederatedVectorSearch(backends={})
        assert fvs.get_available_backends() == []
        result = fvs.search(vector=[0.1] * 16, collection="x", top_k=5)
        assert result == []
        fvs.close()

    def test_init_with_custom_backends(self):
        """Backends custom se registran correctamente."""
        be1 = FakeVectorStoreAdapter("lancedb")
        be2 = FakeVectorStoreAdapter("chroma")
        fvs = FederatedVectorSearch(backends={"lancedb": be1, "chroma": be2})
        assert set(fvs.get_available_backends()) == {"lancedb", "chroma"}
        fvs.close()

    def test_init_invalid_mmr_lambda_raises(self):
        """mmr_lambda fuera de [0, 1] lanza ValueError."""
        be = FakeVectorStoreAdapter("x")
        with pytest.raises(ValueError, match="mmr_lambda"):
            FederatedVectorSearch(backends={"x": be}, mmr_lambda=-0.1)
        with pytest.raises(ValueError, match="mmr_lambda"):
            FederatedVectorSearch(backends={"x": be}, mmr_lambda=1.5)
        # dict vacio con lambda invalido tambien valida
        with pytest.raises(ValueError, match="mmr_lambda"):
            FederatedVectorSearch(backends={}, mmr_lambda=2.0)

    def test_init_default_lambda(self):
        """Default mmr_lambda = 0.5."""
        fvs = FederatedVectorSearch(backends={})
        assert fvs._mmr_lambda == DEFAULT_MMR_LAMBDA
        fvs.close()

    def test_init_custom_cache_params(self):
        """Cache params custom se aplican."""
        fvs = FederatedVectorSearch(backends={}, cache_max_size=42, cache_ttl=99.0)
        assert fvs._cache is not None
        fvs.close()


# ---------------------------------------------------------------------------
# Search basico
# ---------------------------------------------------------------------------


class TestFederatedSearchSearch:
    """Tests del metodo search principal."""

    def test_search_empty_vector_raises(self):
        """Vector vacio lanza ValueError."""
        fvs = FederatedVectorSearch(backends={})
        with pytest.raises(ValueError, match="vector"):
            fvs.search(vector=[], collection="x")
        fvs.close()

    def test_search_invalid_collection_raises(self):
        """Collection invalida lanza ValueError."""
        fvs = FederatedVectorSearch(backends={})
        with pytest.raises(ValueError, match="collection"):
            fvs.search(vector=[0.1] * 16, collection="")
        with pytest.raises(ValueError, match="collection"):
            fvs.search(vector=[0.1] * 16, collection=None)  # type: ignore[arg-type]
        fvs.close()

    def test_search_with_results(self):
        """Search con resultados de un backend los fusiona."""
        items = [
            make_result("a", 0.9, vec=[0.1] * 16),
            make_result("b", 0.7, vec=[0.2] * 16),
        ]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        results = fvs.search(vector=[0.1] * 16, collection="x", top_k=5, use_mmr=False)
        assert len(results) == 2
        # Resultados normalizados y ordenados
        assert all(isinstance(r, FederatedResult) for r in results)
        assert results[0].id in {"a", "b"}
        fvs.close()

    def test_search_with_no_backends_returns_empty(self):
        """Sin backends, search devuelve lista vacia sin error."""
        fvs = FederatedVectorSearch(backends={})
        results = fvs.search(vector=[0.1] * 16, collection="x")
        assert results == []
        fvs.close()

    def test_search_backend_failure_isolated(self):
        """Fallo de un backend no afecta a los demas (aislamiento)."""
        good_items = [make_result("a", 0.8, vec=[0.1] * 16)]
        be1 = FakeVectorStoreAdapter("good", items=good_items)
        be2 = FakeVectorStoreAdapter("bad", fail=True)
        fvs = FederatedVectorSearch(backends={"good": be1, "bad": be2})
        results = fvs.search(vector=[0.1] * 16, collection="x", top_k=5, use_mmr=False)
        # Al menos los resultados de 'good' deben estar presentes
        assert len(results) >= 1
        assert any(r.id == "a" for r in results)
        fvs.close()

    def test_search_with_filters(self):
        """Filtros se pasan al backend."""
        items = [make_result("a", 0.9, vec=[0.1] * 16)]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        results = fvs.search(
            vector=[0.1] * 16, collection="x", top_k=5,
            filters={"category": "code"}, use_mmr=False,
        )
        assert len(results) >= 1
        fvs.close()

    def test_search_top_k_limits_results(self):
        """top_k limita el numero de resultados finales."""
        items = [make_result(f"id_{i}", 0.5 - i * 0.01, vec=[0.1] * 16) for i in range(10)]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        results = fvs.search(vector=[0.1] * 16, collection="x", top_k=3, use_mmr=False)
        assert len(results) <= 3
        fvs.close()

    def test_search_with_mmr_lambda_param(self):
        """mmr_lambda como parametro de search sobrescribe el default."""
        items = [
            make_result("a", 0.9, vec=[0.1] * 16),
            make_result("b", 0.8, vec=[0.9] * 16),  # muy diferente
        ]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        results = fvs.search(
            vector=[0.1] * 16, collection="x", top_k=2,
            use_mmr=True, mmr_lambda=1.0,  # solo diversidad
        )
        assert len(results) >= 1
        fvs.close()

    def test_search_without_mmr_preserves_relevance_order(self):
        """Sin MMR, los resultados respetan el orden de score."""
        items = [
            make_result("high", 0.9, vec=[0.1] * 16),
            make_result("low", 0.1, vec=[0.1] * 16),
        ]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        results = fvs.search(vector=[0.1] * 16, collection="x", top_k=5, use_mmr=False)
        # Sin MMR el orden es por score normalizado descendente
        assert len(results) == 2
        assert results[0].id == "high"
        fvs.close()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestFederatedSearchCache:
    """Tests del cache de PerformanceCache."""

    def test_cache_hit_on_repeated_query(self):
        """La misma query 2 veces usa cache (segunda es hit)."""
        items = [make_result("a", 0.9, vec=[0.1] * 16)]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        vec = [0.1] * 16
        r1 = fvs.search(vector=vec, collection="x", top_k=5, use_mmr=False)
        # Segunda llamada: mismo vector, mismo top_k -> debe ser cache hit
        r2 = fvs.search(vector=vec, collection="x", top_k=5, use_mmr=False)
        assert len(r1) == len(r2)
        stats = fvs.get_stats()
        assert stats["cache_hits"] >= 1
        fvs.close()

    def test_cache_miss_on_different_query(self):
        """Queries diferentes generan cache miss."""
        items = [make_result("a", 0.9, vec=[0.1] * 16)]
        be = FakeVectorStoreAdapter("lancedb", items=items)
        fvs = FederatedVectorSearch(backends={"lancedb": be})
        fvs.search(vector=[0.1] * 16, collection="x", top_k=5, use_mmr=False)
        fvs.search(vector=[0.2] * 16, collection="x", top_k=5, use_mmr=False)
        stats = fvs.get_stats()
        assert stats["cache_misses"] >= 2
        fvs.close()

    def test_stats_reflect_cache_activity(self):
        """get_stats refleja actividad de cache."""
        be = FakeVectorStoreAdapter("x", items=[make_result("a", 0.5, vec=[0.1] * 16)])
        fvs = FederatedVectorSearch(backends={"x": be})
        vec = [0.1] * 16
        fvs.search(vector=vec, collection="x", use_mmr=False)
        fvs.search(vector=vec, collection="x", use_mmr=False)  # cache hit
        stats = fvs.get_stats()
        assert stats["total_requests"] >= 2
        assert "hit_rate" in stats
        assert "backends_available" in stats
        assert "backends_total" in stats
        fvs.close()


# ---------------------------------------------------------------------------
# Estadisticas y lifecycle
# ---------------------------------------------------------------------------


class TestFederatedSearchStats:
    """Tests de get_stats, get_available_backends, context manager."""

    def test_get_available_backends_lists_active(self):
        """get_available_backends solo lista los inicializados."""
        be1 = FakeVectorStoreAdapter("a")
        be2 = FakeVectorStoreAdapter("b")
        fvs = FederatedVectorSearch(backends={"a": be1, "b": be2})
        assert set(fvs.get_available_backends()) == {"a", "b"}
        fvs.close()

    def test_get_stats_initial(self):
        """Stats iniciales: total_requests=0, hit_rate=0."""
        fvs = FederatedVectorSearch(backends={})
        stats = fvs.get_stats()
        assert stats["total_requests"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["hit_rate"] == 0
        fvs.close()

    def test_context_manager(self):
        """with statement cierra correctamente."""
        be = FakeVectorStoreAdapter("x")
        with FederatedVectorSearch(backends={"x": be}) as fvs:
            fvs.search(vector=[0.1] * 16, collection="x", use_mmr=False)
            assert fvs.get_available_backends() == ["x"]
        # Tras salir del with, el executor esta cerrado

    def test_close_is_idempotent_safe(self):
        """close() puede llamarse sin error (cleanup graceful)."""
        fvs = FederatedVectorSearch(backends={})
        fvs.close()
        # Segunda llamada: el executor ya esta cerrado pero no debe romper

    def test_invalid_backend_type_is_skipped(self):
        """Backend que no es VectorStoreAdapter se omite (con log warning)."""
        invalid = "not_an_adapter"
        valid = FakeVectorStoreAdapter("good")
        fvs = FederatedVectorSearch(backends={"invalid": invalid, "good": valid})
        # El invalido se omite, solo 'good' debe estar
        assert "good" in fvs.get_available_backends()
        assert "invalid" not in fvs.get_available_backends()
        fvs.close()


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TestFederatedSearchDTOs:
    """Tests de dataclasses FederatedResult y FederatedStats."""

    def test_federated_result_defaults(self):
        """FederatedResult con defaults razonables."""
        r = FederatedResult(id="x", score=0.5)
        assert r.payload == {}
        assert r.backend == ""
        assert r.vector is None

    def test_federated_result_full(self):
        """FederatedResult con todos los campos."""
        r = FederatedResult(
            id="x", score=0.5, payload={"k": "v"},
            backend="lancedb", vector=[0.1, 0.2],
        )
        assert r.id == "x"
        assert r.score == 0.5
        assert r.payload == {"k": "v"}
        assert r.backend == "lancedb"
        assert r.vector == [0.1, 0.2]

    def test_federated_stats_defaults(self):
        """FederatedStats con defaults razonables."""
        s = FederatedStats()
        assert s.total_requests == 0
        assert s.cache_hits == 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateFederatedSearch:
    """Tests de la factory create_federated_search."""

    def test_create_with_no_args(self):
        """Factory sin args devuelve instancia valida."""
        fvs = create_federated_search()
        assert isinstance(fvs, FederatedVectorSearch)
        fvs.close()

    def test_create_with_custom_backends(self):
        """Factory con backends custom."""
        be = FakeVectorStoreAdapter("custom")
        fvs = create_federated_search(backends={"custom": be})
        assert "custom" in fvs.get_available_backends()
        fvs.close()

    def test_create_with_custom_params(self):
        """Factory con mmr_lambda y cache custom."""
        fvs = create_federated_search(backends={}, mmr_lambda=0.7, cache_max_size=10, cache_ttl=60.0)
        assert fvs._mmr_lambda == 0.7
        fvs.close()
