"""
Command handlers for harness/run.py — extracted for file size compliance.
"""
from __future__ import annotations

import os
import subprocess as _subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging
logger = logging.getLogger(__name__)


# ── RAG Commands ─────────────────────────────────────────────────────

def _handle_rag_ingest(store, cmd: str) -> None:
    """Handle ``!rag ingest [--dir <path>]``."""
    from harness.memory_rag.doc_ingester import ingest_project_directory
    import time

    parts = cmd.split()
    target_dir = None
    if "--dir" in parts:
        idx = parts.index("--dir")
        target_dir = parts[idx + 1] if idx + 1 < len(parts) else None

    if target_dir:
        directory = Path(target_dir).resolve()
    else:
        # Default: project root (excluye harness/ y .opencode/ por RAG_EXCLUDE)
        directory = Path(__file__).resolve().parent.parent.parent

    if not directory.is_dir():
        logger.info("[RAG] Directorio no encontrado: %s", directory)
        return

    logger.info("[RAG] Ingestando desde: %s", directory)
    start = time.time()
    try:
        stats = ingest_project_directory(str(directory), show_progress=True)
        elapsed = time.time() - start
        logger.info(
            "[RAG] \u2705 Completado: %d archivos, %d chunks en %.1fs",
            stats.get("files_processed", 0),
            stats.get("chunks_inserted", 0),
            elapsed,
        )
        if stats.get("errors", 0):
            logger.warning("[RAG] \u26a0\ufe0f %d errores", stats["errors"])
    except Exception as e:
        logger.error("[RAG] \u274c Error: %s", e)


def _handle_rag_stats(store) -> None:
    """Handle ``!rag stats`` — muestra estadisticas de la BD RAG."""
    colls = store.list_collections()
    logger.info("")
    logger.info("[RAG] Colecciones disponibles: %s", colls)
    if "rag_chunks" in colls:
        try:
            stats = store.get_collection_stats("rag_chunks")
            logger.info("[RAG] Coleccion 'rag_chunks':")
            logger.info("  Items: %d", stats.get("item_count", 0))
            logger.info("  Ultima actualizacion: %s", stats.get("last_updated", "N/A"))
        except Exception as exc:
            logger.info("[RAG] Coleccion 'rag_chunks' existe (error al obtener stats: %s)", exc)
            logger.info("  (Esto es normal si la BD esta vacia o es una version reciente de LanceDB)")
    else:
        logger.info("[RAG] Coleccion 'rag_chunks' no existe. Ejecuta '!rag ingest'.")
    logger.info("")


# ── DB Commands ──────────────────────────────────────────────────────

def _handle_db_migrate(store, cmd: str) -> None:
    """Handle ``!db migrate [--path <ruta>]``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    parts = cmd.split()
    if "--path" in parts:
        idx = parts.index("--path")
        custom_path = parts[idx + 1] if idx + 1 < len(parts) else None
        if custom_path:
            result = migrator.migrate(custom_path)
        else:
            logger.info("[DB] Especifica una ruta: !db migrate --path <ruta>")
            return
    else:
        imports = migrator.scan_imports()
        if not imports:
            logger.info("[DB] No hay bases para migrar.")
            return
        for imp in imports:
            logger.info(f"[DB] Migrando '{imp['name']}'...")
            result = migrator.migrate(imp["path"])
    if result.get("migrated_collections"):
        logger.info("[DB] Migradas: {}".format(", ".join(result["migrated_collections"])))
    if result.get("created"):
        logger.info("[DB] Creadas: {}".format(", ".join(result["created"])))
    for s in result.get("skipped", []):
        logger.info("[DB] SKIP: {}".format(s))
    for e in result.get("errors", []):
        logger.info("[DB] ERROR: {}".format(e))
    if result.get("backup_path"):
        logger.info("[DB] Backup: {}".format(result["backup_path"]))


def _handle_db_list_imports() -> None:
    """Handle ``!db list-imports``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    imports = migrator.scan_imports()
    if imports:
        logger.info("\n[DB] Bases detectadas ({}):".format(len(imports)))
        for imp in imports:
            colls = ", ".join(imp["collections"])
            logger.info("  * {}: {} ({})".format(imp["name"], colls, imp["estimated_size_human"]))
    else:
        logger.info("[DB] No se detectaron bases de datos en import/")


