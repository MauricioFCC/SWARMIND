"""Fixtures compartidas para todos los tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from harness.memory_rag.lance_schemas import DEFAULT_COLLECTIONS
from harness.memory_rag.lance_vector_store import (
    LanceVectorStore,
)
from harness.tests.mock_vector_store import MockVectorStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Colecciones por defecto (compatibles con LanceVectorStore.DEFAULT_COLLECTIONS)
# para que los tests existentes sigan funcionando sin cambios.
# ---------------------------------------------------------------------------

_MOCK_DEFAULT_COLLECTIONS = [
    "asi_cognition_store",
    "rag_chunks",
    "tasks_board",
    "agent_workspace_logs",
    "procedural_skills",
    "prompt_evolution_log",
    "scheduler_log",
    "hitl_approval_log",
    "semantic_cache",
    "iteration_reports",
    "agent_performance",
    "skill_effectiveness",
    "telemetry_events",
    "session_kpis",
    "agent_interactions",
]


def _mock_store_with_defaults() -> MockVectorStore:
    """Crea MockVectorStore con las colecciones por defecto pre-creadas."""
    store = MockVectorStore()
    for name in _MOCK_DEFAULT_COLLECTIONS:
        store.create_collection(name)
    return store


# ---------------------------------------------------------------------------
# Fixtures de infraestructura pesada — scope=session para reutilizacion
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mock_store():
    """MockVectorStore compartido por toda la sesion de tests (session scope).

    Incluye las colecciones por defecto. Permite paralelismo real con
    pytest-xdist al evitar locks de base de datos.
    No requiere LanceDB instalado.
    """
    return _mock_store_with_defaults()


@pytest.fixture
def vector_store():
    """VectorStore aislado por test (function scope) usando MockVectorStore.

    Reemplaza LanceVectorStore real con implementacion en memoria.
    Incluye las colecciones por defecto para compatibilidad con tests existentes.
    No requiere LanceDB instalado y permite tests paralelos.
    """
    return _mock_store_with_defaults()


@pytest.fixture
def agent_bus(vector_store):
    """AgentBus conectado al vector store."""
    from harness.orchestrator.agent_bus import AgentBus
    return AgentBus(vector_store=vector_store)


@pytest.fixture
def delegation_engine():
    """DelegationEngine."""
    from harness.orchestrator.delegation_engine import DelegationEngine
    return DelegationEngine()


@pytest.fixture
def context_assembler(vector_store):
    """ContextAssembler."""
    from harness.memory_rag.context_assembler import ContextAssembler
    return ContextAssembler(vector_store=vector_store)


@pytest.fixture
def hermes_bridge():
    """HermesBridge."""
    from harness.memory_rag.hermes_bridge import HermesBridge
    return HermesBridge()


@pytest.fixture
def cognition_sync(vector_store):
    """CognitionSync."""
    from harness.evolve_loop.cognition_sync import CognitionSync
    return CognitionSync(vector_store=vector_store)


@pytest.fixture
def semantic_cache(vector_store):
    """SemanticCache con MockVectorStore (evita dependencia de LanceDB)."""
    from harness.memory_rag.semantic_cache import SemanticCache
    return SemanticCache(vector_store=vector_store)


@pytest.fixture
def agent_discovery():
    """Agent discovery."""
    from harness.orchestrator.agent_discovery import discover_agents_recursive
    return discover_agents_recursive()


@pytest.fixture
def trajectory_compressor():
    """TrajectoryCompressor."""
    from harness.memory_rag.trajectory_compressor import TrajectoryCompressor
    return TrajectoryCompressor()


@pytest.fixture
def context_injector():
    """ContextInjector."""
    from harness.memory_rag.context_injector import ContextInjector
    return ContextInjector(always_inject=True)


# ===========================================================================
# Helpers para tests de LanceVectorStore
# ===========================================================================

_EMPTY_EMBEDDING = np.zeros(384, dtype=np.float32)


def _make_vec(dim: int = 384, seed: int = 0) -> np.ndarray:
    """Crea un vector unitario normalizado para tests."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


# ===========================================================================
# Fixtures — Modo memoria (fallback) para LanceVectorStore
# ===========================================================================


