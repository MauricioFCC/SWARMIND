"""
Harness — Multi-Agent Execution Engine (portable base)
Entry point for the agent orchestration system with LanceDB memory.

Usage:
    python harness/run.py "@rol: describe tu tarea"
    python harness/run.py --force-cloud "@software-engineer: crear API"
    python harness/run.py --auto-pilot "@data-architect: migrar DB"
    python harness/run.py --hitl-sensitive "@devops-sre: deploy"

Features:
    - ModelRouter: Hybrid local/cloud model routing (Ollama + Cloud API)
    - HITLGuard: Human-in-the-Loop for destructive actions
    - MCP Client: Universal JSON-RPC tool execution
    - LanceDB memory with RAG context assembly
    - SandboxLoop for autonomous code execution

Flags:
    --daemon                Inicia scheduler en background
    --gateway <type>        Modo gateway (cli, slack, telegram)
    --force-cloud           Override ModelRouter → siempre cloud
    --auto-pilot            Desactiva HITL (solo entornos de confianza)
    --hitl-sensitive        HITL solo para acciones críticas
    !evolve mutate @<a> ".." Evolucion de prompts
    !schedule add <n> ...   Programar job
    !schedule list          Listar jobs
"""
import sys
import os
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Verificar LanceDB antes de cualquier otra operacion
# ---------------------------------------------------------------------------
try:
    import lancedb  # noqa: F401
except ImportError:
    print("=" * 60)
    print("  LanceDB REQUERIDO — No se encontro instalado.")
    print("=" * 60)
    print()
    print("  Ejecuta uno de estos comandos:")
    print()
    print("    pip install lancedb")
    print("    python harness/scripts/init.py")
    print()
    print("  El sistema NO puede funcionar sin LanceDB.")
    print("=" * 60)
    sys.exit(1)

from harness.orchestrator.task_manager import TaskManager
from harness.orchestrator.delegation_engine import DelegationEngine
from harness.memory_rag.context_assembler import ContextAssembler
from harness.memory_rag.lance_vector_store import LanceVectorStore
from harness.evolve_loop.cognition_sync import CognitionSync
from harness.memory_rag.doc_ingester import DocumentChunker, ingest_directory

# New modules
from harness.model_router.router import ModelRouter
from harness.orchestrator.hitl_guard import HITLGuard

try:
    from opencode.core.guardrails import run_full_pipeline
    HAS_GUARDRAILS = True