def _handle_db_stats(store) -> None:
    """Handle ``!db stats``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    stats = migrator.get_stats()
    logger.info("\n[DB] Estadisticas de BD activa:")
    logger.info("  Path:   {}".format(stats.get("path", "N/A")))
    logger.info("  Chunks: {}".format(stats["total_chunks"]))
    logger.info("  Tamano: {}".format(stats.get("size_human", "N/A")))
    logger.info("  Ultima mod: {}".format(stats.get("last_modified", "N/A")))
    logger.info("  Colecciones:")
    for coll in stats["collections"]:
        count = coll["count"]
        if count >= 0:
            logger.info("  * {}: {} registros".format(coll["name"], count))
        else:
            logger.info("  * {}: ERROR {}".format(coll["name"], coll.get("error", "")))


def _handle_db_rollback(cmd: str) -> None:
    """Handle ``!db rollback <backup_path>``."""
    from harness.db.migrate_db import DBMigrator
    parts = cmd.split(maxsplit=2)
    if len(parts) < 2:
        logger.info("[DB] Uso: !db rollback <ruta_del_backup>")
        return
    backup_path = parts[2] if len(parts) > 2 else ""
    if not backup_path:
        logger.info("[DB] Uso: !db rollback <ruta_del_backup>")
        return
    migrator = DBMigrator()
    success = migrator.rollback(backup_path)
    if success:
        logger.info("[DB] Base restaurada desde: {}".format(backup_path))
    else:
        logger.info("[DB] Error al restaurar desde: {}".format(backup_path))


# ── Iteration End ───────────────────────────────────────────────────

def _parse_iteration_flags(cmd: str) -> dict:
    """Parse flags from a !iteration end command."""
    flags = {"skip_bugs": False, "skip_sec": False, "skip_docs": False, "dry_run": False}
    parts = cmd.split()
    if "--dry-run" in parts:
        flags["dry_run"] = True
    if "--skip-bugs" in parts:
        flags["skip_bugs"] = True
    if "--skip-sec" in parts:
        flags["skip_sec"] = True
    if "--skip-docs" in parts:
        flags["skip_docs"] = True
    return flags


def _handle_iteration_end(cmd: str, harness_root) -> None:
    """Handle ``!iteration end [--dry-run] [--skip-bugs] [--skip-sec] [--skip-docs]``."""
    flags = _parse_iteration_flags(cmd)
    logger.info(f"[Harness] Iniciando pipeline de fin de iteracion...")
    if flags["dry_run"]:
        logger.info(f"[Harness] Modo DRY-RUN — no se modificaran archivos")
    if any([flags["skip_bugs"], flags["skip_sec"], flags["skip_docs"]]):
        skips = []
        if flags["skip_bugs"]:
            skips.append("bugs")
        if flags["skip_sec"]:
            skips.append("security")
        if flags["skip_docs"]:
            skips.append("docs")
        logger.info(f"[Harness] Fases saltadas: {', '.join(skips)}")
    sys.path.insert(0, str(harness_root.parent))
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline(
        skip_bugs=flags["skip_bugs"], skip_security=flags["skip_sec"],
        skip_docs=flags["skip_docs"], dry_run=flags["dry_run"],
    )


def _handle_iteration_report() -> None:
    """Handle ``!iteration report`` — shows the last saved iteration report."""
    from harness.scripts.end_of_iteration import print_last_report
    print_last_report()


# ── Hooks ────────────────────────────────────────────────────────────

def _handle_hooks_install() -> None:
    """Handle ``!hooks install`` — installs the pre-commit hook."""
    from harness.scripts.install_hooks import install_hook
    logger.info("[Harness] Instalando hook pre-commit...")
    install_hook()


def _handle_hooks_uninstall() -> None:
    """Handle ``!hooks uninstall`` — uninstalls the pre-commit hook."""
    from harness.scripts.install_hooks import uninstall_hook
    logger.info("[Harness] Desinstalando hook pre-commit...")
    uninstall_hook()


def _handle_hooks_status() -> None:
    """Handle ``!hooks status`` — shows hook installation status."""
    from harness.scripts.install_hooks import show_status
    show_status()


# ── Evolve ──────────────────────────────────────────────────────────

def _handle_evolve_mutate(store, cmd: str) -> None:
    """Handle ``!evolve mutate @<agent> \"<task>\"``."""
    import shlex
    from harness.evolve_loop.prompt_evolver import PromptEvolver
    parts = shlex.split(cmd)
    if len(parts) < 4:
        logger.info('[Harness] Uso: !evolve mutate @<agent> "<task>"')
        return
    agent_arg = parts[2].lstrip("@")
    task_arg = parts[3]
    agent_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        ".opencode", "agents", f"{agent_arg}.md"
    )
    if not os.path.exists(agent_path):
        logger.info(f"[Harness] Agente '{agent_arg}' no encontrado en {agent_path}")
        return
    evolver = PromptEvolver(vector_store=store)
    logger.info(f"[Harness] Mutando prompt de @{agent_arg}...")
    mutants = evolver.mutate_prompt(agent_path)
    if not mutants:
        logger.info("[Harness] No se generaron mutantes.")
        return
    logger.info(f"[Harness] Mutantes generados ({len(mutants)}):")
    for m in mutants:
        logger.info(f"  - {m}")
    logger.info(f"\n[Harness] Evaluando mutantes con tarea: {task_arg[:80]}...")
    scores = evolver.evaluate_mutants(agent_path, mutants, task_arg)
    logger.info("\n[Harness] Resultados de evaluacion:")
    for label, result in sorted(scores.items(), key=lambda x: -x[1].get("score", 0)):
        logger.info(
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
        winner = next((m for m in mutants if best_label in m), None)
        if winner:
            logger.info(f"\n[Harness] Promoviendo ganador: {best_label}")
            promoted = evolver.promote_winner(winner)
            if promoted:
                logger.info(f"[Harness] Prompt de @{agent_arg} actualizado exitosamente.")
        else:
            logger.info("[Harness] No se pudo determinar el ganador.")
    else:
        logger.info(f"[Harness] Original conservado (ningun mutante supero el score original).")


def _handle_schedule_add(store, cmd: str) -> None:
    """Handle ``!schedule add <name> --cron \"<cron>\" --task \"<cmd>\"``."""
    import shlex
    from harness.orchestrator.scheduler import Scheduler
    parts = shlex.split(cmd)
    if len(parts) < 5:
        logger.info('[Harness] Uso: !schedule add <name> --cron "<cron>" --task "<cmd>"')
        logger.info('[Harness]   O: !schedule add <name> --interval "30m" --task "<cmd>"')
        logger.info('[Harness]   O: !schedule add <name> --once "ISO" --task "<cmd>"')
        return
    name = parts[2]
    trigger = ""
    trigger_value = ""
    command = ""
    j = 3
    while j < len(parts):
        if parts[j] == "--cron" and j + 1 < len(parts):
            trigger = "cron"; trigger_value = parts[j + 1]; j += 2
        elif parts[j] == "--interval" and j + 1 < len(parts):
            trigger = "interval"; trigger_value = parts[j + 1]; j += 2
        elif parts[j] == "--once" and j + 1 < len(parts):
            trigger = "once"; trigger_value = parts[j + 1]; j += 2
        elif parts[j] == "--task" and j + 1 < len(parts):
            command = parts[j + 1]; j += 2
        else:
            j += 1
    if not trigger or not command:
        logger.info("[Harness] Error: se requiere --cron/--interval/--once y --task")
        return
    scheduler = Scheduler(vector_store=store)
    job = scheduler.add_job(name=name, trigger=trigger, trigger_value=trigger_value, command=command)
    logger.info(f"[Harness] Job programado: {job.name} ({job.trigger}: {job.trigger_value})")


def _handle_schedule_list(store) -> None:
    """Handle ``!schedule list``."""
    from harness.orchestrator.scheduler import Scheduler
    scheduler = Scheduler(vector_store=store)
    jobs = scheduler.list_jobs()
    if not jobs:
        logger.info("[Harness] No hay jobs programados.")
        return
    logger.info(f"[Harness] Jobs programados ({len(jobs)}):")
    for job in jobs:
        status = "activo" if job.enabled else "inactivo"
        logger.info(f"  - {job.name}: {job.trigger} = {job.trigger_value} [{status}] ultimo: {job.last_run or 'nunca'}")


# ── Model Routing ────────────────────────────────────────────────────

def _apply_model_routing(task: str, target_agent: str, force_cloud: bool = False) -> str:
    """Apply ModelRouter to determine local vs cloud execution.

    Returns the routing source ("local" or "cloud") for logging.
    """
    from harness.model_router.router import ModelRouter
    router = ModelRouter()
    if force_cloud:
        logger.info(f"[ROUTER] @{target_agent} → cloud (--force-cloud override)")
        return "cloud"
    decision = router.route(task, target_agent)
    source = decision.source
    logger.info(f"[ROUTER] @{target_agent} → {source} ({decision.provider}/{decision.model}) [{decision.reason}]")
    if source == "local":
        if not router._is_ollama_available():
            logger.info(f"[ROUTER] ⚠️  Ollama no detectado. Modelo local '{decision.model}' no disponible.")
            if router.config.get("local", {}).get("fallback_to_cloud", True):
                logger.info(f"[ROUTER] ⚠️  Fallback a cloud automatico activado.")
            else:
                logger.info(f"[ROUTER] 💡 Instala Ollama: https://ollama.com")
                logger.info(f"[ROUTER] 💡 O usa --force-cloud para modo cloud")
    return source


# ── HITL Guard ─────────────────────────────────────────────────────

def _check_hitl(action: str, agent_role: str, guard) -> bool:
    """Check if an action needs human approval and handle it.

    Returns True if action is approved/safe, False if blocked.
    """
    if guard.mode == "auto_pilot":
        return True
    check = guard.check_action(action, agent_role)
    if check["approved"]:
        return True
    logger.info(f"[HITL] @{agent_role} propone accion que requiere aprobacion:")
    logger.info(f"[HITL]   {action[:200]}")
    return guard.request_approval(action, agent_role)


# ── Watch mode helpers ──────────────────────────────────────────────

def _get_files_to_watch(harness_root: Path) -> dict:
    """Get file modification times for harness/ and .opencode/."""
    snapshots = {}
    watch_dirs = [str(harness_root), str(harness_root.parent / ".opencode")]
    exclude_patterns = ["__pycache__", "harness/db/", ".git/", ".git"]
    for watch_dir in watch_dirs:
        if not os.path.isdir(watch_dir):
            continue
        for root, dirs, files in os.walk(watch_dir):
            dirs[:] = [d for d in dirs if not any(p in os.path.join(root, d) for p in exclude_patterns)]
            for fname in files:
                if not any(fname.endswith(ext) for ext in (".py", ".md", ".yaml", ".yml", ".json")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    snapshots[fpath] = st.st_mtime
                except (FileNotFoundError, OSError):
                    pass
    return snapshots


# ── ANSI helpers ────────────────────────────────────────────────────

_RED = "\033[91m"; _GREEN = "\033[92m"; _YELLOW = "\033[93m"
_CYAN = "\033[96m"; _BOLD = "\033[1m"; _RESET = "\033[0m"

def _ok(msg: str) -> str: return f"{_GREEN}{msg}{_RESET}"
def _warn(msg: str) -> str: return f"{_YELLOW}{msg}{_RESET}"
def _err(msg: str) -> str: return f"{_RED}{msg}{_RESET}"
def _bold(msg: str) -> str: return f"{_BOLD}{msg}{_RESET}"
def _cyan(msg: str) -> str: return f"{_CYAN}{msg}{_RESET}"


def _safe_print(*args, **kwargs) -> None:
    """Print with Unicode fallback: replaces non-encodable chars."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                arg = (arg.replace("\u2014", "--").replace("\u2013", "-")
                       .replace("\u2500", "-").replace("\u2502", "|")
                       .replace("\u2018", "'").replace("\u2019", "'")
                       .replace("\u201c", '"').replace("\u201d", '"')
                       .replace("\u2026", "...").replace("\u00a0", " "))
            safe_args.append(arg)
        print(*safe_args, **kwargs)
