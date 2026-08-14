"""run_commands handlers varios (rag/db/hooks/evolve/schedule/watch)."""
from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

import harness.run_commands as _rc


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
        _rc.logger.info('[Harness] Uso: !evolve mutate @<agent> "<task>"')
        return
    agent_arg = parts[2].lstrip("@")
    task_arg = parts[3]
    agent_path = str(Path(__file__).resolve().parent.parent / ".opencode" / "agents" / f"{agent_arg}.md")
    if not Path(agent_path).exists():
        _rc.logger.info(f"[Harness] Agente '{agent_arg}' no encontrado en {agent_path}")
        return
    evolver = PromptEvolver(vector_store=store)
    _rc.logger.info(f"[Harness] Mutando prompt de @{agent_arg}...")
    mutants = evolver.mutate_prompt(agent_path)
    if not mutants:
        _rc.logger.info("[Harness] No se generaron mutantes.")
        return
    _rc.logger.info(f"[Harness] Mutantes generados ({len(mutants)}):")
    for m in mutants:
        _rc.logger.info(f"  - {m}")
    _rc.logger.info(f"\n[Harness] Evaluando mutantes con tarea: {task_arg[:80]}...")
    scores = evolver.evaluate_mutants(agent_path, mutants, task_arg)
    _rc.logger.info("\n[Harness] Resultados de evaluacion:")
    for label, result in sorted(scores.items(), key=lambda x: -x[1].get("score", 0)):
        _rc.logger.info(
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
            _rc.logger.info(f"\n[Harness] Promoviendo ganador: {best_label}")
            promoted = evolver.promote_winner(winner)
            if promoted:
                _rc.logger.info(f"[Harness] Prompt de @{agent_arg} actualizado exitosamente.")
        else:
            _rc.logger.info("[Harness] No se pudo determinar el ganador.")
    else:
        _rc.logger.info("[Harness] Original conservado (ningun mutante supero el score original).")


def _handle_schedule_add(store, cmd: str) -> None:
    """Handle ``!schedule add <name> --cron \"<cron>\" --task \"<cmd>\"``."""
    import shlex

    from harness.orchestrator.scheduler import Scheduler
    parts = shlex.split(cmd)
    if len(parts) < 5:
        _rc.logger.info('[Harness] Uso: !schedule add <name> --cron "<cron>" --task "<cmd>"')
        _rc.logger.info('[Harness]   O: !schedule add <name> --interval "30m" --task "<cmd>"')
        _rc.logger.info('[Harness]   O: !schedule add <name> --once "ISO" --task "<cmd>"')
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
        _rc.logger.info("[Harness] Error: se requiere --cron/--interval/--once y --task")
        return
    scheduler = Scheduler(vector_store=store)
    job = scheduler.add_job(name=name, trigger=trigger, trigger_value=trigger_value, command=command)
    _rc.logger.info(f"[Harness] Job programado: {job.name} ({job.trigger}: {job.trigger_value})")


def _handle_schedule_list(store) -> None:
    """Handle ``!schedule list``."""
    from harness.orchestrator.scheduler import Scheduler
    scheduler = Scheduler(vector_store=store)
    jobs = scheduler.list_jobs()
    if not jobs:
        _rc.logger.info("[Harness] No hay jobs programados.")
        return
    _rc.logger.info(f"[Harness] Jobs programados ({len(jobs)}):")
    for job in jobs:
        status = "activo" if job.enabled else "inactivo"
        _rc.logger.info(f"  - {job.name}: {job.trigger} = {job.trigger_value} [{status}] ultimo: {job.last_run or 'nunca'}")


# â”€â”€ Model Routing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _apply_model_routing(task: str, target_agent: str, force_cloud: bool = False) -> str:
    """Apply ModelRouter to determine local vs cloud execution.

    Returns the routing source ("local" or "cloud") for logging.
    """
    from harness.model_router.ollama_client import OllamaClient
    from harness.model_router.ollama_tiers import OllamaTierRouter
    from harness.model_router.router import ModelRouter

    router = ModelRouter()
    if force_cloud:
        _rc.logger.info(f"[ROUTER] @{target_agent} → cloud (--force-cloud override)")
        return "cloud"
    decision = router.route(task, target_agent)
    source = decision.source
    _rc.logger.info(
        f"[ROUTER] @{target_agent} → {source} "
        f"({decision.suggested_provider or 'n/a'}/{decision.model}) "
        f"[{decision.model_route.reason}]"
    )
    if source == "local":
        # Delegación local 4-tier por capacidad (fast/quality/embedding/vision).
        # Degrada a cloud si Ollama no está disponible (no crashea).
        client = OllamaClient()
        if client.is_available():
            tiers = OllamaTierRouter(client)
            tier = tiers.tier_for_task(task)
            model = tiers.model_for(tier)
            _rc.logger.info(
                f"[ROUTER] @{target_agent} → local tier={tier.value} model={model} "
                f"(keep_alive {tiers.model_for(tier)})"
            )
            return "local"
        _rc.logger.info("[ROUTER] ⚠️  Ollama no detectado. Modelo local no disponible.")
        if router.config.get("local", {}).get("fallback_to_cloud", True):
            _rc.logger.info("[ROUTER] ⚠️  Fallback a cloud automatico activado.")
        else:
            _rc.logger.info("[ROUTER] 💡 Instala Ollama: https://ollama.com")
            _rc.logger.info("[ROUTER] 💡 O usa --force-cloud para modo cloud")
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
    _rc.logger.info(f"[HITL] @{agent_role} propone accion que requiere aprobacion:")
    _rc.logger.info(f"[HITL]   {action[:200]}")
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

    from harness.cli_common import get_project_root

    _rc.logger.info("[Harness] Watch mode activado - monitoreando:")
    _rc.logger.info("  - %s", harness_root)
    _rc.logger.info("  - %s", harness_root.parent / ".opencode")
    _rc.logger.info("  Excluyendo: harness/db/, __pycache__/, .git/")
    _rc.logger.info("")

    eoi_script = harness_root / "scripts" / "end_of_iteration.py"
    if not eoi_script.exists():
        _rc._safe_print(f"    {_rc._err('[ERROR]')} No se encontro: %s", eoi_script)
        return

    last_snapshot = _rc._get_files_to_watch(harness_root)
    idle_since: float | None = None
    debounce_seconds = 3.0

    _rc._safe_print(f"  {_rc._cyan('[WATCH]')} Waiting for changes...")
    _rc._safe_print("  Press Ctrl+C to stop.")
    _rc._safe_print()

    try:
        while True:
            _time.sleep(2)
            now = _time.time()

            new_snapshot = _rc._get_files_to_watch(harness_root)
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

            timestamp = _datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            for f in changed_files[:5]:
                rel = str(Path(f).relative_to(get_project_root()))
                _rc._safe_print(f"  [{timestamp}] change detected: {rel}")
            if len(changed_files) > 5:
                _rc._safe_print(f"  [{timestamp}] ... and {len(changed_files) - 5} more")

            _rc._safe_print(f"  [{timestamp}] Running check...")
            try:
                import subprocess as _subprocess
                result = _subprocess.run(
                    [_rc.sys.executable, str(eoi_script), "--watch"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(harness_root.parent), check=False,
                )
                for line in result.stdout.splitlines():
                    _rc._safe_print(f"  {line}")
                if result.stderr.strip():
                    for line in result.stderr.splitlines():
                        _rc._safe_print(f"  {_rc._warn('[STDERR]')} {line}")
            except _subprocess.TimeoutExpired:
                _rc._safe_print(f"  {_rc._warn('[WARN]')} Pipeline timeout (>30s)")
            except Exception as exc:  # noqa: BLE001
                _rc._safe_print(f"  {_rc._err('[ERROR]')} Pipeline failed: {exc}")

            last_snapshot = new_snapshot.copy()
            idle_since = None
            _rc._safe_print(f"  {_rc._cyan('[WATCH]')} Waiting for changes...")
            _rc.logger.info("")

    except KeyboardInterrupt:
        _rc._safe_print(f"\n  {_rc._cyan('[WATCH]')} Watch mode detenido.")


# â”€â”€ Hermes commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _handle_hermes(cmd: str) -> None:
    """Handle !hermes sync and !hermes stats."""
    from harness.memory_rag.hermes_bridge import HermesBridge

    sub = cmd[len("!hermes"):].strip()
    if sub == "sync":
        bridge = HermesBridge()
        result = bridge.sync_all()
        _rc.logger.info("[Hermes] Sync complete: %s", result)
    elif sub == "stats":
        bridge = HermesBridge()
        stats = bridge.get_stats()
        _rc.logger.info("[Hermes] Bridge stats: %s", stats)
    elif sub in ("", "help"):
        _rc.logger.info("[Hermes] Commands:")
        _rc.logger.info("  !hermes sync    - Bidirectional sync Swarmind <-> shared_memory")
        _rc.logger.info("  !hermes stats   - Show bridge statistics")
    else:
        _rc.logger.info("[Hermes] Unknown subcommand: '%s'. Try '!hermes sync' or '!hermes stats'.", sub)


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
        _rc.logger.info("[Harness] Guardrails no disponible (opencode.core.guardrails no importado)")
        _rc.logger.info("[Harness] El sistema opera SIN proteccion de guardrails.")
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
        _rc.logger.info("[Harness] Guardrails BLOCKED en fase %s: %s",
                     blocked_at, summary.get("failed_rules", []))
        _rc.sys.exit(1)
    _rc.logger.info("[Harness] Guardrails OK (%s/%s checks pasados)",
                 result['summary']['passed'], result['summary']['total_checks'])


# â”€â”€ ANSI helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

__all__ = [
    "_apply_model_routing",
    "_check_hitl",
    "_get_files_to_watch",
    "_handle_evolve_mutate",
    "_handle_hermes",
    "_handle_hooks_status",
    "_handle_schedule_add",
    "_handle_schedule_list",
    "_handle_watch_mode",
    "_run_guardrails",
]

__all__ = [
    "_apply_model_routing",
    "_check_hitl",
    "_get_files_to_watch",
    "_handle_evolve_mutate",
    "_handle_hermes",
    "_handle_hooks_status",
    "_handle_schedule_add",
    "_handle_schedule_list",
    "_handle_watch_mode",
    "_run_guardrails",
]