except ImportError:
    HAS_GUARDRAILS = False


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> Dict[str, Any]:
    """Parse CLI arguments, extracting flags and the task string."""
    args = sys.argv[1:]
    parsed: Dict[str, Any] = {
        "daemon": False,
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
        if arg == "--daemon":
            parsed["daemon"] = True
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


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _handle_db_migrate(store: LanceVectorStore, cmd: str) -> None:
    """
    Handle ``!db migrate [--path <ruta>]``.
    """
    from harness.db.migrate_db import DBMigrator

    migrator = DBMigrator()

    parts = cmd.split()
    if "--path" in parts:
        idx = parts.index("--path")
        custom_path = parts[idx + 1] if idx + 1 < len(parts) else None
        if custom_path:
            result = migrator.migrate(custom_path)
        else:
            print("[DB] Especifica una ruta: !db migrate --path <ruta>")
            return
    else:
        imports = migrator.scan_imports()
        if not imports:
            print("[DB] No hay bases para migrar.")
            return
        for imp in imports:
            print(f"[DB] Migrando '{imp['name']}'...")
            result = migrator.migrate(imp["path"])

    # Print results
    if result.get("migrated_collections"):
        print("[DB] Migradas: {}".format(", ".join(result["migrated_collections"])))
    if result.get("created"):
        print("[DB] Creadas: {}".format(", ".join(result["created"])))
    for s in result.get("skipped", []):
        print("[DB] SKIP: {}".format(s))
    for e in result.get("errors", []):
        print("[DB] ERROR: {}".format(e))
    if result.get("backup_path"):
        print("[DB] Backup: {}".format(result["backup_path"]))


def _handle_db_list_imports() -> None:
    """
    Handle ``!db list-imports``.
    """
    from harness.db.migrate_db import DBMigrator

    migrator = DBMigrator()
    imports = migrator.scan_imports()
    if imports:
        print("\n[DB] Bases detectadas ({}):".format(len(imports)))
        for imp in imports:
            colls = ", ".join(imp["collections"])
            print("  * {}: {} ({})".format(imp["name"], colls, imp["estimated_size_human"]))
    else:
        print("[DB] No se detectaron bases de datos en import/")


def _handle_db_stats(store: LanceVectorStore) -> None:
    """
    Handle ``!db stats``.
    """
    from harness.db.migrate_db import DBMigrator

    migrator = DBMigrator()
    stats = migrator.get_stats()
    print("\n[DB] Estadisticas de BD activa:")
    print("  Path:   {}".format(stats.get("path", "N/A")))
    print("  Chunks: {}".format(stats["total_chunks"]))
    print("  Tamano: {}".format(stats.get("size_human", "N/A")))
    print("  Ultima mod: {}".format(stats.get("last_modified", "N/A")))
    print("  Colecciones:")
    for coll in stats["collections"]:
        count = coll["count"]
        if count >= 0:
            print("  * {}: {} registros".format(coll["name"], count))
        else:
            print("  * {}: ERROR {}".format(coll["name"], coll.get("error", "")))


def _handle_db_rollback(cmd: str) -> None:
    """
    Handle ``!db rollback <backup_path>``.
    """
    from harness.db.migrate_db import DBMigrator

    parts = cmd.split(maxsplit=2)
    if len(parts) < 2:
        print("[DB] Uso: !db rollback <ruta_del_backup>")
        return

    backup_path = parts[2] if len(parts) > 2 else ""
    if not backup_path:
        print("[DB] Uso: !db rollback <ruta_del_backup>")
        return

    migrator = DBMigrator()
    success = migrator.rollback(backup_path)
    if success:
        print("[DB] Base restaurada desde: {}".format(backup_path))
    else:
        print("[DB] Error al restaurar desde: {}".format(backup_path))


def _handle_evolve_mutate(store: LanceVectorStore, cmd: str) -> None:
    """
    Handle ``!evolve mutate @<agent> "<task>"``.
    """
    import shlex

    parts = shlex.split(cmd)
    if len(parts) < 4:
        print("[Harness] Uso: !evolve mutate @<agent> \"<task>\"")
        return

    agent_arg = parts[2].lstrip("@")
    task_arg = parts[3]

    agent_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        ".opencode", "agents", f"{agent_arg}.md"
    )
    if not os.path.exists(agent_path):
        print(f"[Harness] Agente '{agent_arg}' no encontrado en {agent_path}")
        return

    from harness.evolve_loop.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(vector_store=store)
    print(f"[Harness] Mutando prompt de @{agent_arg}...")
    mutants = evolver.mutate_prompt(agent_path)

    if not mutants:
        print("[Harness] No se generaron mutantes.")
        return

    print(f"[Harness] Mutantes generados ({len(mutants)}):")
    for m in mutants:
        print(f"  - {m}")

    print(f"\n[Harness] Evaluando mutantes con tarea: {task_arg[:80]}...")
    scores = evolver.evaluate_mutants(agent_path, mutants, task_arg)

    print("\n[Harness] Resultados de evaluacion:")
    for label, result in sorted(scores.items(), key=lambda x: -x[1].get("score", 0)):
        print(
            f"  {label}: tokens={result.get('tokens')} "
            f"success={result.get('success')} "
            f"time={result.get('time', 0):.3f}s "
            f"score={result.get('score', 0):.1f}"
        )

    best_label = "original"
    best_score = -9999
    for label, result in scores.items():
        if label != "original" and result.get("score", -9999) > best_score:
            best_score = result.get("score", -9999)
            best_label = label

    if best_label != "original" and best_score > scores.get("original", {}).get("score", 0):
        winner = next(
            (m for m in mutants if best_label in m),
            None,
        )
        if winner:
            print(f"\n[Harness] Promoviendo ganador: {best_label}")
            promoted = evolver.promote_winner(winner)
            if promoted:
                print(f"[Harness] Prompt de @{agent_arg} actualizado exitosamente.")
        else:
            print("[Harness] No se pudo determinar el ganador.")
    else:
        print(f"[Harness] Original conservado (ningun mutante supero el score original).")


