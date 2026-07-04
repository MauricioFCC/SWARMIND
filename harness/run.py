"""
Harness — Multi-Agent Execution Engine (portable base)
Entry point for the agent orchestration system with LanceDB memory.

Usage:
    python harness/run.py "@rol: describe tu tarea"
    python harness/run.py --force-cloud "@software-engineer: crear API"
    python harness/run.py --auto-pilot "@data-architect: migrar DB"
    python harness/run.py --hitl-sensitive "@devops-sre: deploy"
    python harness/run.py -s "implementa una API REST"           -> detecta rol automaticamente

Features:
    - ModelRouter: Hybrid local/cloud model routing (Ollama + Cloud API)
    - HITLGuard: Human-in-the-Loop for destructive actions
    - MCP Client: Universal JSON-RPC tool execution
    - LanceDB memory with RAG context assembly
    - SandboxLoop for autonomous code execution

REFACTOR: Usa cli_common para funcionalidad compartida con delegate.py
(ANSI helpers, parse_message, load_vector_store, etc.).
Elimina HAS_GUARDRAILS bypass silencioso — ahora es error EXPLICITO.
"""
from __future__ import annotations

import sys
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict, Optional

# Importar funcionalidad compartida (DRY con delegate.py)
from harness.cli_common import (
    setup_logging, get_harness_root, get_project_root,
    parse_message, load_vector_store, check_first_run,
    _safe_print, _ok, _warn, _err, _bold, _cyan,
)

logger = setup_logging()

# Asegurar que la raíz del proyecto está en sys.path
sys.path.insert(0, str(get_project_root()))

HARNESS_ROOT = get_harness_root()

# ---------------------------------------------------------------------------
# Verificar LanceDB antes de cualquier otra operacion
# ---------------------------------------------------------------------------
try:
    import lancedb  # noqa: F401
except ImportError:
    logger.info("=" * 60)
    logger.info("  LanceDB REQUERIDO - No se encontro instalado.")
    logger.info("=" * 60)
    logger.info("")
    logger.info("    pip install lancedb")
    logger.info("    python harness/scripts/init.py")
    logger.info("")
    logger.info("  El sistema NO puede funcionar sin LanceDB.")
    logger.info("=" * 60)
    sys.exit(1)

from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.doc_ingester import DocumentChunker, ingest_directory
from harness.model_router.router import ModelRouter
from harness.orchestrator.hitl_guard import HITLGuard

# ---------------------------------------------------------------------------
# Guardrails - AHORA ES ERROR EXPLICITO si no está disponible
# Eliminado HAS_GUARDRAILS bypass silencioso (P7)
# ---------------------------------------------------------------------------
# Las guardrails de seguridad son OBLIGATORIAS. Si no están disponibles,
# el sistema falla con mensaje claro en lugar de operar sin protección.
try:
    from opencode.core.guardrails import run_full_pipeline
except ImportError:
    run_full_pipeline = None  # type: ignore[assignment]
    logger.warning(
        "GUARDRAILS NO DISPONIBLES: opencode.core.guardrails no importado.\n"
        "  El sistema operara SIN proteccion de guardrails.\n"
        "  Instala opencode.core o asegura que guardrails.py este accesible."
    )


# Import command handlers
from harness.run_commands import (
    _handle_db_migrate, _handle_db_list_imports, _handle_db_stats, _handle_db_rollback,
    _parse_iteration_flags, _handle_iteration_end, _handle_iteration_report,
    _handle_iteration_quick, _handle_iteration_auto,
    _handle_iteration_history, _handle_iteration_diff,
    _handle_hooks_install, _handle_hooks_uninstall, _handle_hooks_status,
    _handle_evolve_mutate, _handle_schedule_add, _handle_schedule_list,
    _handle_rag_ingest, _handle_rag_stats,
    _apply_model_routing, _check_hitl, _get_files_to_watch,
)
from harness.hermes_bridge import HermesBridge


