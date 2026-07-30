"""
Command handlers for harness/run.py â€” extracted for file size compliance.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# â”€â”€ RAG Commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _handle_rag_ingest(store, cmd: str) -> None:
    """Handle ``!rag ingest [--dir <path>]``."""
    from harness.memory_rag.doc_ingester import ingest_project_directory

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
    except Exception as e:  # noqa: BLE001
        logger.error("[RAG] \u274c Error: %s", e)


def _handle_rag_stats(store) -> None:
    """Handle ``!rag stats`` â€” muestra estadisticas de la BD RAG."""
    colls = store.list_collections()
    logger.info("")
    logger.info("[RAG] Colecciones disponibles: %s", colls)
    if "rag_chunks" in colls:
        try:
            stats = store.get_collection_stats("rag_chunks")
            logger.info("[RAG] Coleccion 'rag_chunks':")
            logger.info("  Items: %d", stats.get("item_count", 0))
            logger.info("  Ultima actualizacion: %s", stats.get("last_updated", "N/A"))
        except Exception as exc:  # noqa: BLE001
            logger.info("[RAG] Coleccion 'rag_chunks' existe (error al obtener stats: %s)", exc)
            logger.info("  (Esto es normal si la BD esta vacia o es una version reciente de LanceDB)")
    else:
        logger.info("[RAG] Coleccion 'rag_chunks' no existe. Ejecuta '!rag ingest'.")
    logger.info("")


# â”€â”€ DB Commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        logger.info(f"[DB] SKIP: {s}")
    for e in result.get("errors", []):
        logger.info(f"[DB] ERROR: {e}")
    if result.get("backup_path"):
        logger.info("[DB] Backup: {}".format(result["backup_path"]))


def _handle_db_list_imports() -> None:
    """Handle ``!db list-imports``."""
    from harness.db.migrate_db import DBMigrator
    migrator = DBMigrator()
    imports = migrator.scan_imports()
    if imports:
        logger.info(f"\n[DB] Bases detectadas ({len(imports)}):")
        for imp in imports:
            colls = ", ".join(imp["collections"])
            logger.info("  * {}: {} ({})".format(imp["name"], colls, imp["estimated_size_human"]))
    else:
        logger.info("[DB] No se detectaron bases de datos en import/")


def _handle_db_stats(store: Any) -> None:
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
        logger.info(f"[DB] Base restaurada desde: {backup_path}")
    else:
        logger.info(f"[DB] Error al restaurar desde: {backup_path}")


# â”€â”€ Iteration End â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _parse_iteration_flags(cmd: str) -> dict:
    """Parse flags from a !iteration end command."""
    flags = {
        "skip_bugs": False, "skip_sec": False, "skip_docs": False,
        "dry_run": False, "quick": False, "auto": False,
    }
    parts = cmd.split()
    if "--dry-run" in parts:
        flags["dry_run"] = True
    if "--skip-bugs" in parts:
        flags["skip_bugs"] = True
    if "--skip-sec" in parts:
        flags["skip_sec"] = True
    if "--skip-docs" in parts:
        flags["skip_docs"] = True
    if "--quick" in parts:
        flags["quick"] = True
    if "--auto" in parts:
        flags["auto"] = True
    return flags


def _handle_iteration_end(cmd: str, harness_root) -> None:
    """Handle ``!iteration end [--dry-run] [--skip-bugs] [--skip-sec] [--skip-docs] [--quick] [--auto]``."""
    flags = _parse_iteration_flags(cmd)

    # Redirect to quick/auto mode if flagged
    if flags["quick"]:
        _handle_iteration_quick(cmd, harness_root)
        return
    if flags["auto"]:
        _handle_iteration_auto(cmd, harness_root)
        return

    logger.info("[Harness] Iniciando pipeline de fin de iteracion...")
    if flags["dry_run"]:
        logger.info("[Harness] Modo DRY-RUN â€” no se modificaran archivos")
    if any([flags["skip_bugs"], flags["skip_sec"], flags["skip_docs"]]):
        skips = []
        if flags["skip_bugs"]:
            skips.append("bugs")
        if flags["skip_sec"]:
            skips.append("security")
        if flags["skip_docs"]:
            skips.append("docs")
        logger.info(f"[Harness] Fases saltadas: {', '.join(skips)}")
    sys.path.insert(1, str(harness_root.parent))
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline(
        skip_bugs=flags["skip_bugs"], skip_security=flags["skip_sec"],
        skip_docs=flags["skip_docs"], dry_run=flags["dry_run"],
    )


def _handle_iteration_quick(cmd: str = "", harness_root=None) -> None:
    """Handle ``!iteration quick`` or ``!iteration end --quick``.

    Modo rÃ¡pido: solo bugs + tokens, salta security y docs.
    """
    sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
    from harness.scripts.end_of_iteration import run_quick_pipeline
    run_quick_pipeline()


def _handle_iteration_auto(cmd: str = "", harness_root=None) -> None:
    """Handle ``!iteration auto`` or ``!iteration end --auto``.

    Modo automÃ¡tico: pipeline completo + commit si no hay criticals.
    """
    sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
    from harness.scripts.end_of_iteration import run_auto_pipeline
    run_auto_pipeline()


def _handle_iteration_report() -> None:
    """Handle ``!iteration report`` â€” shows the last saved iteration report."""
    from harness.scripts.end_of_iteration import print_last_report
    print_last_report()


def _handle_iteration_history(cmd: str) -> None:
    """Handle ``!iteration history [--all]`` â€” muestra timeline de iteraciones."""
    from harness.scripts.end_of_iteration import show_iteration_history
    parts = cmd.split()
    if "--all" in parts:
        show_iteration_history(limit=0)  # 0 = sin lÃ­mite
    else:
        show_iteration_history(limit=10)


def _handle_iteration_diff(cmd: str) -> None:
    """Handle ``!iteration diff [--last] [--n <num>]`` â€” muestra detalle de iteraciÃ³n.

    Ejemplos:
        !iteration diff            â†’ Ãºltima iteraciÃ³n
        !iteration diff --last     â†’ Ãºltima iteraciÃ³n
        !iteration diff --n 2      â†’ penÃºltima iteraciÃ³n
        !iteration diff --n 3      â†’ antepenÃºltima iteraciÃ³n
    """
    from harness.scripts.end_of_iteration import show_iteration_diff
    parts = cmd.split()

    n = 1  # default: Ãºltima
    if "--n" in parts:
        idx = parts.index("--n")
        if idx + 1 < len(parts):
            try:
                n = max(1, int(parts[idx + 1]))
            except (ValueError, IndexError):
                n = 1
    # --last tambiÃ©n es 1 (default)
    show_iteration_diff(n=n)


# â”€â”€ Hooks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _handle_hooks_install() -> None:
    """Handle ``!hooks install`` â€” installs the pre-commit hook."""
    from harness.scripts.install_hooks import install_hook
    logger.info("[Harness] Instalando hook pre-commit...")
    install_hook()


def _handle_hooks_uninstall() -> None:
    """Handle ``!hooks uninstall`` â€” uninstalls the pre-commit hook."""
    from harness.scripts.install_hooks import uninstall_hook
    logger.info("[Harness] Desinstalando hook pre-commit...")
    uninstall_hook()


def _handle_hooks_status() -> None:
    """Handle ``!hooks status`` â€” shows hook installation status."""
    from harness.scripts.install_hooks import show_status
    show_status()


# â”€â”€ Evolve â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    agent_path = str(Path(__file__).resolve().parent.parent / ".opencode" / "agents" / f"{agent_arg}.md")
    if not Path(agent_path).exists():
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
        logger.info("[Harness] Original conservado (ningun mutante supero el score original).")


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


# â”€â”€ Model Routing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _apply_model_routing(task: str, target_agent: str, force_cloud: bool = False) -> str:
    """Apply ModelRouter to determine local vs cloud execution.

    Returns the routing source ("local" or "cloud") for logging.
    """
    from harness.model_router.router import ModelRouter
    router = ModelRouter()
    if force_cloud:
        logger.info(f"[ROUTER] @{target_agent} â†’ cloud (--force-cloud override)")
        return "cloud"
    decision = router.route(task, target_agent)
    source = decision.source
    logger.info(f"[ROUTER] @{target_agent} â†’ {source} ({decision.provider}/{decision.model}) [{decision.reason}]")
    if source == "local" and not router._is_ollama_available():
        logger.info(f"[ROUTER] âš ï¸  Ollama no detectado. Modelo local '{decision.model}' no disponible.")
        if router.config.get("local", {}).get("fallback_to_cloud", True):
            logger.info("[ROUTER] âš ï¸  Fallback a cloud automatico activado.")
        else:
            logger.info("[ROUTER] ðŸ’¡ Instala Ollama: https://ollama.com")
            logger.info("[ROUTER] ðŸ’¡ O usa --force-cloud para modo cloud")
    return source


# â”€â”€ HITL Guard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Watch mode helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_files_to_watch(harness_root: Path) -> dict:
    """Get file modification times for harness/ and .opencode/."""
    snapshots = {}
    watch_dirs = [harness_root, harness_root.parent / ".opencode"]
    exclude_patterns = ["__pycache__", "harness/db/", ".git/", ".git"]
    for watch_dir in watch_dirs:
        if not watch_dir.is_dir():
            continue
        for fpath in watch_dir.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix not in (".py", ".md", ".yaml", ".yml", ".json"):
                continue
            # Check exclude patterns
            rel = fpath.relative_to(watch_dir)
            if any(p in str(rel) for p in exclude_patterns):
                continue
            try:
                st = fpath.stat()
                snapshots[str(fpath)] = st.st_mtime
            except (FileNotFoundError, OSError):
                pass
    return snapshots


# â”€â”€ Watch-mode handler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _handle_watch_mode(harness_root: Path) -> None:
    """Handle --watch flag - monitors harness/ and .opencode/ for changes."""
    import time as _time
    from datetime import datetime as _datetime
    from datetime import timezone as _timezone

    from harness.cli_common import get_project_root

    logger.info("[Harness] Watch mode activado - monitoreando:")
    logger.info("  - %s", harness_root)
    logger.info("  - %s", harness_root.parent / ".opencode")
    logger.info("  Excluyendo: harness/db/, __pycache__/, .git/")
    logger.info("")

    eoi_script = harness_root / "scripts" / "end_of_iteration.py"
    if not eoi_script.exists():
        _safe_print(f"    {_err('[ERROR]')} No se encontro: %s", eoi_script)
        return

    last_snapshot = _get_files_to_watch(harness_root)
    idle_since: float | None = None
    debounce_seconds = 3.0

    _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
    _safe_print("  Press Ctrl+C to stop.")
    _safe_print()

    try:
        while True:
            _time.sleep(2)
            now = _time.time()

            new_snapshot = _get_files_to_watch(harness_root)
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

            timestamp = _datetime.now(_timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for f in changed_files[:5]:
                rel = str(Path(f).relative_to(get_project_root()))
                _safe_print(f"  [{timestamp}] change detected: {rel}")
            if len(changed_files) > 5:
                _safe_print(f"  [{timestamp}] ... and {len(changed_files) - 5} more")

            _safe_print(f"  [{timestamp}] Running check...")
            try:
                import subprocess as _subprocess
                result = _subprocess.run(
                    [sys.executable, str(eoi_script), "--watch"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(harness_root.parent), check=False,
                )
                for line in result.stdout.splitlines():
                    _safe_print(f"  {line}")
                if result.stderr.strip():
                    for line in result.stderr.splitlines():
                        _safe_print(f"  {_warn('[STDERR]')} {line}")
            except _subprocess.TimeoutExpired:
                _safe_print(f"  {_warn('[WARN]')} Pipeline timeout (>30s)")
            except Exception as exc:  # noqa: BLE001
                _safe_print(f"  {_err('[ERROR]')} Pipeline failed: {exc}")

            last_snapshot = new_snapshot.copy()
            idle_since = None
            _safe_print(f"  {_cyan('[WATCH]')} Waiting for changes...")
            logger.info("")

    except KeyboardInterrupt:
        _safe_print(f"\n  {_cyan('[WATCH]')} Watch mode detenido.")


# â”€â”€ Hermes commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _handle_hermes(cmd: str) -> None:
    """Handle !hermes sync and !hermes stats."""
    from harness.memory_rag.hermes_bridge import HermesBridge

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
        logger.info("  !hermes sync    - Bidirectional sync Swarmind <-> shared_memory")
        logger.info("  !hermes stats   - Show bridge statistics")
    else:
        logger.info("[Hermes] Unknown subcommand: '%s'. Try '!hermes sync' or '!hermes stats'.", sub)


# â”€â”€ Guardrails helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _run_guardrails(task: str, target_agent: str, ctx: Any,
                     routing_source: str,
                     run_full_pipeline: Any = None) -> None:
    """
    Ejecuta guardrails de seguridad.
    
    Si run_full_pipeline no estÃ¡ disponible, emite WARNING pero continÃºa
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


# â”€â”€ ANSI helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