def _handle_schedule_add(store: LanceVectorStore, cmd: str) -> None:
    """Handle ``!schedule add <name> --cron "<cron>" --task "<cmd>"``."""
    import shlex

    parts = shlex.split(cmd)
    if len(parts) < 5:
        print("[Harness] Uso: !schedule add <name> --cron \"<cron>\" --task \"<cmd>\"")
        print("[Harness]   O: !schedule add <name> --interval \"30m\" --task \"<cmd>\"")
        print("[Harness]   O: !schedule add <name> --once \"ISO\" --task \"<cmd>\"")
        return

    name = parts[2]
    trigger = ""
    trigger_value = ""
    command = ""

    j = 3
    while j < len(parts):
        if parts[j] == "--cron" and j + 1 < len(parts):
            trigger = "cron"
            trigger_value = parts[j + 1]
            j += 2
        elif parts[j] == "--interval" and j + 1 < len(parts):
            trigger = "interval"
            trigger_value = parts[j + 1]
            j += 2
        elif parts[j] == "--once" and j + 1 < len(parts):
            trigger = "once"
            trigger_value = parts[j + 1]
            j += 2
        elif parts[j] == "--task" and j + 1 < len(parts):
            command = parts[j + 1]
            j += 2
        else:
            j += 1

    if not trigger or not command:
        print("[Harness] Error: se requiere --cron/--interval/--once y --task")
        return

    from harness.orchestrator.scheduler import Scheduler

    scheduler = Scheduler(vector_store=store)
    job = scheduler.add_job(
        name=name,
        trigger=trigger,
        trigger_value=trigger_value,
        command=command,
    )
    print(f"[Harness] Job programado: {job.name} ({job.trigger}: {job.trigger_value})")


def _handle_schedule_list(store: LanceVectorStore) -> None:
    """Handle ``!schedule list``."""
    from harness.orchestrator.scheduler import Scheduler

    scheduler = Scheduler(vector_store=store)
    jobs = scheduler.list_jobs()
    if not jobs:
        print("[Harness] No hay jobs programados.")
        return

    print(f"[Harness] Jobs programados ({len(jobs)}):")
    for job in jobs:
        status = "activo" if job.enabled else "inactivo"
        print(
            f"  - {job.name}: {job.trigger} = {job.trigger_value} "
            f"[{status}] ultimo: {job.last_run or 'nunca'}"
        )


# ---------------------------------------------------------------------------
# Model Routing
# ---------------------------------------------------------------------------


def _apply_model_routing(task: str, target_agent: str, force_cloud: bool = False) -> str:
    """
    Apply ModelRouter to determine local vs cloud execution.

    Returns the routing source ("local" or "cloud") for logging.
    """
    router = ModelRouter()

    if force_cloud:
        print(f"[ROUTER] @{target_agent} → cloud (--force-cloud override)")
        return "cloud"

    decision = router.route(task, target_agent)
    model_name = decision.model
    provider = decision.provider
    source = decision.source
    reason = decision.reason

    print(f"[ROUTER] @{target_agent} → {source} ({provider}/{model_name}) [{reason}]")

    # If local and Ollama not available, show helpful message
    if source == "local":
        if not router._is_ollama_available():
            print(f"[ROUTER] ⚠️  Ollama no detectado. Modelo local '{model_name}' no disponible.")
            if router.config.get("local", {}).get("fallback_to_cloud", True):
                print(f"[ROUTER] ⚠️  Fallback a cloud automatico activado.")
            else:
                print(f"[ROUTER] 💡 Instala Ollama: https://ollama.com")
                print(f"[ROUTER] 💡 O usa --force-cloud para modo cloud")

    return source


# ---------------------------------------------------------------------------
# HITL Guard
# ---------------------------------------------------------------------------


