"""
Harness — Multi-agent orchestration engine with LanceDB memory.

Entry points:
    python -m harness           -> run.main()
    python harness/run.py       -> run.main()
    python harness/delegate.py  -> delegate.delegate_task()

INICIO RAPIDO: Este __init__.py usa lazy imports via __getattr__ (PEP 562).
Importar 'harness' NO carga submodulos pesados (numpy, LanceDB, etc.)
hasta que se accede explicitamente a un simbolo. Cold-start: ~10ms vs ~2800ms.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapeo nombre -> modulo para lazy loading
# ---------------------------------------------------------------------------
_SYMBOL_MAP: dict[str, str] = {
    "TaskManager": "harness.orchestrator.task_manager",
    "DelegationEngine": "harness.orchestrator.delegation_engine",
    "AgentBus": "harness.orchestrator.agent_bus",
    "SandboxLoop": "harness.orchestrator.sandbox_loop",
    "AgentDispatcher": "harness.orchestrator.agent_dispatcher",
    "Scheduler": "harness.orchestrator.scheduler",
    "DebateOrchestrator": "harness.orchestrator.debate_orchestrator",
    "LanceVectorStore": "harness.memory_rag.lance_vector_store",
    "ContextAssembler": "harness.memory_rag.context_assembler",
    "CASEEvaluator": "harness.evolve_loop.evaluator",
    "CognitionSync": "harness.evolve_loop.cognition_sync",
    "SelfImprover": "harness.evolve_loop.self_improver",
    "GEPAMutator": "harness.evolve_loop.gepa_mutator",
    "ProceduralMemory": "harness.evolve_loop.procedural_memory",
    "MCPExecutor": "harness.tools_sandbox.mcp_executor",
    "TaskScheduler": "harness.scheduler",
    "DocumentChunker": "harness.memory_rag.doc_ingester",
    "ingest_directory": "harness.memory_rag.doc_ingester",
    "run_main": "harness",  # local, no de submodulo
    # Workflow Patterns (nuevos)
    "evaluator_optimizer": "harness.orchestrator.workflow_patterns",
    "voting": "harness.orchestrator.workflow_patterns",
    "critique_revise": "harness.orchestrator.workflow_patterns",
    "parallel_transform": "harness.orchestrator.workflow_patterns",
    "PBTTemplate": "harness.orchestrator.pbt_templates",
    "TEMPLATES": "harness.orchestrator.pbt_templates",
    "BehavioralTracer": "harness.orchestrator.behavioral_tracer",
    "check_all": "harness.orchestrator.architectural_guardrails",
}


def __getattr__(name: str) -> Any:
    """Lazy import: solo carga el submodulo cuando se accede al simbolo.

    Args:
        name: Nombre del simbolo a importar.

    Returns:
        El objeto importado (clase, funcion o constante).

    Raises:
        AttributeError: Si el simbolo no esta en el mapa.
    """
    if name == "run_main":
        from harness.run import main
        return main

    module_path = _SYMBOL_MAP.get(name)
    if module_path is None:
        raise AttributeError(f"module 'harness' has no attribute '{name}'")

    module = importlib.import_module(module_path)
    attr = getattr(module, name, None)
    if attr is None:
        raise AttributeError(f"module '{module_path}' has no attribute '{name}'")

    # Cachear en el modulo para acceso futuro directo
    globals()[name] = attr
    return attr


def __dir__() -> list:
    """Soporte para tab completion."""
    return list(_SYMBOL_MAP.keys()) + list(globals().keys())


# Cache frio: simbolos que NO requieren import pesado y se usan siempre
# (actualmente vacio, pero se puede poblar con constantes/utiles ligeros)


__all__ = list(_SYMBOL_MAP.keys())
