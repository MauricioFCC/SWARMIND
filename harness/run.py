"""
Harness — Multi-Agent Execution Engine (portable base)
Entry point for the agent orchestration system with LanceDB memory.

Usage:
    python harness/run.py "@rol: describe tu tarea"
    python harness/run.py --force-cloud "@software-engineer: crear API"
    python harness/run.py --auto-pilot "@data-architect: migrar DB"
    python harness/run.py --hitl-sensitive "@devops-sre: deploy"
    python harness/run.py -s "implementa una API REST"           → detecta rol automaticamente

Features:
    - ModelRouter: Hybrid local/cloud model routing (Ollama + Cloud API)
    - HITLGuard: Human-in-the-Loop for destructive actions
    - MCP Client: Universal JSON-RPC tool execution
    - LanceDB memory with RAG context assembly
    - SandboxLoop for autonomous code execution

Flags:
    --daemon                Inicia scheduler en background
    --watch                 Modo watch: monitorea cambios en harness/ y .opencode/
    --gateway <type>        Modo gateway (cli, slack, telegram)
    --force-cloud           Override ModelRouter → siempre cloud
    --auto-pilot            Desactiva HITL (solo entornos de confianza)
    --hitl-sensitive        HITL solo para acciones críticas
    !evolve mutate @<a> ".." Evolucion de prompts
    !schedule add <n> ...   Programar job
    !schedule list          Listar jobs
    !iteration end          Pipeline fin de iteracion (bugs, security, docs, tokens, commit)
    !iteration end --dry-run    Simulacion del pipeline
    !iteration end --skip-bugs  Salta bug hunting
    !iteration end --skip-sec   Salta security review
    !iteration end --skip-docs  Salta docs update
    !iteration report       Muestra ultimo reporte de iteracion
    !hooks install          Instala pre-commit hook (auto-pipeline en commits)
    !hooks uninstall        Desinstala pre-commit hook
    !hooks status           Muestra estado del pre-commit hook
"""
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging
from datetime import datetime
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

HARNESS_ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Verificar LanceDB antes de cualquier otra operacion
# ---------------------------------------------------------------------------
try:
    import lancedb  # noqa: F401
except ImportError:
    logger.info("=" * 60)
    logger.info("  LanceDB REQUERIDO — No se encontro instalado.")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Ejecuta uno de estos comandos:")
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

# New modules
from harness.model_router.router import ModelRouter
from harness.orchestrator.hitl_guard import HITLGuard

try:
    from opencode.core.guardrails import run_full_pipeline
    HAS_GUARDRAILS = True
except ImportError:
    HAS_GUARDRAILS = False


# ---------------------------------------------------------------------------
# First-run onboarding
# ---------------------------------------------------------------------------


