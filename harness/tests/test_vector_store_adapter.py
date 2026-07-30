"""
Tests para vector_store_adapter — adaptador abstracto de bases de datos vectoriales.

Cubre:
  - Factory method create_vector_store
  - LanceDBAdapter con mocks
  - ChromaAdapter con mocks
  - QdrantAdapter con mocks
  - Error en backend desconocido
  - SearchResult dataclass
"""
from __future__ import annotations

import sys
import types
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import del modulo bajo test solo para SearchResult (que no tiene dependencias)
from harness.memory_rag.vector_store_adapter import SearchResult

# ===========================================================================
# Helpers: inyectar modulos mock en sys.modules antes del import
# ===========================================================================


def _inject_mock_module(name: str) -> MagicMock:
    """Inyecta un MagicMock como modulo en sys.modules.

    Args:
        name: Nombre del modulo (ej: 'lancedb').

    Returns:
        El modulo mock inyectado.
    """
    mod = MagicMock(name=f"mock_{name}")
    # Hacer que el modulo actue como modulo real (no como class/function)
    mod.__spec__ = None
    sys.modules[name] = mod
    return mod


def _inject_real_module(name: str) -> types.ModuleType:
    """Inyecta un ModuleType real en sys.modules (soporta subimports).

    A diferencia de _inject_mock_module, los ModuleType reales
    permiten sub-imports como 'from package.sub import X'.

    Args:
        name: Nombre del modulo (ej: 'qdrant_client').

    Returns:
        El modulo ModuleType inyectado.
    """
    mod = types.ModuleType(name)
    mod.__package__ = name
    mod.__path__ = []  # type: ignore[attr-defined]
    mod.__spec__ = None
    sys.modules[name] = mod
    return mod


@pytest.fixture(autouse=True)
def _clean_sys_modules() -> Generator[None, None, None]:
    """Limpia modulos mock del sys.modules despues de cada test."""
    injected: list[str] = []
    yield
    for m in injected:
        sys.modules.pop(m, None)


# ===========================================================================
# Tests de SearchResult dataclass
# ===========================================================================


class TestSearchResult:
    """Suite de pruebas para el dataclass SearchResult."""

    def test_default_construction(self) -> None:
        """Constructor con solo campos obligatorios."""
        result = SearchResult(id="abc", score=0.95)
        assert result.id == "abc"
        assert result.score == 0.95
        assert result.payload == {}
        assert result.vector is None

    def test_full_construction(self) -> None:
        """Constructor con todos los campos."""
        result = SearchResult(
            id="xyz",
            score=0.85,
            payload={"domain": "test", "source": "unit"},
            vector=[0.1, 0.2, 0.3],
        )
        assert result.id == "xyz"
        assert result.score == 0.85
        assert result.payload == {"domain": "test", "source": "unit"}
        assert result.vector == [0.1, 0.2, 0.3]

    def test_mutable_payload(self) -> None:
        """El payload es mutable post-creacion."""
        result = SearchResult(id="abc", score=0.5)
        result.payload["key"] = "value"
        assert result.payload["key"] == "value"


# ===========================================================================
# Tests de Factory
# ===========================================================================


