"""
Harness — Multi-Agent Execution Engine (portable base)
Entry point for the agent orchestration system with LanceDB memory.
Usage: python harness/run.py "@rol: describe tu tarea"
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
        print("Uso: python harness/run.py \"<descripcion de la tarea>\"")
        print("Ej: python harness/run.py \"@software-engineer: Implementa endpoint de facturacion\"")
        sys.exit(1)

    print("[Harness] Inicializando...")

    store = LanceVectorStore()
    tm = TaskManager()
    engine = DelegationEngine()
    assembler = ContextAssembler(store)

    target_agent = engine.route_message(task)

    print(f"[Harness] Ruteando a @{target_agent}")

    ctx = assembler.assemble(task, target_agent)
    if ctx.relevant_docs:
        print(f"[Harness] Contexto: {len(ctx.relevant_docs)} chunks, {ctx.metadata.get('total_tokens_used', 0)} tokens")

    new_task = tm.create_task(
        title=task[:80],
        description=task,
        agent_assigned=target_agent,
        priority=5
    )
    if new_task:
        task_id = getattr(new_task, 'id', 'N/A')
        task_status = getattr(new_task, 'status', 'pending')
        print(f"[Harness] Tarea creada: {task_id} (estado: {task_status})")

    print(f"[Harness] Tarea enrutada a @{target_agent}")
    print(f"[Harness] Para ejecutar: invoca @{target_agent} con el contexto ensamblado")


if __name__ == "__main__":
    main()