def _check_first_run() -> bool:
    """Detecta si es primera ejecucion del harness en este proyecto."""
    marker_file = Path(HARNESS_ROOT) / ".harness_initialized"
    if marker_file.exists():
        return False

    logger.info("=" * 60)
    logger.info("  \U0001F680 AGENTIC Harness -- Primera ejecucion detectada")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Vamos a configurar tu proyecto paso a paso.")
    logger.info("")

    # Paso 1: Nombre del proyecto
    try:
        project_name = input("  1. Nombre del proyecto [default: mi-proyecto]: ").strip()
    except (EOFError, KeyboardInterrupt):
        project_name = ""
    if not project_name:
        project_name = "mi-proyecto"

    # Paso 2: Stack tecnologico
    print(f"\n  2. Stack tecnologico:")
    print(f"     a) Python")
    print(f"     b) Rust")
    print(f"     c) Go")
    print(f"     d) Node/TypeScript")
    print(f"     e) Otro")
    try:
        stack = input("     Selecciona tu stack [a]: ").strip().lower() or "a"
    except (EOFError, KeyboardInterrupt):
        stack = "a"
    stack_map = {"a": "Python", "b": "Rust", "c": "Go", "d": "Node/TypeScript", "e": "Otro"}
    tech_stack = stack_map.get(stack, "Python")

    # Paso 3: Dominio
    print(f"\n  3. Dominio del proyecto:")
    print(f"     a) Web")
    print(f"     b) Trading")
    print(f"     c) CLI/Herramienta")
    print(f"     d) API/Microservicio")
    print(f"     e) Otro")
    try:
        dom = input("     Selecciona el dominio [a]: ").strip().lower() or "a"
    except (EOFError, KeyboardInterrupt):
        dom = "a"
    dom_map = {"a": "web", "b": "trading", "c": "cli", "d": "api", "e": "otro"}
    domain = dom_map.get(dom, "web")

    # Paso 4: Auto-configurar project_config.yaml
    config_path = Path(HARNESS_ROOT).parent / ".opencode" / "config" / "project_config.yaml"
    if config_path.exists():
        config_content = config_path.read_text(encoding="utf-8")
        config_content = config_content.replace('PROJECT_NAME: ""', f'PROJECT_NAME: "{project_name}"')
        config_content = config_content.replace('DOMAIN: ""', f'DOMAIN: "{domain}"')
        config_content = config_content.replace('TECH_STACK: ""', f'TECH_STACK: "{tech_stack}"')
        config_path.write_text(config_content, encoding="utf-8")
        logger.info(f"  project_config.yaml actualizado: {project_name} ({tech_stack}, {domain})")

    # Paso 5: Ejecutar init.py
    logger.info("")
    logger.info("  Ejecutando init.py para completar la configuracion...")
    import subprocess as _subprocess

    _subprocess.run([sys.executable, str(Path(HARNESS_ROOT) / "scripts" / "init.py")], cwd=HARNESS_ROOT.parent)

    # Paso 6: Crear marker
    marker_file.write_text(f"initialized: {datetime.now().isoformat()}\nproject: {project_name}\n")
    logger.info("")
    logger.info("  Harness configurado. Listo para usar!")
    logger.info("")
    logger.info("  Proximos pasos:")
    logger.info(f"    python harness/run.py \"@project-manager: planificar {project_name}\"")
    logger.info("    python harness/run.py --watch")
    logger.info("")
    return True


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
    logger.info("  -s, --simplified            Entrada simplificada (detecta rol automaticamente)")
    logger.info("  --help                      Muestra esta ayuda")
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
    logger.info("  !iteration report           Muestra ultimo reporte")
    logger.info("  !hooks install              Instala pre-commit hook")
    logger.info("  !hooks uninstall            Desinstala pre-commit hook")
    logger.info("  !hooks status               Muestra estado del hook")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


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
        "simplified": False,
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
        elif arg in ("--simplified", "-s"):
            parsed["simplified"] = True
            i += 1
        elif arg.startswith("!"):
            parsed["command"] = arg
            i += 1
        else:
            parsed["task"] = arg
            i += 1

    return parsed


# Import command handlers from separated module for file size compliance
from harness.run_commands import (
    _handle_db_migrate, _handle_db_list_imports, _handle_db_stats, _handle_db_rollback,
    _parse_iteration_flags, _handle_iteration_end, _handle_iteration_report,
    _handle_hooks_install, _handle_hooks_uninstall, _handle_hooks_status,
    _handle_evolve_mutate, _handle_schedule_add, _handle_schedule_list,
    _apply_model_routing, _check_hitl, _get_files_to_watch, _ok, _warn, _err, _bold, _cyan, _safe_print,
)