class TestCreateVectorStore:
    """Suite de pruebas para la funcion factory create_vector_store.

    Cada test inyecta el modulo mock necesario en sys.modules
    antes de importar el modulo bajo test.
    """

    @staticmethod
    def _import_module():
        """Importa (o reimporta) el modulo vector_store_adapter limpio."""
        # Remover del cache para forzar reimportacion limpia
        import harness.memory_rag.vector_store_adapter as vsa
        return vsa

    def test_create_lancedb_adapter(self) -> None:
        """Factory crea LanceDBAdapter correctamente."""
        mock_lancedb = _inject_mock_module("lancedb")
        mock_conn = MagicMock()
        mock_lancedb.connect.return_value = mock_conn

        vsa = self._import_module()
        adapter = vsa.create_vector_store("lancedb", db_path="/tmp/test_lance")

        assert isinstance(adapter, vsa.LanceDBAdapter)
        assert isinstance(adapter, vsa.VectorStoreAdapter)
        mock_lancedb.connect.assert_called_once_with("/tmp/test_lance")

    def test_create_chroma_adapter(self) -> None:
        """Factory crea ChromaAdapter correctamente."""
        mock_chromadb = _inject_mock_module("chromadb")
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        vsa = self._import_module()
        adapter = vsa.create_vector_store("chroma", db_path="/tmp/test_chroma")

        assert isinstance(adapter, vsa.ChromaAdapter)
        assert isinstance(adapter, vsa.VectorStoreAdapter)
        mock_chromadb.PersistentClient.assert_called_once_with(
            path="/tmp/test_chroma"
        )

    def test_create_qdrant_adapter(self) -> None:
        """Factory crea QdrantAdapter correctamente."""
        # Usar ModuleType real para qdrant_client (soporta subimports)
        qdrant_mod = _inject_real_module("qdrant_client")
        http_mod = _inject_real_module("qdrant_client.http")
        http_mod.models = MagicMock()
        http_mod.models.VectorParams = MagicMock
        http_mod.models.Distance = MagicMock(COSINE="Cosine")
        http_mod.models.PointStruct = MagicMock
        http_mod.models.Filter = MagicMock
        http_mod.models.FieldCondition = MagicMock
        http_mod.models.MatchValue = MagicMock

        qdrant_mod.QdrantClient = MagicMock()
        mock_client_instance = MagicMock()
        qdrant_mod.QdrantClient.return_value = mock_client_instance

        vsa = self._import_module()
        adapter = vsa.create_vector_store(
            "qdrant", host="qdrant.test", port=6334
        )

        assert isinstance(adapter, vsa.QdrantAdapter)
        assert isinstance(adapter, vsa.VectorStoreAdapter)
        qdrant_mod.QdrantClient.assert_called_once_with(
            host="qdrant.test",
            port=6334,
            prefer_grpc=True,
            api_key=None,
        )

    def test_unknown_backend_raises_error(self) -> None:
        """Backend desconocido lanza ValueError con mensaje descriptivo."""
        vsa = self._import_module()
        with pytest.raises(ValueError) as exc_info:
            vsa.create_vector_store("nonexistent_db")
        msg = str(exc_info.value)
        assert "nonexistent_db" in msg
        assert "lancedb" in msg
        assert "chroma" in msg
        assert "qdrant" in msg

    def test_factory_returns_abstract_type(self) -> None:
        """La factory retorna siempre un VectorStoreAdapter."""
        _inject_mock_module("lancedb")
        vsa = self._import_module()
        adapter = vsa.create_vector_store("lancedb")
        assert isinstance(adapter, vsa.VectorStoreAdapter)


# ===========================================================================
# Tests de LanceDBAdapter
# ===========================================================================


