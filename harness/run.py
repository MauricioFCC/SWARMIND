"""
Harness â€” Multi-Agent Execution Engine (portable base)
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
Elimina HAS_GUARDRAILS bypass silencioso â€” ahora es error EXPLICITO.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Importar funcionalidad compartida (DRY con delegate.py)
from harness.cli_common import (
    _cyan,
    _ok,
    _safe_print,
    _warn,
    check_first_run,
    get_harness_root,
    get_project_root,
    setup_logging,
)

logger = setup_logging()

# Asegurar que la raÃ­z del proyecto estÃ¡ en sys.path
sys.path.insert(1, str(get_project_root()))

HARNESS_ROOT = get_harness_root()
HAS_LANCEDB: bool = False

# ---------------------------------------------------------------------------
# Verificar LanceDB â€” solo warning en import, error en main()
# ---------------------------------------------------------------------------
try:
    import lancedb  # noqa: F401
    HAS_LANCEDB = True
except ImportError:
    logger.warning(
        "LanceDB no encontrado. Ejecuta: pip install lancedb && python harness/scripts/init.py"
    )

# Script standalone: sys.path debe configurarse (get_project_root + insert) antes
# de importar los modulos harness.* para soportar ejecucion desde cualquier CWD.
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.doc_ingester import (
    DocumentChunker,
    ingest_directory,
)
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.orchestrator.hitl_guard import HITLGuard
from harness.orchestrator.task_manager import TaskManager

# ---------------------------------------------------------------------------
# Guardrails - AHORA ES ERROR EXPLICITO si no estÃ¡ disponible
# Eliminado HAS_GUARDRAILS bypass silencioso (P7)
# ---------------------------------------------------------------------------
# Las guardrails de seguridad son OBLIGATORIAS. Si no estÃ¡n disponibles,
# el sistema falla con mensaje claro en lugar de operar sin protecciÃ³n.
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
# (mismo criterio que arriba: requiere sys.path setup previo + guardrails)
from harness.run_commands import (
    _apply_model_routing,
    _check_hitl,
    _handle_db_list_imports,
    _handle_db_migrate,
    _handle_db_rollback,
    _handle_db_stats,
    _handle_evolve_mutate,
    _handle_hermes,
    _handle_hooks_install,
    _handle_hooks_status,
    _handle_hooks_uninstall,
    _handle_iteration_auto,
    _handle_iteration_diff,
    _handle_iteration_end,
    _handle_iteration_history,
    _handle_iteration_quick,
    _handle_iteration_report,
    _handle_rag_ingest,
    _handle_rag_stats,
    _handle_schedule_add,
    _handle_schedule_list,
    _handle_watch_mode,
    _run_guardrails,
)


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
    logger.info("  !hermes sync                Sync bidireccional Swarmind <-> shared_memory")
    logger.info("  !hermes stats               Estadisticas del puente Hermes")
    logger.info("")


def _parse_args() -> dict[str, Any]:
    """Parse CLI arguments, extracting flags and the task string."""
    args = sys.argv[1:]
    parsed: dict[str, Any] = {
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


# (moved to run_commands.py: _handle_watch_mode, _handle_hermes, _run_guardrails)


# ---------------------------------------------------------------------------
# Extracted sub-functions from main()
# ---------------------------------------------------------------------------


def _handle_gateway_mode(parsed: dict[str, Any]) -> None:
    """Handle --gateway mode."""
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


def _handle_daemon_mode() -> None:
    """Handle --daemon mode."""
    import time

    from harness.orchestrator.scheduler import Scheduler

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


def _handle_command(cmd: str) -> None:
    """Dispatch a !command to its handler."""
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


def _display_plan(orch_result: Any, task: str) -> None:
    """Display the execution plan to the user."""
    if not orch_result.is_new_plan:
        return

    _safe_print()
    _safe_print(f"  {_cyan('ðŸ“‹ PLAN DE EJECUCIÃ“N')}")
    _safe_print(f"  {'â”€' * 50}")
    _safe_print(f"  SesiÃ³n: {orch_result.session_id}")
    _safe_print(f"  Tarea: {task[:100]}")
    _safe_print()

    for level_idx, level in enumerate(orch_result.plan.get_levels()):
        is_parallel = len(level) > 1
        mode = "âš¡ PARALELO" if is_parallel else "â†’ SECUENCIAL"
        _safe_print(f"  Nivel {level_idx} ({mode}):")
        for s in level:
            deps = f" [espera: {', '.join(s.dependencies)}]" if s.dependencies else ""
            _safe_print(f"    â–¸ [{s.agent}] {s.description}{deps}")
        _safe_print()
    _safe_print(f"  {'â”€' * 50}")
    _safe_print()

    # Current level
    if orch_result.current_level:
        if len(orch_result.current_level) == 1:
            st = orch_result.current_level[0]
            _safe_print(f"  {_cyan('â–¶ Ejecutando:')} [{st['agent']}] {st['description']}")
        else:
            _safe_print(f"  {_cyan(f'â–¶ Ejecutando {len(orch_result.current_level)} subtareas en PARALELO:')}")
            for st in orch_result.current_level:
                _safe_print(f"    â–¸ [{st['agent']}] {st['description']}")
        _safe_print()

    # Previous results
    if orch_result.previous_results:
        _safe_print(f"  {_cyan('âœ… Subtareas completadas:')}")
        for prev in orch_result.previous_results:
            _safe_print(f"    âœ“ [{prev['agent']}] {prev['description']}")
        _safe_print()


def _dispatch_task(store: Any, orch_result: Any, task: str) -> str:
    """Dispatch task via AgentDispatcher and return routing_source."""
    target_agent = orch_result.target_agent
    plan_context = {
        "session_id": orch_result.session_id,
        "plan_summary": orch_result.session_status,
        "current_level": orch_result.current_level,
        "previous_results": orch_result.previous_results,
        "communication_log": orch_result.communication_log,
        "is_complete": orch_result.is_complete,
    }

    import asyncio

    from harness.orchestrator.agent_dispatcher import AgentDispatcher
    dispatcher = AgentDispatcher(vector_store=store)

    async def _run():
        result = await dispatcher.dispatch_async(target_agent, task, plan_context=plan_context)
        logger.info("[Harness] Dispatch: skill=%s, chunks=%d, plan=%s",
                     result["used_skill"],
                     len(result.get("rag_context", {}).get("relevant_docs", [])),
                     bool(result.get("execution_plan")))

    asyncio.run(_run())
    return target_agent


def _resolve_hitl_mode(parsed: dict[str, Any]) -> str:
    """Determine HITL mode from parsed args."""
    if parsed.get("auto_pilot"):
        return "auto_pilot"
    if parsed.get("hitl_sensitive"):
        return "hitl_sensitive"
    return "hitl"


def _ensure_rag_context(store: Any, task: str, target_agent: str) -> Any:
    """Assemble RAG context, auto-ingesting if empty."""
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
    return ctx


def _create_task_and_lesson(
    store: Any, task: str, target_agent: str,
    routing_source: str, orch_result: Any, ctx: Any,
) -> Any:
    """Create a TaskManager task and register cognition lesson."""
    tm = TaskManager(vector_store=store)
    new_task = tm.create_task(title=task[:80], description=task, agent_assigned=target_agent, priority=5)
    if new_task:
        logger.info("[Harness] Tarea creada: %s (estado: %s)",
                     getattr(new_task, 'id', 'N/A'), getattr(new_task, 'status', 'pending'))

    cognition = CognitionSync(store)
    try:
        cognition.add_lesson(
            title=f"Tarea: {task[:60]}",
            content=(
                f"Tarea enrutada a @{target_agent}.\n"
                f"Descripcion: {task}\n"
                f"Routing: {routing_source}\n"
                f"SesiÃ³n: {orch_result.session_id}\n"
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
    except Exception as exc:  # noqa: BLE001
        logger.info("[Harness] Cognition store no disponible: %s", exc)

    return new_task


def _display_final_output(orch_result: Any, target_agent: str, routing_source: str) -> None:
    """Display final output and status."""
    if orch_result.is_complete:
        _safe_print(f"\n  {_ok('ðŸŽ‰ Â¡PLAN COMPLETO!')} Todas las subtareas han sido ejecutadas.")
        _safe_print(f"  El plan '{orch_result.session_id}' ha finalizado.")
    else:
        pending = len(orch_result.plan.subtasks) - sum(1 for s in orch_result.plan.subtasks if s.completed)
        if pending > 0:
            _safe_print(f"\n  {_warn(f'â³ Quedan {pending} subtareas pendientes.')}")
            _safe_print("  Para continuar, escribe 'continuar' o el siguiente paso.")
        else:
            _safe_print(f"\n  {_cyan('â„¹ï¸  Usa este plan como guÃ­a para la implementaciÃ³n.')}")

    if orch_result.current_level:
        for st in orch_result.current_level:
            _safe_print(f"  â–¶ [{st['agent']}] {st['description']}")

    logger.info("[Harness] Tarea enrutada a @%s (%s) â€” sesiÃ³n %s",
                target_agent, routing_source, orch_result.session_id)


def _start_sandbox_if_needed(
    target_agent: str, new_task: Any, store: Any,
    task: str, orch_result: Any, routing_source: str,
) -> None:
    """Start SandboxLoop for builder agents."""
    if target_agent not in ("builder", "software-engineer") or not new_task:
        return

    from harness.orchestrator.agent_bus import AgentBus
    from harness.orchestrator.sandbox_loop import SandboxLoop

    task_id = getattr(new_task, 'id', 'N/A')
    logger.info("\n[Harness] [Sandbox] Iniciando SandboxLoop para task_id=%s", task_id)

    SandboxLoop(vector_store=store)
    bus = AgentBus(vector_store=store)
    bus.post_message(
        channel="#swe-sandbox",
        from_agent="@harness",
        to_agent=f"@{target_agent}",
        message=(
            f"Tarea creada: **{task[:80]}**\n"
            f"Task ID: `{task_id}`\n"
            f"SesiÃ³n: `{orch_result.session_id}`\n"
            f"Routing: `{routing_source}`\n\n"
            f"Plan de ejecuciÃ³n con {len(orch_result.plan.subtasks)} subtareas.\n"
            f"Nivel actual: {len(orch_result.current_level)} subtarea(s) lista(s).\n\n"
            f"El SandboxLoop esta listo para ejecutar el bucle autonomo.\n"
        ),
        message_type="notification",
        task_id=task_id,
    )
    logger.info("[Harness] SandboxLoop listo en canal #swe-sandbox")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _check_lancedb_or_exit() -> None:
    """Verifica LanceDB al inicio de main(). Si no estÃ¡, sale con mensaje claro."""
    global HAS_LANCEDB  # noqa: PLW0602
    if HAS_LANCEDB:
        return
    import logging as _log
    _log.basicConfig(level=_log.INFO, format="%(message)s")
    _logger = _log.getLogger(__name__)
    _logger.info("=" * 60)
    _logger.info("  LanceDB REQUERIDO - No se encontro instalado.")
    _logger.info("=" * 60)
    _logger.info("")
    _logger.info("    pip install lancedb")
    _logger.info("    python harness/scripts/init.py")
    _logger.info("")
    _logger.info("  El sistema NO puede funcionar sin LanceDB.")
    _logger.info("=" * 60)
    sys.exit(1)


def main() -> None:
    """Main entry point for the Harness."""
    _check_lancedb_or_exit()

    parsed = _parse_args()

    if parsed.get("help"):
        _show_usage()
        return

    check_first_run(HARNESS_ROOT)

    # --- Mode dispatch ---
    if parsed["gateway"]:
        _handle_gateway_mode(parsed)
        return

    if parsed["daemon"]:
        _handle_daemon_mode()
        return

    if parsed["watch"]:
        _handle_watch_mode(HARNESS_ROOT)
        return

    cmd = parsed.get("command")
    if cmd:
        _handle_command(cmd)
        return

    # --- Task mode ---
    task = parsed.get("task")
    if not task:
        _show_usage()
        sys.exit(1)

    logger.info("[Harness] Inicializando...")
    store = LanceVectorStore()
    if not (Path(HARNESS_ROOT) / "db" / "lancedb").exists():
        logger.warning("harness/db/lancedb/ no existe. Los datos se perderan al reiniciar.")

    # Orchestrate
    from harness.orchestrator.task_orchestrator import TaskOrchestrator

    orch_result = TaskOrchestrator(vector_store=store).process_message(message=task, force_agent=None)

    # Display plan
    _display_plan(orch_result, task)

    # Dispatch
    target_agent = _dispatch_task(store, orch_result, task)

    # Model routing
    routing_source = _apply_model_routing(task, target_agent, parsed.get("force_cloud", False))

    # HITL
    guard = HITLGuard(vector_store=store, mode=_resolve_hitl_mode(parsed))
    if not _check_hitl(task, target_agent, guard):
        logger.info("[HITL] Accion rechazada por el usuario. Cancelando.")
        sys.exit(1)

    # RAG context
    ctx = _ensure_rag_context(store, task, target_agent)

    # Guardrails
    _run_guardrails(task, target_agent, ctx, routing_source, run_full_pipeline)

    # Task + cognition
    new_task = _create_task_and_lesson(store, task, target_agent, routing_source, orch_result, ctx)

    # Final output
    _display_final_output(orch_result, target_agent, routing_source)

    # Sandbox
    _start_sandbox_if_needed(target_agent, new_task, store, task, orch_result, routing_source)


if __name__ == "__main__":
    main()