@pytest.fixture
def mem_store():
    """LanceVectorStore en modo fallback in-memory.

    _try_import_lancedb se parcha para retornar None, forzando el path
    de memoria.  Se usa allow_fallback=True para evitar ImportError.
    """
    with patch.object(
        LanceVectorStore, "_try_import_lancedb", return_value=None
    ):
        store = LanceVectorStore(db_path="/tmp/test_mem", allow_fallback=True)
        yield store


@pytest.fixture
def mem_store_no_defaults():
    """Idem mem_store pero sin las colecciones por defecto (limpio)."""
    with patch.object(
        LanceVectorStore, "_try_import_lancedb", return_value=None
    ):
        store = LanceVectorStore.__new__(LanceVectorStore)
        store._lancedb_available = False
        store._db = None
        store._mem_collections = {}
        store._embedding_dim = 384
        store._allow_fallback = True
        yield store


# ===========================================================================
# Fixtures — Modo LanceDB mockeado
# ===========================================================================


@pytest.fixture
def mock_lancedb():
    """Crea un ecosistema completo de mocks para LanceDB.

    Retorna un dict con:
      - lancedb_module: el módulo mockeado
      - db_conn: la conexión mockeada (lancedb.connect)
      - table: la tabla mockeada
      - table_list: resultado de list_tables()
    """
    table = MagicMock(name="table")
    table.count_rows.return_value = 0
    table.search.return_value.limit.return_value.to_list.return_value = []
    table.to_arrow.return_value.num_rows = 0

    table_list_mock = MagicMock(name="table_list")
    table_list_mock.tables = list(DEFAULT_COLLECTIONS.keys())

    db_conn = MagicMock(name="db_conn")
    db_conn.list_tables.return_value = table_list_mock
    db_conn.open_table.return_value = table
    db_conn.create_table.return_value = None

    lancedb_module = MagicMock(name="lancedb")
    lancedb_module.connect.return_value = db_conn

    return {
        "lancedb_module": lancedb_module,
        "db_conn": db_conn,
        "table": table,
        "table_list": table_list_mock,
    }


@pytest.fixture
def lancedb_store(mock_lancedb):
    """LanceVectorStore con LanceDB mockeado (conexión exitosa)."""
    patches = [
        patch.object(
            LanceVectorStore, "_try_import_lancedb",
            return_value=mock_lancedb["lancedb_module"],
        ),
        patch("harness.memory_rag.lance_vector_store.Path.mkdir"),
    ]
    with patches[0], patches[1]:
        store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        yield store


@pytest.fixture
def lancedb_store_with_data(mock_lancedb):
    """LanceVectorStore con datos pre-insertados en la tabla mockeada."""
    table = mock_lancedb["table"]
    table.count_rows.return_value = 3
    table.search.return_value.limit.return_value.to_list.return_value = [
        {
            "id": "r1",
            "vector": [0.1, 0.2],
            "metadata": json.dumps({"domain": "test", "score": 1}),
            "created_at": "2025-01-01T00:00:00",
            "_distance": 0.9,
        },
        {
            "id": "r2",
            "vector": [0.3, 0.4],
            "metadata": json.dumps({"domain": "test", "score": 2}),
            "created_at": "2025-01-02T00:00:00",
            "_distance": 0.8,
        },
    ]

    # to_arrow mock para stats
    arrow_mock = MagicMock(name="arrow_table")
    arrow_mock.num_rows = 2
    col_mock = MagicMock(name="created_at_col")
    col_mock.__getitem__.return_value.as_py.return_value = "2025-01-02T00:00:00"
    arrow_mock.column_names = ["id", "vector", "metadata", "created_at"]
    # slice devuelve una tabla con una fila
    slice_mock = MagicMock(name="slice")
    slice_mock.column.return_value = col_mock
    arrow_mock.slice.return_value = slice_mock
    table.to_arrow.return_value = arrow_mock

    patches = [
        patch.object(
            LanceVectorStore, "_try_import_lancedb",
            return_value=mock_lancedb["lancedb_module"],
        ),
        patch("harness.memory_rag.lance_vector_store.Path.mkdir"),
    ]
    with patches[0], patches[1]:
        store = LanceVectorStore(db_path="/fake/path", allow_fallback=False)
        yield store