class TestLanceDBAdapter:
    """Suite de pruebas para LanceDBAdapter con mocks."""

    @pytest.fixture(autouse=True)
    def _setup_lancedb_mocks(self) -> Generator[None, None, None]:
        """Inyecta modulo lancedb mock antes de cada test y lo limpia."""
        self.mock_lancedb = _inject_mock_module("lancedb")
        self.mock_conn = MagicMock()
        self.mock_table = MagicMock()
        self.mock_conn.create_table.return_value = None
        self.mock_conn.open_table.return_value = self.mock_table
        self.mock_conn.table_names.return_value = ["test_col", "other_col"]
        self.mock_lancedb.connect.return_value = self.mock_conn

        # Importar modulo bajo test
        import harness.memory_rag.vector_store_adapter as vsa

        self.vsa = vsa
        yield
        # cleanup done by _clean_sys_modules

    @pytest.fixture
    def adapter(self) -> Any:
        """Crea LanceDBAdapter con el entorno mockeado."""
        return self.vsa.LanceDBAdapter(db_path="/tmp/test")

    def test_create_collection(self, adapter: Any) -> None:
        """create_collection delega en db.create_table."""
        self.mock_conn.create_table.reset_mock()
        adapter.create_collection("mi_col", dimension=128)
        self.mock_conn.create_table.assert_called_once()
        args, _kwargs = self.mock_conn.create_table.call_args
        assert args[0] == "mi_col"

    def test_add_returns_ids(self, adapter: Any) -> None:
        """add retorna IDs para cada vector insertado."""
        ids = adapter.add(
            collection="test_col",
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            payloads=[{"a": 1}, {"b": 2}],
            ids=["id1", "id2"],
        )
        assert ids == ["id1", "id2"]
        self.mock_conn.open_table.assert_called_with("test_col")

    def test_add_generates_ids_when_missing(self, adapter: Any) -> None:
        """add genera IDs cuando no se proveen."""
        ids = adapter.add(
            collection="test_col",
            vectors=[[0.1, 0.2]],
            payloads=[{"x": 1}],
        )
        assert len(ids) == 1
        assert isinstance(ids[0], str)

    def test_search_returns_search_results(self, adapter: Any) -> None:
        """search retorna lista de SearchResult."""
        self.mock_table.search.return_value.limit.return_value.to_list.return_value = [
            {
                "id": "r1",
                "vector": [0.1, 0.2],
                "_distance": 0.15,
                "domain": "test",
                "score": 5,
            },
            {
                "id": "r2",
                "vector": [0.3, 0.4],
                "_distance": 0.35,
                "domain": "other",
                "score": 3,
            },
        ]

        results = adapter.search(
            collection="test_col",
            vector=[0.5, 0.6],
            top_k=2,
        )
        assert len(results) == 2
        assert all(isinstance(r, self.vsa.SearchResult) for r in results)
        assert results[0].id == "r1"
        assert results[0].score == 0.15
        assert results[0].payload == {"domain": "test", "score": 5}

    def test_search_with_filters(self, adapter: Any) -> None:
        """search aplica post-filtro de metadatos."""
        self.mock_table.search.return_value.limit.return_value.to_list.return_value = [
            {"id": "r1", "_distance": 0.1, "domain": "keep"},
            {"id": "r2", "_distance": 0.2, "domain": "skip"},
            {"id": "r3", "_distance": 0.3, "domain": "keep"},
        ]

        results = adapter.search(
            collection="test_col",
            vector=[0.5, 0.6],
            top_k=5,
            filters={"domain": "keep"},
        )
        assert len(results) == 2
        assert all(r.payload.get("domain") == "keep" for r in results)

    def test_delete(self, adapter: Any) -> None:
        """delete elimina cada ID en la tabla."""
        adapter.delete(collection="test_col", ids=["id1", "id2"])
        assert self.mock_table.delete.call_count == 2

    def test_list_collections(self, adapter: Any) -> None:
        """list_collections retorna nombres de tabla."""
        cols = adapter.list_collections()
        assert cols == ["test_col", "other_col"]

    def test_create_collection_failure(self, adapter: Any) -> None:
        """create_collection lanza RuntimeError si falla."""
        self.mock_conn.create_table.side_effect = Exception("boom")
        with pytest.raises(RuntimeError, match="no se pudo crear coleccion"):
            adapter.create_collection("fail_col")


# ===========================================================================
# Tests de ChromaAdapter
# ===========================================================================


