"""
Harness — Onyx Multi-Agent Execution Engine
Entry point for the agent orchestration system with LanceDB memory.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.lance_vector_store import LanceVectorStore


def main():
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if not task:
        print("Uso: python harness/run.py \"<descripción de la tarea>\"")
        print("Ej: python harness/run.py \"@software-engineer: Implementa endpoint de facturación\"")
        sys.exit(1)

    print(f"⚡ Inicializando Harness...")
    
    store = LanceVectorStore()
    tm = TaskManager()
    engine = DelegationEngine()
    assembler = ContextAssembler(store)
    
    result = engine.route_message(task)
    target_agent = result.get("agent", "project-manager")
    
    print(f"  → Ruteando a @{target_agent}")
    
    context = assembler.assemble(task, target_agent)
    if context.get("relevant_chunks"):
        print(f"  → Contexto ensamblado: {len(context['relevant_chunks'])} chunks, {context.get('token_estimate', 0)} tokens")
    
    new_task = tm.create_task(
        title=task[:80],
        description=task,
        agent_assigned=target_agent,
        priority=5
    )
    if new_task:
        print(f"  → Tarea creada: {new_task.get('id', 'N/A')} (estado: {new_task.get('status', 'pending')})")

    print(f"\n✅ Tarea enrutada a @{target_agent}")
    print(f"📋 Para ejecutar: invoca @{target_agent} con el contexto ensamblado")


if __name__ == "__main__":
    main()
