"""Fixtures compartidas para todos los tests."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))


@pytest.fixture
def vector_store():
    """LanceVectorStore con base de datos aislada (temp dir) y fallback in-memory."""
    from harness.memory_rag.lance_vector_store import LanceVectorStore
    tmpdir = tempfile.mkdtemp(prefix="agentic_test_")
    return LanceVectorStore(db_path=tmpdir, allow_fallback=True)


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
def semantic_cache():
    """SemanticCache."""
    from harness.memory_rag.semantic_cache import SemanticCache
    return SemanticCache()


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