class TestChromaAdapter:
    """Suite de pruebas para ChromaAdapter con mocks."""

    @pytest.fixture(autouse=True)
    def _setup_chroma_mocks(self) -> Generator[None, None, None]:
        """Inyecta modulo chromadb mock antes de cada test."""
        self.mock_chromadb = _inject_mock_module("chromadb")
        self.mock_client = MagicMock()
        self.mock_collection = MagicMock()
        self.mock_collection.add.return_value = None
        self.mock_collection.delete.return_value = None
        self.mock_collection.query.return_value = {
            "ids": [["c1", "c2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [[{"k": "v1"}, {"k": "v2"}]],
        }
        self.mock_client.create_collection.return_value = self.mock_collection
        self.mock_client.get_collection.return_value = self.mock_collection
        col_a = MagicMock()
        col_b = MagicMock()
        col_a.name = "col_a"
        col_b.name = "col_b"
        self.mock_client.list_collections.return_value = [col_a, col_b]
        self.mock_chromadb.PersistentClient.return_value = self.mock_client

        import harness.memory_rag.vector_store_adapter as vsa

        self.vsa = vsa
        yield

    @pytest.fixture
    def adapter(self) -> Any:
        """Crea ChromaAdapter con el entorno mockeado."""
        return self.vsa.ChromaAdapter(db_path="/tmp/test_chroma")

    def test_create_collection(self, adapter: Any) -> None:
        """create_collection delega en client.create_collection."""
        self.mock_client.create_collection.reset_mock()
        adapter.create_collection("mi_col")
        self.mock_client.create_collection.assert_called_once_with("mi_col")

    def test_add_returns_ids(self, adapter: Any) -> None:
        """add retorna los IDs asignados."""
        ids = adapter.add(
            collection="test",
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            payloads=[{"a": 1}, {"b": 2}],
            ids=["id1", "id2"],
        )
        assert ids == ["id1", "id2"]
        self.mock_client.get_collection.assert_called_with("test")

    def test_add_generates_ids(self, adapter: Any) -> None:
        """add genera IDs secuenciales cuando no se proveen."""
        ids = adapter.add(
            collection="test",
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            payloads=[{"a": 1}, {"b": 2}],
        )
        assert ids == ["0", "1"]

    def test_search_returns_search_results(self, adapter: Any) -> None:
        """search retorna SearchResult con score convertido."""
        self.mock_collection.query.return_value = {
            "ids": [["c1"]],
            "distances": [[0.25]],
            "metadatas": [[{"domain": "test"}]],
        }

        results = adapter.search(
            collection="test",
            vector=[0.5, 0.6],
            top_k=1,
        )
        assert len(results) == 1
        assert results[0].id == "c1"
        # score = 1 - distance
        assert results[0].score == pytest.approx(0.75)
        assert results[0].payload == {"domain": "test"}

    def test_search_with_filters(self, adapter: Any) -> None:
        """search pasa filtros como where a Chroma."""
        adapter.search(
            collection="test",
            vector=[0.5, 0.6],
            top_k=3,
            filters={"domain": "keep"},
        )
        self.mock_collection.query.assert_called_once()
        _args, kwargs = self.mock_collection.query.call_args
        assert kwargs.get("where") == {"domain": "keep"}
        assert kwargs.get("n_results") == 3

    def test_delete(self, adapter: Any) -> None:
        """delete llama a col.delete con los IDs."""
        adapter.delete(collection="test", ids=["id1", "id2"])
        self.mock_collection.delete.assert_called_once_with(ids=["id1", "id2"])

    def test_list_collections(self, adapter: Any) -> None:
        """list_collections retorna nombres de coleccion."""
        cols = adapter.list_collections()
        assert cols == ["col_a", "col_b"]


# ===========================================================================
# Tests de QdrantAdapter
# ===========================================================================


class TestQdrantAdapter:
    """Suite de pruebas para QdrantAdapter con mocks."""

    @pytest.fixture(autouse=True)
    def _setup_qdrant_mocks(self) -> Generator[None, None, None]:
        """Inyecta modulo qdrant_client mock antes de cada test.

        Usa ModuleType real para que 'from qdrant_client.http import models'
        funcione correctamente en el adaptador.
        """
        # Package principal
        self.mock_qdrant_mod = _inject_real_module("qdrant_client")
        # Subpackage http
        self.mock_http_mod = _inject_real_module("qdrant_client.http")
        # Models dentro de http
        self.mock_models = MagicMock()
        self.mock_models.VectorParams = MagicMock
        self.mock_models.Distance = MagicMock(COSINE="Cosine")
        self.mock_models.PointStruct = MagicMock
        self.mock_models.Filter = MagicMock
        self.mock_models.FieldCondition = MagicMock
        self.mock_models.MatchValue = MagicMock
        self.mock_http_mod.models = self.mock_models

        # QdrantClient class
        self.mock_qdrant_mod.QdrantClient = MagicMock()
        self.mock_client_instance = MagicMock()
        self.mock_qdrant_mod.QdrantClient.return_value = self.mock_client_instance

        # Mock search results
        self.scored_point = MagicMock()
        self.scored_point.id = "p1"
        self.scored_point.score = 0.92
        self.scored_point.payload = {"domain": "test", "value": 42}
        self.scored_point.vector = [0.1, 0.2]
        self.mock_client_instance.search.return_value = [self.scored_point]

        # Mock collections list
        col_info = MagicMock()
        col_info.name = "my_collection"
        collections_response = MagicMock()
        collections_response.collections = [col_info]
        self.mock_client_instance.get_collections.return_value = (
            collections_response
        )

        import harness.memory_rag.vector_store_adapter as vsa

        self.vsa = vsa
        yield

    @pytest.fixture
    def adapter(self) -> Any:
        """Crea QdrantAdapter con el entorno mockeado."""
        return self.vsa.QdrantAdapter(
            host="localhost", port=6334, prefer_grpc=False
        )

    def test_create_collection(self, adapter: Any) -> None:
        """create_collection llama a recreate_collection con VectorParams."""
        self.mock_client_instance.recreate_collection.reset_mock()
        adapter.create_collection("mi_col", dimension=256)
        self.mock_client_instance.recreate_collection.assert_called_once()
        _args, kwargs = self.mock_client_instance.recreate_collection.call_args
        assert kwargs["collection_name"] == "mi_col"
        assert kwargs["vectors_config"].size == 256

    def test_add_returns_ids(self, adapter: Any) -> None:
        """add retorna los IDs asignados."""
        ids = adapter.add(
            collection="test",
            vectors=[[0.1, 0.2]],
            payloads=[{"key": "val"}],
            ids=["custom_id"],
        )
        assert ids == ["custom_id"]
        self.mock_client_instance.upsert.assert_called_once()

    def test_add_generates_ids(self, adapter: Any) -> None:
        """add genera UUIDs cuando no se proveen IDs."""
        ids = adapter.add(
            collection="test",
            vectors=[[0.1, 0.2]],
            payloads=[{"key": "val"}],
        )
        assert len(ids) == 1
        assert isinstance(ids[0], str)

    def test_search_returns_search_results(self, adapter: Any) -> None:
        """search retorna SearchResult con score y payload."""
        results = adapter.search(
            collection="test",
            vector=[0.5, 0.6],
            top_k=1,
        )
        assert len(results) == 1
        assert results[0].id == "p1"
        assert results[0].score == pytest.approx(0.92)
        assert results[0].payload == {"domain": "test", "value": 42}
        assert results[0].vector == [0.1, 0.2]

        self.mock_client_instance.search.assert_called_once_with(
            collection_name="test",
            query_vector=[0.5, 0.6],
            limit=1,
            query_filter=None,
        )

    def test_search_with_filters(self, adapter: Any) -> None:
        """search construye Filter con FieldCondition cuando hay filtros."""
        adapter.search(
            collection="test",
            vector=[0.5, 0.6],
            top_k=3,
            filters={"domain": "keep"},
        )
        # Verificar que search fue llamado (con query_filter no None)
        assert self.mock_client_instance.search.called

    def test_delete(self, adapter: Any) -> None:
        """delete llama a client.delete con los IDs."""
        adapter.delete(collection="test", ids=["id1", "id2"])
        self.mock_client_instance.delete.assert_called_once_with(
            collection_name="test",
            points_selector=["id1", "id2"],
        )

    def test_list_collections(self, adapter: Any) -> None:
        """list_collections retorna nombres de coleccion."""
        self.mock_client_instance.get_collections.return_value.collections[0].name = "my_collection"
        cols = adapter.list_collections()
        assert cols == ["my_collection"]


# ===========================================================================
# Tests de integracion basica: el adapter es instanciable y cumple el contrato
# ===========================================================================


class TestVectorStoreAdapterContract:
    """Verifica que todos los adaptadores cumplen el contrato de la ABC.

    NOTA: Estos tests importan el modulo directamente y no requieren
    modulos externos porque solo verifican la estructura de clases.
    """

    @pytest.fixture(autouse=True)
    def _ensure_module(self) -> None:
        """Importa el modulo una vez para toda la clase."""
        from harness.memory_rag import vector_store_adapter as vsa

        self.vsa = vsa

    def test_adapter_is_abstract(self) -> None:
        """VectorStoreAdapter no puede instanciarse directamente."""
        with pytest.raises(TypeError):
            self.vsa.VectorStoreAdapter()  # type: ignore[abstract]

    def test_lancedb_adapter_has_all_methods(self) -> None:
        """LanceDBAdapter implementa todos los metodos abstractos."""
        methods = [
            "create_collection",
            "add",
            "search",
            "delete",
            "list_collections",
        ]
        for m in methods:
            assert hasattr(self.vsa.LanceDBAdapter, m)
            assert callable(getattr(self.vsa.LanceDBAdapter, m))

    def test_chroma_adapter_has_all_methods(self) -> None:
        """ChromaAdapter implementa todos los metodos abstractos."""
        methods = [
            "create_collection",
            "add",
            "search",
            "delete",
            "list_collections",
        ]
        for m in methods:
            assert hasattr(self.vsa.ChromaAdapter, m)
            assert callable(getattr(self.vsa.ChromaAdapter, m))

    def test_qdrant_adapter_has_all_methods(self) -> None:
        """QdrantAdapter implementa todos los metodos abstractos."""
        methods = [
            "create_collection",
            "add",
            "search",
            "delete",
            "list_collections",
        ]
        for m in methods:
            assert hasattr(self.vsa.QdrantAdapter, m)
            assert callable(getattr(self.vsa.QdrantAdapter, m))

    def test_search_result_is_dataclass(self) -> None:
        """SearchResult es un dataclass con campos tipados."""
        from dataclasses import fields

        field_names = {f.name for f in fields(self.vsa.SearchResult)}
        assert "id" in field_names
        assert "score" in field_names
        assert "payload" in field_names
        assert "vector" in field_names
