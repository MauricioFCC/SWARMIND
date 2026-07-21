"""Fixtures compartidas para todos los tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
def hermes_bridge(vector_store):
    """HermesBridge."""
    from harness.hermes_bridge import HermesBridge
    return HermesBridge(vector_store=vector_store)


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