def _check_hitl(action: str, agent_role: str, guard: HITLGuard) -> bool:
    """
    Check if an action needs human approval and handle it.

    Returns True if action is approved/safe, False if blocked.
    """
    if guard.mode == "auto_pilot":
        return True

    # Only check if the action looks destructive
    check = guard.check_action(action, agent_role)
    if check["approved"]:
        return True

    print(f"[HITL] @{agent_role} propone accion que requiere aprobacion:")
    print(f"[HITL]   {action[:200]}")

    return guard.request_approval(action, agent_role)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parsed = _parse_args()

    # --- Gateway mode ---
    if parsed["gateway"]:
        from harness.gateway.gateway import GatewayManager, Message, load_gateway_config

        config = load_gateway_config()
        if parsed["gateway"] not in config.get("active_gateways", []):
            config["active_gateways"] = [parsed["gateway"]]

        manager = GatewayManager(config)
        print(f"[Harness] Gateway mode: {parsed['gateway']}")
        print(f"[Harness] Gateways activas: {manager.list_active_gateways()}")

        cli_gw = manager.get_gateway("cli")
        if cli_gw and cli_gw.is_active():
            print("[Harness] CLI gateway activa. Escribe mensajes o 'exit' para salir.")
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

        print("[Harness] Daemon mode — iniciando scheduler en background...")
        store = LanceVectorStore()
        scheduler = Scheduler(vector_store=store)
        scheduler.run_scheduler()
        print("[Harness] Scheduler corriendo. Presiona Ctrl+C para detener.")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            scheduler.stop()
            print("\n[Harness] Scheduler detenido.")
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
        else:
            print(f"[Harness] Comando desconocido: {cmd}")
        return

    # --- Standard task routing ---
    task = parsed.get("task")
    if not task:
        print("Uso: python harness/run.py \"<descripcion de la tarea>\"")
        print("Ej: python harness/run.py \"@software-engineer: Implementa endpoint de API\"")
        print()
        print("Flags:")
        print("  --daemon                    Inicia scheduler en background")
        print("  --gateway <type>            Modo gateway (cli, slack, telegram)")
        print("  --force-cloud               Override: todas las tareas a cloud API")
        print("  --auto-pilot                Desactiva HITL (entornos de confianza)")
        print("  --hitl-sensitive            HITL solo para acciones criticas")
        print("  !evolve mutate @<a> \"<t>\"   Evolucion de prompts")
        print("  !schedule add <n> ...       Programar job")
        print("  !schedule list              Listar jobs")
        print("  !db migrate                 Migrar BD desde import/")
        print("  !db migrate --path <ruta>   Migrar BD especifica")
        print("  !db list-imports            Listar BDs disponibles")
        print("  !db stats                   Estadisticas de BD activa")
        print("  !db rollback <backup>       Restaurar desde backup")
        sys.exit(1)

    print("[Harness] Inicializando...")

    store = LanceVectorStore()
    tm = TaskManager(vector_store=store)
    engine = DelegationEngine()
    assembler = ContextAssembler(store)
    cognition = CognitionSync(store)

    target_agent = engine.route_message(task)
    print(f"[Harness] Ruteando a @{target_agent}")

    # ── ModelRouter: determinar local vs cloud ──
    force_cloud = parsed.get("force_cloud", False)
    routing_source = _apply_model_routing(task, target_agent, force_cloud)

    # ── HITL Guard: inicializar ──
    hitl_mode = "hitl"
    if parsed.get("auto_pilot"):
        hitl_mode = "auto_pilot"
    elif parsed.get("hitl_sensitive"):
        hitl_mode = "hitl_sensitive"

    guard = HITLGuard(vector_store=store, mode=hitl_mode)
    if hitl_mode != "hitl":
        print(f"[HITL] Modo: {hitl_mode}")

    # ── HITL: check task for destructive actions ──
    if not _check_hitl(task, target_agent, guard):
        print("[HITL] Accion rechazada por el usuario. Cancelando.")
        sys.exit(1)

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
            "routing_source": routing_source,
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
                f"Routing: {routing_source}\n"
                f"Chunks RAG recuperados: {len(ctx.relevant_docs)}\n"
                f"Tokens de contexto: {ctx.metadata.get('total_tokens_used', 0)}"
            ),
            domain="harness.routing",
            tags=["routing", target_agent, routing_source, "harness"],
            metrics={
                "rag_chunks": len(ctx.relevant_docs),
                "token_estimate": ctx.metadata.get("total_tokens_used", 0),
                "routing_source": routing_source,
            },
        )
        print(f"[Harness] Leccion registrada en cognition: {lesson.id}")
    except Exception as exc:
        print(f"[Harness] Cognition store no disponible: {exc}")

    print(f"[Harness] Tarea enrutada a @{target_agent} ({routing_source})")
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

        bus = AgentBus(vector_store=store)
        bus.post_message(
            channel=channel,
            from_agent="@harness",
            to_agent="@software-engineer",
            message=(
                f"Tarea creada: **{task[:80]}**\n"
                f"Task ID: `{task_id}`\n"
                f"Routing: `{routing_source}`\n\n"
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