def _show_usage() -> None:
    """Show usage information."""
    logger.info("Uso: python harness/run.py \"<descripcion de la tarea>\"")
    logger.info("Ej: python harness/run.py \"@software-engineer: Implementa endpoint de API\"")
    logger.info("")
    logger.info("Flags:")
    logger.info("  --daemon                    Inicia scheduler en background")
    logger.info("  --watch                     Modo watch (monitorea cambios)")
    logger.info("  --gateway <type>            Modo gateway (cli, slack, telegram)")
    logger.info("  --force-cloud               Override: todas las tareas a cloud API")
    logger.info("  --auto-pilot                Desactiva HITL (entornos de confianza)")
    logger.info("  --hitl-sensitive            HITL solo para acciones criticas")
    logger.info("  (dispatch paralelo por defecto, no requiere flags)")
    logger.info("  --help                      Muestra esta ayuda")
    logger.info("")
    logger.info("Roles universales (auto-deteccion SIN @):")
    logger.info("  @coordinator   - Entry point, analiza y delega (default)")
    logger.info("  @builder       - Implementacion: Rust, Go, Python, Web, Mobile, Trading, Infra")
    logger.info("  @scientist     - Investigacion: papers, AI/ML, arquitectura, patrones")
    logger.info("  @guardian      - Calidad: testing, seguridad, riesgo, docs, operaciones")
    logger.info("  @evolve        - Auto-mejora del sistema")
    logger.info("  !evolve mutate @<a> \"<t>\"   Evolucion de prompts")
    logger.info("  !schedule add <n> ...       Programar job")
    logger.info("  !schedule list              Listar jobs")
    logger.info("  !db migrate                 Migrar BD desde import/")
    logger.info("  !db migrate --path <ruta>   Migrar BD especifica")
    logger.info("  !db list-imports            Listar BDs disponibles")
    logger.info("  !db stats                   Estadisticas de BD activa")
    logger.info("  !db rollback <backup>       Restaurar desde backup")
    logger.info("  !iteration end              Pipeline fin de iteracion")
    logger.info("  !iteration end --dry-run    Simulacion del pipeline")
    logger.info("  !iteration end --skip-bugs  Salta bug hunting")
    logger.info("  !iteration end --skip-sec   Salta security review")
    logger.info("  !iteration end --skip-docs  Salta docs update")
    logger.info("  !iteration end --quick      Modo rapido (bugs+tokens, <2s)")
    logger.info("  !iteration end --auto       Modo automatico (full pipeline+commit)")
    logger.info("  !iteration quick            Modo rapido directo")
    logger.info("  !iteration auto             Modo automatico directo")
    logger.info("  !iteration report           Muestra ultimo reporte")
    logger.info("  !iteration history          Muestra timeline (ultimas 10)")
    logger.info("  !iteration history --all    Muestra todas las iteraciones")
    logger.info("  !iteration diff             Muestra detalle ultima iteracion")
    logger.info("  !iteration diff --last      Muestra detalle ultima iteracion")
    logger.info("  !iteration diff --n <num>   Muestra detalle iteracion #num")
    logger.info("  !hooks install              Instala pre-commit hook")
    logger.info("  !hooks uninstall            Desinstala pre-commit hook")
    logger.info("  !hooks status               Muestra estado del hook")
    logger.info("  !rag ingest                 Ingiere codigo fuente como RAG")
    logger.info("  !rag ingest --dir <path>    Ingiere solo un directorio")
    logger.info("  !rag stats                  Estadisticas de la BD RAG")
    logger.info("  !hermes sync                Sync bidireccional AGENTIC <-> Hermes_Memory_Proyects")
    logger.info("  !hermes stats               Estadisticas del puente Hermes")
    logger.info("")


def _parse_args() -> Dict[str, Any]:
    """Parse CLI arguments, extracting flags and the task string."""
    args = sys.argv[1:]
    parsed: Dict[str, Any] = {
        "help": False,
        "daemon": False,
        "watch": False,
        "gateway": None,
        "force_cloud": False,
        "auto_pilot": False,
        "hitl_sensitive": False,
        "task": None,
        "command": None,
    }


    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--help":
            parsed["help"] = True
            i += 1
        elif arg == "--daemon":
            parsed["daemon"] = True
            i += 1
        elif arg == "--watch":
            parsed["watch"] = True
            i += 1
        elif arg == "--gateway" and i + 1 < len(args):
            parsed["gateway"] = args[i + 1]
            i += 2
        elif arg == "--force-cloud":
            parsed["force_cloud"] = True
            i += 1
        elif arg == "--auto-pilot":
            parsed["auto_pilot"] = True
            i += 1
        elif arg == "--hitl-sensitive":
            parsed["hitl_sensitive"] = True
            i += 1
        elif arg.startswith("!"):
            parsed["command"] = arg
            i += 1
        else:
            parsed["task"] = arg
            i += 1

    return parsed


