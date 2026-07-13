"""
Harness — Multi-agent orchestration engine with LanceDB memory.

Entry points:
    python -m harness           -> run.main()
    python harness/run.py       -> run.main()
    python harness/delegate.py  -> delegate.delegate_task()

IMPORTANTE: Este __init__.py NO importa run.py ni delegate.py a nivel de módulo
para evitar que el check de LanceDB se ejecute al importar el paquete.
Usa lazy imports en los getters.
"""

from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.orchestrator.agent_bus import AgentBus
from harness.orchestrator.sandbox_loop import SandboxLoop
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.memory_rag.context_assembler import ContextAssembler
from harness.evolve_loop.evaluator import CASEEvaluator
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.evolve_loop.self_improver import SelfImprover
from harness.evolve_loop.gepa_mutator import GEPAMutator
from harness.evolve_loop.procedural_memory import ProceduralMemory
from harness.tools_sandbox.mcp_executor import MCPExecutor
from harness.scheduler import TaskScheduler
from harness.memory_rag.doc_ingester import DocumentChunker, ingest_directory


def run_main() -> None:
    """Ejecuta el entry point principal (lazy import de run.py)."""
    from harness.run import main
    main()


__all__ = [
    "run_main",
    "TaskManager",
    "DelegationEngine",
    "AgentBus",
    "SandboxLoop",
    "LanceVectorStore",
    "ContextAssembler",
    "CASEEvaluator",
    "CognitionSync",
    "SelfImprover",
    "GEPAMutator",
    "ProceduralMemory",
    "MCPExecutor",
    "TaskScheduler",
    "DocumentChunker",
    "ingest_directory",
]
