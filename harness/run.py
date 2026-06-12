"""
Harness — Multi-Agent Execution Engine (portable base)
Entry point for the agent orchestration system with LanceDB memory.
Usage: python harness/run.py "@rol: describe tu tarea"

Flujo completo:
  1. Inicializa LanceDB + TaskManager + DelegationEngine + ContextAssembler + CognitionSync
  2. Rutea el mensaje al agente target via @rol o intent matching
  3. Ensambla contexto RAG desde rag_chunks (con filtro por dominio si aplica)
  4. Ejecuta guardrails pre-check sobre el contexto
  5. Crea tarea en tasks_board (LanceDB con fallback SQLite)
  6. Si guardrails pre OK, registra leccion en asi_cognition_store
  7. Muestra ruteo final para que opencode invoque al agente
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.doc_ingester import DocumentChunker, ingest_directory

try:
    from opencode.core.guardrails import run_full_pipeline
    HAS_GUARDRAILS = True
except ImportError:
    HAS_GUARDRAILS = False


def main():
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if not task:
        print("Uso: python harness/run.py \"<descripcion de la tarea>\"")
        print("Ej: python harness/run.py \"@software-engineer: Implementa endpoint de facturacion\"")
        sys.exit(1)

    print("[Harness] Inicializando...")

    store = LanceVectorStore()
    tm = TaskManager(vector_store=store)
    engine = DelegationEngine()
    assembler = ContextAssembler(store)
    cognition = CognitionSync(store)

    target_agent = engine.route_message(task)
    print(f"[Harness] Ruteando a @{target_agent}")

    ctx = assembler.assemble(task, target_agent)
    if ctx.relevant_docs:
        print(f"[Harness] Contexto RAG: {len(ctx.relevant_docs)} chunks, {ctx.metadata.get('total_tokens_used', 0)} tokens")
    else:
        print("[Harness] Contexto RAG: sin chunks, auto-ingestando documentos...")
        chunker = DocumentChunker(chunk_size=25, overlap=3)
        stats = ingest_directory(store, ["docs", "harness", ".opencode"], chunker)
        print(f"[Harness] Ingest: {stats['files_processed']} archivos, {stats['chunks_inserted']} chunks")
        if stats['chunks_inserted'] > 0:
            ctx = assembler.assemble(task, target_agent)
            if ctx.relevant_docs:
                print(f"[Harness] Contexto RAG tras ingest: {len(ctx.relevant_docs)} chunks")

    # Guardrails pre-check
    if HAS_GUARDRAILS:
        pre_context = {
            "agent_role": target_agent,
            "task_description": task,
            "rag_chunks": len(ctx.relevant_docs),
            "token_budget": ctx.metadata.get("total_tokens_used", 0),
        }
        result = run_full_pipeline(task, "", pre_context)
        if not result.get("allowed", True):
            blocked_at = result.get("blocked_at", "unknown")
            summary = result.get("summary", {})
            print(f"[Harness] Guardrails BLOCKED en fase {blocked_at}: {summary.get('failed_rules', [])}")
            sys.exit(1)
        print(f"[Harness] Guardrails OK ({result['summary']['passed']}/{result['summary']['total_checks']} checks pasados)")
    else:
        print("[Harness] Guardrails no disponible (opencode.core.guardrails no importado)")

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

    # Registrar leccion en cognition store
    try:
        lesson = cognition.add_lesson(
            title=f"Tarea: {task[:60]}",
            content=(
                f"Tarea enrutada a @{target_agent}.\n"
                f"Descripcion: {task}\n"
                f"Chunks RAG recuperados: {len(ctx.relevant_docs)}\n"
                f"Tokens de contexto: {ctx.metadata.get('total_tokens_used', 0)}"
            ),
            domain="harness.routing",
            tags=["routing", target_agent, "harness"],
            metrics={
                "rag_chunks": len(ctx.relevant_docs),
                "token_estimate": ctx.metadata.get("total_tokens_used", 0),
            },
        )
        print(f"[Harness] Leccion registrada en cognition: {lesson.id}")
    except Exception as exc:
        print(f"[Harness] Cognition store no disponible: {exc}")

    print(f"[Harness] Tarea enrutada a @{target_agent}")
    print(f"[Harness] Para ejecutar: invoca @{target_agent} con el contexto ensamblado")

    # ------------------------------------------------------------------
    # Si el target_agent es @software-engineer, iniciar SandboxLoop
    # ------------------------------------------------------------------
    if target_agent == "software-engineer" and new_task:
        from harness.orchestrator.sandbox_loop import SandboxLoop
        from harness.orchestrator.agent_bus import AgentBus

        task_id = getattr(new_task, 'id', 'N/A')
        print(f"\n[Harness] [Sandbox] Iniciando SandboxLoop para task_id={task_id}")

        sandbox = SandboxLoop(vector_store=store)
        channel = "#swe-sandbox"

        # Mensaje de bienvenida en el canal del sandbox
        bus = AgentBus(vector_store=store)
        bus.post_message(
            channel=channel,
            from_agent="@harness",
            to_agent="@software-engineer",
            message=(
                f"🔄 Tarea creada: **{task[:80]}**\n"
                f"Task ID: `{task_id}`\n\n"
                f"El SandboxLoop esta listo para ejecutar el bucle autonomo.\n"
                f"Cuando el codigo este listo, ejecuta:\n"
                f"```\n"
                f"python -c \"from harness.orchestrator.sandbox_loop import SandboxLoop; "
                f"loop = SandboxLoop(); "
                f"loop.run_autonomous('{task_id}', code='<tu-codigo>', test_command='pytest')\"\n"
                f"```"
            ),
            message_type="notification",
            task_id=task_id,
        )
        print(f"[Harness] SandboxLoop listo en canal {channel}")
        print(f"[Harness] Para activar el bucle autonomo con codigo:")
        print(f"[Harness]   SandboxLoop().run_autonomous('{task_id}', code='...', test_command='pytest')")


if __name__ == "__main__":
    main()