def _handle_watch_mode() -> None:
    """Handle --watch flag - monitors harness/ and .opencode/ for changes."""
    import time as _time
    from datetime import datetime as _datetime

    logger.info("[Harness] Watch mode activado - monitoreando:")
    logger.info("  - %s", HARNESS_ROOT)
    logger.info("  - %s", HARNESS_ROOT.parent / ".opencode")
    logger.info("  Excluyendo: harness/db/, __pycache__/, .git/")
    logger.info("")

    eoi_script = HARNESS_ROOT / "scripts" / "end_of_iteration.py"
    if not eoi_script.exists():
        logger.info("[Harness] %s No se encontro: %s", _err('[ERROR]'), eoi_script)
        return

    last_snapshot = _get_files_to_watch(HARNESS_ROOT)
    idle_since: Optional[float] = None
    debounce_seconds = 3.0

    _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
    _safe_print(f"  Press Ctrl+C to stop.")
    _safe_print()

    try:
        while True:
            _time.sleep(2)
            now = _time.time()

            new_snapshot = _get_files_to_watch(HARNESS_ROOT)
            changed_files = []

            for fpath, mtime in new_snapshot.items():
                old_mtime = last_snapshot.get(fpath)
                if old_mtime is None or mtime > old_mtime:
                    changed_files.append(fpath)

            for fpath in last_snapshot:
                if fpath not in new_snapshot:
                    changed_files.append(fpath)

            if not changed_files:
                idle_since = None
                continue

            if idle_since is None:
                idle_since = now
                continue

            if now - idle_since < debounce_seconds:
                continue

            timestamp = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for f in changed_files[:5]:
                rel = os.path.relpath(f, str(get_project_root()))
                _safe_print(f"  [{timestamp}] change detected: {rel}")
            if len(changed_files) > 5:
                _safe_print(f"  [{timestamp}] ... and {len(changed_files) - 5} more")

            _safe_print(f"  [{timestamp}] Running check...")
            try:
                import subprocess as _subprocess
                result = _subprocess.run(
                    [sys.executable, str(eoi_script), "--watch"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(get_project_root()),
                )
                for line in result.stdout.splitlines():
                    _safe_print(f"  {line}")
                if result.stderr.strip():
                    for line in result.stderr.splitlines():
                        _safe_print(f"  {_warn('[STDERR]')} {line}")
            except _subprocess.TimeoutExpired:
                _safe_print(f"  {_warn('[WARN]')} Pipeline timeout (>30s)")
            except Exception as exc:
                _safe_print(f"  {_err('[ERROR]')} Pipeline failed: {exc}")

            last_snapshot = new_snapshot.copy()
            idle_since = None
            _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
            logger.info("")

    except KeyboardInterrupt:
        _safe_print(f"\n  {_cyan('[WATCH]')} Watch mode detenido.")


# ---------------------------------------------------------------------------
# Hermes commands
# ---------------------------------------------------------------------------


def _handle_hermes(cmd: str) -> None:
    """Handle !hermes sync and !hermes stats."""
    sub = cmd[len("!hermes"):].strip()
    if sub == "sync":
        bridge = HermesBridge()
        result = bridge.sync_all()
        logger.info("[Hermes] Sync complete: %s", result)
    elif sub == "stats":
        bridge = HermesBridge()
        stats = bridge.get_stats()
        logger.info("[Hermes] Bridge stats: %s", stats)
    elif sub in ("", "help"):
        logger.info("[Hermes] Commands:")
        logger.info("  !hermes sync    - Bidirectional sync AGENTIC <-> Hermes_Memory_Proyects")
        logger.info("  !hermes stats   - Show bridge statistics")
    else:
        logger.info("[Hermes] Unknown subcommand: '%s'. Try '!hermes sync' or '!hermes stats'.", sub)


# ---------------------------------------------------------------------------
# Guardrails helper (P7: eliminado HAS_GUARDRAILS bypass silencioso)
# ---------------------------------------------------------------------------


def _run_guardrails(task: str, target_agent: str, ctx: Any, routing_source: str) -> None:
    """
    Ejecuta guardrails de seguridad.
    
    Si run_full_pipeline no está disponible, emite WARNING pero continúa
    (comportamiento degradado pero no bloqueante para desarrollo local).
    """
    if run_full_pipeline is None:
        logger.info("[Harness] Guardrails no disponible (opencode.core.guardrails no importado)")
        logger.info("[Harness] El sistema opera SIN proteccion de guardrails.")
        return

    pre_context = {
        "agent_role": target_agent,
        "task_description": task,
        "rag_chunks": len(ctx.relevant_docs) if hasattr(ctx, 'relevant_docs') else 0,
        "token_budget": ctx.metadata.get("total_tokens_used", 0) if hasattr(ctx, 'metadata') else 0,
        "routing_source": routing_source,
    }
    result = run_full_pipeline(task, "", pre_context)
    if not result.get("allowed", True):
        blocked_at = result.get("blocked_at", "unknown")
        summary = result.get("summary", {})
        logger.info("[Harness] Guardrails BLOCKED en fase %s: %s",
                     blocked_at, summary.get("failed_rules", []))
        sys.exit(1)
    logger.info("[Harness] Guardrails OK (%s/%s checks pasados)",
                 result['summary']['passed'], result['summary']['total_checks'])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the Harness."""
    parsed = _parse_args()

    # --- Handle --help immediately (before first-run check) ---
    if parsed.get("help"):
        _show_usage()
        return

    # --- First-run onboarding (before any command processing) ---
    check_first_run(HARNESS_ROOT)

    # --- Gateway mode ---
    if parsed["gateway"]:
        from harness.gateway.gateway import GatewayManager, Message, load_gateway_config

        config = load_gateway_config()
        if parsed["gateway"] not in config.get("active_gateways", []):
            config["active_gateways"] = [parsed["gateway"]]

        manager = GatewayManager(config)
        logger.info("[Harness] Gateway mode: %s", parsed['gateway'])
        logger.info("[Harness] Gateways activas: %s", manager.list_active_gateways())

        cli_gw = manager.get_gateway("cli")
        if cli_gw and cli_gw.is_active():
            logger.info("[Harness] CLI gateway activa. Escribe mensajes o 'exit' para salir.")
            try:
                while True:
                    line = input("> ").strip()
                    if line.lower() in ("exit", "quit", "q"):
                        break
                    if line:
                        msg = Message(role="user", content=line, channel="cli")
                        manager.send_all(msg)
            except (EOFError, KeyboardInterrupt):
                pass
        return

    # --- Daemon mode ---
    if parsed["daemon"]:
        from harness.orchestrator.scheduler import Scheduler
        import time

        logger.info("[Harness] Daemon mode - iniciando scheduler en background...")
        store = LanceVectorStore()
        scheduler = Scheduler(vector_store=store)
        scheduler.run_scheduler()
        logger.info("[Harness] Scheduler corriendo. Presiona Ctrl+C para detener.")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            scheduler.stop()
            logger.info("\n[Harness] Scheduler detenido.")
        return

    # --- Watch mode ---
    if parsed["watch"]:
        _handle_watch_mode()
        return

    # --- Command mode ---
    cmd = parsed.get("command")
    if cmd:
        store = LanceVectorStore()
        if cmd.startswith("!evolve mutate"):
            _handle_evolve_mutate(store, cmd)
        elif cmd.startswith("!schedule add"):
            _handle_schedule_add(store, cmd)
        elif cmd.startswith("!schedule list"):
            _handle_schedule_list(store)
        elif cmd.startswith("!db migrate"):
            _handle_db_migrate(store, cmd)
        elif cmd.startswith("!db list-imports"):
            _handle_db_list_imports()
        elif cmd.startswith("!db stats"):
            _handle_db_stats(store)
        elif cmd.startswith("!db rollback"):
            _handle_db_rollback(cmd)
        elif cmd.startswith("!iteration end"):
            _handle_iteration_end(cmd, HARNESS_ROOT)
        elif cmd.startswith("!iteration quick"):
            _handle_iteration_quick(cmd, HARNESS_ROOT)
        elif cmd.startswith("!iteration auto"):
            _handle_iteration_auto(cmd, HARNESS_ROOT)
        elif cmd.startswith("!iteration history"):
            _handle_iteration_history(cmd)
        elif cmd.startswith("!iteration diff"):
            _handle_iteration_diff(cmd)
        elif cmd.startswith("!iteration report"):
            _handle_iteration_report()
        elif cmd.startswith("!hooks install"):
            _handle_hooks_install()
        elif cmd.startswith("!hooks uninstall"):
            _handle_hooks_uninstall()
        elif cmd.startswith("!hooks status"):
            _handle_hooks_status()
        elif cmd.startswith("!rag ingest"):
            _handle_rag_ingest(store, cmd)
        elif cmd.startswith("!rag stats"):
            _handle_rag_stats(store)
        elif cmd.startswith("!agent evolve"):
            from harness.evolve_loop.agent_builder import run_agent_evolution
            dry_run = "--dry-run" in cmd
            result = run_agent_evolution(dry_run=dry_run)
            logger.info("[AgentEvolve] Built: %s | Pruned: %s | Stats: %s",
                         result["built"], result["pruned"], result["builder_stats"])
        elif cmd.startswith("!agent build"):
            from harness.evolve_loop.agent_builder import AgentBuilder
            builder = AgentBuilder()
            built = builder.build_agents_from_cognition()
            logger.info("[AgentBuild] Created: %s", built)
        elif cmd.startswith("!agent prune"):
            from harness.evolve_loop.agent_builder import AgentPruner
            dry_run = "--dry-run" in cmd
            pruner = AgentPruner()
            pruned = pruner.prune_underperforming(dry_run=dry_run)
            logger.info("[AgentPrune] Removed: %s", pruned)
        elif cmd.startswith("!hermes"):
            _handle_hermes(cmd)
        else:
            logger.info("[Harness] Comando desconocido: %s", cmd)
        return

    # --- Plan-and-Execute Orchestrator (reemplaza auto-detección simple) ---
    task = parsed.get("task")
    if not task:
        _show_usage()
        sys.exit(1)

    logger.info("[Harness] Inicializando...")

    store = LanceVectorStore()
    if not os.path.exists(os.path.join(HARNESS_ROOT, "db", "lancedb")):
        logger.warning("harness/db/lancedb/ no existe. Los datos se perderan al reiniciar.")

    # --- NEW: TaskOrchestrator (Plan-and-Execute) ---
    # Descompone la peticion en un DAG de subtareas, preserva contexto,
    # paraleliza niveles independientes, secuencializa los dependientes.
    from harness.orchestrator.task_orchestrator import TaskOrchestrator

    orchestrator = TaskOrchestrator(vector_store=store)
    orch_result = orchestrator.process_message(
        message=task,
        force_agent=None,  # se auto-detecta
    )

    # --- Mostrar plan al usuario ---
    if orch_result.is_new_plan:
        _safe_print()
        _safe_print(f"  {_cyan('📋 PLAN DE EJECUCIÓN')}")
        _safe_print(f"  {'─' * 50}")
        _safe_print(f"  Sesión: {orch_result.session_id}")
        _safe_print(f"  Tarea: {task[:100]}")
        _safe_print()

        for level_idx, level in enumerate(orch_result.plan.get_levels()):
            is_parallel = len(level) > 1
            mode = "⚡ PARALELO" if is_parallel else "→ SECUENCIAL"
            _safe_print(f"  Nivel {level_idx} ({mode}):")
            for s in level:
                deps = f" [espera: {', '.join(s.dependencies)}]" if s.dependencies else ""
                _safe_print(f"    ▸ [{s.agent}] {s.description}{deps}")
            _safe_print()
        _safe_print(f"  {'─' * 50}")
        _safe_print()

    # Si hay un nivel actual listo, mostrar qué se ejecuta ahora
    if orch_result.current_level:
        if len(orch_result.current_level) == 1:
            st = orch_result.current_level[0]
            _safe_print(
                f"  {_cyan(f'▶ Ejecutando:')} [{st['agent']}] {st['description']}"
            )
        else:
            agents = {st['agent'] for st in orch_result.current_level}
            _safe_print(
                f"  {_cyan(f'▶ Ejecutando {len(orch_result.current_level)} subtareas en PARALELO:')}"
            )
            for st in orch_result.current_level:
                _safe_print(f"    ▸ [{st['agent']}] {st['description']}")
        _safe_print()

    # Si hay resultados previos, mostrarlos
    if orch_result.previous_results:
        _safe_print(f"  {_cyan('✅ Subtareas completadas:')}")
        for prev in orch_result.previous_results:
            _safe_print(f"    ✓ [{prev['agent']}] {prev['description']}")
        _safe_print()

    # --- Preparar contexto de dispatch con el plan ---
    target_agent = orch_result.target_agent
    logger.info("[Harness] Ruteando a @%s (sesión %s)",
                target_agent, orch_result.session_id)

    # Plan context para inyectar en el dispatch
    plan_context = {
        "session_id": orch_result.session_id,
        "plan_summary": orch_result.session_status,
        "current_level": orch_result.current_level,
        "previous_results": orch_result.previous_results,
        "communication_log": orch_result.communication_log,
        "is_complete": orch_result.is_complete,
    }

    # Dispatch PARALELO con plan context
    import asyncio
    from harness.orchestrator.agent_dispatcher import AgentDispatcher
    dispatcher = AgentDispatcher(vector_store=store)

    async def run_async():
        result = await dispatcher.dispatch_async(
            target_agent, task,
            plan_context=plan_context,
        )
        logger.info("[Harness] Dispatch paralelo: skill=%s, chunks=%d, plan=%s",
                     result["used_skill"],
                     len(result.get("rag_context", {}).get("relevant_docs", [])),
                     bool(result.get("execution_plan")),
        )

    asyncio.run(run_async())

    # ModelRouter: determinar local vs cloud
    force_cloud = parsed.get("force_cloud", False)
    routing_source = _apply_model_routing(task, target_agent, force_cloud)

    # HITL Guard: inicializar
    hitl_mode = "hitl"
    if parsed.get("auto_pilot"):
        hitl_mode = "auto_pilot"
    elif parsed.get("hitl_sensitive"):
        hitl_mode = "hitl_sensitive"

    guard = HITLGuard(vector_store=store, mode=hitl_mode)
    if hitl_mode != "hitl":
        logger.info("[HITL] Modo: %s", hitl_mode)

    # HITL: check task for destructive actions
    if not _check_hitl(task, target_agent, guard):
        logger.info("[HITL] Accion rechazada por el usuario. Cancelando.")
        sys.exit(1)

    # Contexto RAG
    assembler = ContextAssembler(store)
    ctx = assembler.assemble(task, target_agent)
    if ctx.relevant_docs:
        logger.info("[Harness] Contexto RAG: %d chunks, %d tokens",
                     len(ctx.relevant_docs), ctx.metadata.get("total_tokens_used", 0))
    else:
        logger.info("[Harness] Contexto RAG: sin chunks, auto-ingestando documentos...")
        chunker = DocumentChunker(chunk_size=25, overlap=3)
        stats = ingest_directory(store, ["docs", "harness", ".opencode"], chunker)
        logger.info("[Harness] Ingest: %d archivos, %d chunks",
                     stats['files_processed'], stats['chunks_inserted'])
        if stats['chunks_inserted'] > 0:
            ctx = assembler.assemble(task, target_agent)
            if ctx.relevant_docs:
                logger.info("[Harness] Contexto RAG tras ingest: %d chunks", len(ctx.relevant_docs))

    # Guardrails pre-check
    _run_guardrails(task, target_agent, ctx, routing_source)

    tm = TaskManager(vector_store=store)
    new_task = tm.create_task(
        title=task[:80],
        description=task,
        agent_assigned=target_agent,
        priority=5
    )
    if new_task:
        task_id = getattr(new_task, 'id', 'N/A')
        task_status = getattr(new_task, 'status', 'pending')
        logger.info("[Harness] Tarea creada: %s (estado: %s)", task_id, task_status)

    # Registrar leccion en cognition store
    cognition = CognitionSync(store)
    try:
        lesson = cognition.add_lesson(
            title=f"Tarea: {task[:60]}",
            content=(
                f"Tarea enrutada a @{target_agent}.\n"
                f"Descripcion: {task}\n"
                f"Routing: {routing_source}\n"
                f"Sesión: {orch_result.session_id}\n"
                f"Subtasks en plan: {len(orch_result.plan.subtasks)}\n"
                f"Chunks RAG recuperados: {len(ctx.relevant_docs)}\n"
                f"Tokens de contexto: {ctx.metadata.get('total_tokens_used', 0)}"
            ),
            domain="harness.routing",
            tags=["routing", target_agent, routing_source, "harness", "plan-and-execute"],
            metrics={
                "rag_chunks": len(ctx.relevant_docs),
                "token_estimate": ctx.metadata.get("total_tokens_used", 0),
                "routing_source": routing_source,
                "plan_subtasks": len(orch_result.plan.subtasks),
                "session_id": orch_result.session_id,
            },
        )
        logger.info("[Harness] Leccion registrada en cognition: %s", lesson.id)
    except Exception as exc:
        logger.info("[Harness] Cognition store no disponible: %s", exc)

    # --- Output final ---
    if orch_result.is_complete:
        _safe_print(f"\n  {_ok('🎉 ¡PLAN COMPLETO!')} Todas las subtareas han sido ejecutadas.")
        _safe_print(f"  El plan '{orch_result.session_id}' ha finalizado.")
    else:
        pending = len(orch_result.plan.subtasks) - sum(
            1 for s in orch_result.plan.subtasks if s.completed
        )
        if pending > 0:
            _safe_print(f"\n  {_warn(f'⏳ Quedan {pending} subtareas pendientes.')}")
            _safe_print(f"  Para continuar, escribe 'continuar' o el siguiente paso.")
        else:
            _safe_print(f"\n  {_cyan('ℹ️  Usa este plan como guía para la implementación.')}")

    if orch_result.current_level:
        for st in orch_result.current_level:
            _safe_print(f"  ▶ [{st['agent']}] {st['description']}")

    logger.info("[Harness] Tarea enrutada a @%s (%s) — sesión %s",
                target_agent, routing_source, orch_result.session_id)

    # --- SandboxLoop (solo si es implementación y hay tarea) ---
    if target_agent in ("builder", "software-engineer") and new_task:
        from harness.orchestrator.sandbox_loop import SandboxLoop
        from harness.orchestrator.agent_bus import AgentBus

        task_id = getattr(new_task, 'id', 'N/A')
        logger.info("\n[Harness] [Sandbox] Iniciando SandboxLoop para task_id=%s", task_id)

        sandbox = SandboxLoop(vector_store=store)
        channel = "#swe-sandbox"

        bus = AgentBus(vector_store=store)
        bus.post_message(
            channel=channel,
            from_agent="@harness",
            to_agent=f"@{target_agent}",
            message=(
                f"Tarea creada: **{task[:80]}**\n"
                f"Task ID: `{task_id}`\n"
                f"Sesión: `{orch_result.session_id}`\n"
                f"Routing: `{routing_source}`\n\n"
                f"Plan de ejecución con {len(orch_result.plan.subtasks)} subtareas.\n"
                f"Nivel actual: {len(orch_result.current_level)} subtarea(s) lista(s).\n\n"
                f"El SandboxLoop esta listo para ejecutar el bucle autonomo.\n"
            ),
            message_type="notification",
            task_id=task_id,
        )
        logger.info("[Harness] SandboxLoop listo en canal %s", channel)


if __name__ == "__main__":
    main()