def _handle_watch_mode() -> None:
    """
    Handle ``--watch`` flag — monitors harness/ and .opencode/ for changes.

    Uses polling every 2 seconds with os.stat() to compare modification times.
    When changes are detected, waits 3 seconds of inactivity then runs the
    end_of_iteration pipeline in quick mode (--watch).
    """
    import time as _time
    from datetime import datetime as _datetime

    logger.info("[Harness] Watch mode activado — monitoreando:")
    logger.info(f"  - {HARNESS_ROOT}")
    logger.info(f"  - {HARNESS_ROOT.parent / '.opencode'}")
    logger.info(f"  Excluyendo: harness/db/, __pycache__/, .git/")
    logger.info("")

    # Quick check: ensure end_of_iteration.py exists
    eoi_script = HARNESS_ROOT / "scripts" / "end_of_iteration.py"
    if not eoi_script.exists():
        logger.info(f"[Harness] {_err('[ERROR]')} No se encontro: {eoi_script}")
        return

    # Initial snapshot
    last_snapshot = _get_files_to_watch()
    idle_since: Optional[float] = None
    debounce_seconds = 3.0

    _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
    _safe_print(f"  Press Ctrl+C to stop.")
    _safe_print()

    try:
        while True:
            _time.sleep(2)
            now = _time.time()

            new_snapshot = _get_files_to_watch()
            changed_files = []

            # Check for new/modified files
            for fpath, mtime in new_snapshot.items():
                old_mtime = last_snapshot.get(fpath)
                if old_mtime is None or mtime > old_mtime:
                    changed_files.append(fpath)

            # Check for deleted files
            for fpath in last_snapshot:
                if fpath not in new_snapshot:
                    changed_files.append(fpath)

            if not changed_files:
                idle_since = None
                continue

            if idle_since is None:
                idle_since = now
                continue

            # Wait for inactivity (debounce)
            if now - idle_since < debounce_seconds:
                continue

            # Change detected + inactive for debounce_seconds -> run pipeline
            timestamp = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for f in changed_files[:5]:
                rel = os.path.relpath(f, str(HARNESS_ROOT.parent))
                _safe_print(f"  [{timestamp}] change detected: {rel}")
            if len(changed_files) > 5:
                _safe_print(f"  [{timestamp}] ... and {len(changed_files) - 5} more")

            # Run pipeline in watch mode
            _safe_print(f"  [{timestamp}] Running check...")
            try:
                import subprocess as _subprocess
                result = _subprocess.run(
                    [sys.executable, str(eoi_script), "--watch"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(HARNESS_ROOT.parent),
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

            # Reset snapshot
            last_snapshot = new_snapshot.copy()
            idle_since = None
            _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
            logger.info("")

    except KeyboardInterrupt:
        _safe_print(f"\n  {_cyan('[WATCH]')} Watch mode detenido.")
        return


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main."""
    parsed = _parse_args()

    # --- Handle --help immediately (before first-run check) ---
    if parsed.get("help"):
        _show_usage()
        return

    # --- First-run onboarding (before any command processing) ---
    _check_first_run()

    # --- Gateway mode ---
    if parsed["gateway"]:
        from harness.gateway.gateway import GatewayManager, Message, load_gateway_config

        config = load_gateway_config()
        if parsed["gateway"] not in config.get("active_gateways", []):
            config["active_gateways"] = [parsed["gateway"]]

        manager = GatewayManager(config)
        logger.info(f"[Harness] Gateway mode: {parsed['gateway']}")
        logger.info(f"[Harness] Gateways activas: {manager.list_active_gateways()}")

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

        logger.info("[Harness] Daemon mode — iniciando scheduler en background...")
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
        elif cmd.startswith("!iteration report"):
            _handle_iteration_report()
        elif cmd.startswith("!hooks install"):
            _handle_hooks_install()
        elif cmd.startswith("!hooks uninstall"):
            _handle_hooks_uninstall()
        elif cmd.startswith("!hooks status"):
            _handle_hooks_status()
        else:
            logger.info(f"[Harness] Comando desconocido: {cmd}")
        return

    # --- Simplified mode (auto-detect role) ---
    task = parsed.get("task")
    if parsed.get("simplified") and task:
        # If task doesn't start with @rol:, auto-detect
        if not task.startswith("@"):
            try:
                from harness.orchestrator.delegation_engine import DelegationEngine
                engine = DelegationEngine()
                detected = engine.route_message(task)
                if detected:
                    task = f"@{detected}: {task}"
                    logger.info(f"[Harness] Simplified: rol detectado @{detected}")
                else:
                    logger.info("[Harness] Simplified: no se pudo detectar rol, usando @project-manager")
                    task = f"@project-manager: {task}"
            except Exception as exc:
                logger.info(f"[Harness] Simplified: error en deteccion: {exc}")
                logger.info("[Harness] Simplified: usando @project-manager por defecto")
                task = f"@project-manager: {task}"
        parsed["task"] = task

    # --- Standard task routing ---
    if not task:
        _show_usage()
        sys.exit(1)

    logger.info("[Harness] Inicializando...")

    store = LanceVectorStore()
    if store is None:
        logger.warning("LanceVectorStore no inicializado. Intentando crear...")
        store = LanceVectorStore()

    tm = TaskManager(vector_store=store)
    if not os.path.exists(os.path.join(HARNESS_ROOT, "db", "lancedb")):
        logger.warning("harness/db/lancedb/ no existe. Los datos se perderán al reiniciar.")
    engine = DelegationEngine()
    assembler = ContextAssembler(store)
    cognition = CognitionSync(store)

    target_agent = engine.route_message(task)
    logger.info(f"[Harness] Ruteando a @{target_agent}")

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
        logger.info(f"[HITL] Modo: {hitl_mode}")

    # ── HITL: check task for destructive actions ──
    if not _check_hitl(task, target_agent, guard):
        logger.info("[HITL] Accion rechazada por el usuario. Cancelando.")
        sys.exit(1)

    ctx = assembler.assemble(task, target_agent)
    if ctx.relevant_docs:
        logger.info(f"[Harness] Contexto RAG: {len(ctx.relevant_docs)} chunks, {ctx.metadata.get('total_tokens_used', 0)} tokens")
    else:
        logger.info("[Harness] Contexto RAG: sin chunks, auto-ingestando documentos...")
        chunker = DocumentChunker(chunk_size=25, overlap=3)
        stats = ingest_directory(store, ["docs", "harness", ".opencode"], chunker)
        logger.info(f"[Harness] Ingest: {stats['files_processed']} archivos, {stats['chunks_inserted']} chunks")
        if stats['chunks_inserted'] > 0:
            ctx = assembler.assemble(task, target_agent)
            if ctx.relevant_docs:
                logger.info(f"[Harness] Contexto RAG tras ingest: {len(ctx.relevant_docs)} chunks")

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
            logger.info(f"[Harness] Guardrails BLOCKED en fase {blocked_at}: {summary.get('failed_rules', [])}")
            sys.exit(1)
        logger.info(f"[Harness] Guardrails OK ({result['summary']['passed']}/{result['summary']['total_checks']} checks pasados)")
    else:
        logger.info("[Harness] Guardrails no disponible (opencode.core.guardrails no importado)")

    new_task = tm.create_task(
        title=task[:80],
        description=task,
        agent_assigned=target_agent,
        priority=5
    )
    if new_task:
        task_id = getattr(new_task, 'id', 'N/A')
        task_status = getattr(new_task, 'status', 'pending')
        logger.info(f"[Harness] Tarea creada: {task_id} (estado: {task_status})")

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
        logger.info(f"[Harness] Leccion registrada en cognition: {lesson.id}")
    except Exception as exc:
        logger.info(f"[Harness] Cognition store no disponible: {exc}")

    logger.info(f"[Harness] Tarea enrutada a @{target_agent} ({routing_source})")
    logger.info(f"[Harness] Para ejecutar: invoca @{target_agent} con el contexto ensamblado")

    # ------------------------------------------------------------------
    # Si el target_agent es @software-engineer, iniciar SandboxLoop
    # ------------------------------------------------------------------
    if target_agent == "software-engineer" and new_task:
        from harness.orchestrator.sandbox_loop import SandboxLoop
        from harness.orchestrator.agent_bus import AgentBus

        task_id = getattr(new_task, 'id', 'N/A')
        logger.info(f"\n[Harness] [Sandbox] Iniciando SandboxLoop para task_id={task_id}")

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
        logger.info(f"[Harness] SandboxLoop listo en canal {channel}")
        logger.info(f"[Harness] Para activar el bucle autonomo con codigo:")
        logger.info(f"[Harness]   SandboxLoop().run_autonomous('{task_id}', code='...', test_command='pytest')")


if __name__ == "__main__":
    main()
