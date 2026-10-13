"""run_commands handlers varios (rag/db/hooks/evolve/schedule/watch)."""
from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

import harness.run_commands as _rc


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


# ── Model Routing ────────────────────────────────────────────────────

def _local_backend_available() -> bool:
    """Consulta best-effort si el backend local responde (no lo arranca).

    Returns:
        True si llama.cpp/llama-swap responde; False si esta caido o si el
        chequeo falla (nunca propaga: el routing degrada a cloud).
    """
    try:
        from harness.model_router.llama_swap_manager import LlamaSwapManager
        return bool(LlamaSwapManager().is_up())
    except Exception as exc:  # noqa: BLE001 - best-effort, no rompe el routing
        _rc.logger.warning(
            "[ROUTER] WHAT=no se pudo consultar el backend local; "
            "WHY=%s; WHERE=_local_backend_available", exc,
        )
        return False


def _cloud_skip_reason(policy, force_cloud: bool, backend_available: bool) -> str:
    """Motivo legible de por que se paga cloud (orden de precedencia).

    Args:
        policy: LocalFirstPolicy efectiva.
        force_cloud: True si el usuario forzo cloud.
        backend_available: True si el backend local responde.

    Returns:
        Motivo WHAT/WHY para el log de routing.
    """
    if force_cloud:
        return "--force-cloud override"
    if not policy.enabled:
        return "politica local-first desactivada"
    if not backend_available:
        return "llama.cpp no disponible (backend local caido)"
    return "sin destino local"


def _route_local_tier(task: str, target_agent: str, router) -> str:
    """Resuelve el tier local; frontier-only paga cloud como oraculo.

    Args:
        task: Descripcion de la tarea.
        target_agent: Agente destino (para logs).
        router: ModelRouter (config de fallback a cloud).

    Returns:
        "local" si hay tier; "cloud" si la tarea es frontier-only.
    """
    from harness.model_router.ollama_client import OllamaClient
    from harness.model_router.ollama_tiers import OllamaTierRouter

    client = OllamaClient()
    if client.is_available():
        # Delegacion local 5-tier por capacidad (fast/quality/coding/
        # embedding/vision). Tareas FRONTIER_ONLY (diseno/arquitectura/
        # planning/sintesis/razonamiento/audit) NO se delegan: tier None.
        tiers = OllamaTierRouter(client)
        tier = tiers.tier_for_task(task)
        if tier is None:
            _rc.logger.info(
                f"[ROUTER] @{target_agent} → oraculo cloud (frontier-only: "
                "diseno/planning/sintesis/razonamiento/audit no se delegan; "
                "cloud de minima intervencion, TKN justificado)"
            )
            return "cloud"
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
    return "local"


def _apply_model_routing(task: str, target_agent: str, force_cloud: bool = False) -> str:
    """Aplica la politica local-first y decide local vs cloud (cloud oraculo).

    Args:
        task: Descripcion de la tarea.
        target_agent: Agente destino.
        force_cloud: True = paga cloud sin consultar el backend local.

    Returns:
        "local" o "cloud" (fuente usada para logging/telemetria).
    """
    from harness.model_router.local_first import LocalFirstPolicy
    from harness.model_router.router import ModelRouter

    policy = LocalFirstPolicy.from_env()
    backend_available = not force_cloud and _local_backend_available()
    if not policy.should_use_local(
        backend_available=backend_available, force_cloud=force_cloud
    ):
        reason = _cloud_skip_reason(policy, force_cloud, backend_available)
        _rc.logger.info(f"[ROUTER] @{target_agent} → cloud ({reason})")
        return "cloud"

    router = ModelRouter()
    decision = router.route(task, target_agent)
    source = decision.source
    _rc.logger.info(
        f"[ROUTER] @{target_agent} → {source} "
        f"({decision.suggested_provider or 'n/a'}/{decision.model}) "
        f"[{decision.model_route.reason}]"
    )
    if source == "local":
        return _route_local_tier(task, target_agent, router)
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
    _rc.logger.info(f"[HITL] @{agent_role} propone accion que requiere aprobacion:")
    _rc.logger.info(f"[HITL]   {action[:200]}")
    return guard.request_approval(action, agent_role)


# ── Watch mode helpers ──────────────────────────────────────────────

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


# ── Watch-mode handler ──────────────────────────────────────────────


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


# ── Guardrails helper (fail-closed + engine local) ─────────────────
#
# Diseno (EDV, Forge 2026): los guardrails cierran el gap de reliability;
# fallar ABIERTO (continuar sin proteccion) es un riesgo inaceptable.
# Cadena de resolucion:
#   1. Engine EXTERNO ``opencode.core.guardrails`` (si ``run_full_pipeline``).
#   2. Engine LOCAL ``harness.guardrails`` (fallback cableado, no mas bypass).
#   3. Ninguno -> FAIL-CLOSED: se bloquea la ejecucion (constante
#      ``FAIL_CLOSED_ON_NO_ENGINE``). El unico camino de degradacion es
#      explicito y consciente (bandera a False).

#: Si es True (default), bloquear cuando NINGUN engine de guardrails carga.
FAIL_CLOSED_ON_NO_ENGINE: bool = True

#: Marca de registro unico de los hooks builtin (idempotencia runtime).
_BUILTIN_HOOKS_REGISTERED: bool = False


def _ensure_builtin_hooks_registered() -> int:
    """Registra los hooks builtin (audit_logger, etc.) una sola vez.

    Idempotente: la primera invocacion instala los hooks; las siguientes
    retornan 0 sin re-registrar. Activa ``audit_logger`` en runtime.

    Returns:
        Numero de hooks nuevos registrados (0 si ya estaban registrados).
    """
    global _BUILTIN_HOOKS_REGISTERED
    if _BUILTIN_HOOKS_REGISTERED:
        return 0
    from harness.hooks.builtin_hooks import register_builtin_hooks
    try:
        count = register_builtin_hooks()
    except Exception as exc:  # noqa: BLE001 - no rompe el runtime por hooks
        _rc.logger.warning(
            "[HOOKS] WHAT=no se pudieron registrar los hooks builtin; "
            "WHY=%s; WHERE=_ensure_builtin_hooks_registered", exc,
        )
        return 0
    _BUILTIN_HOOKS_REGISTERED = True
    return count

def _get_local_guardrail_engine() -> Any:
    """Construye el engine LOCAL de guardrails (``harness.guardrails``).

    Returns:
        Instancia de ``GuardrailEngine``.

    Raises:
        Exception: Si el engine local no puede importarse/construirse.
    """
    from harness.guardrails import GuardrailEngine
    return GuardrailEngine()


def _run_local_guardrail_pipeline(
    user_message: str,
    generated_code: str,
    context: dict,
    engine: Any = None,
) -> dict:
    """Adapta el engine LOCAL al contrato de ``run_full_pipeline``.

    Ejecuta las capas INPUT (y CONTENT si hay codigo) del ``GuardrailEngine``
    local y normaliza el veredicto al dict ``{allowed, blocked_at, summary}``
    que consume ``_run_guardrails``.

    Args:
        user_message: Prompt/tarea del usuario.
        generated_code: Codigo generado (puede ser "").
        context: Contexto de ejecucion (agent_role, etc.).
        engine: Engine inyectable (None = construye el local).

    Returns:
        Dict compatible con ``opencode.core.guardrails.run_full_pipeline``.
    """
    if engine is None:
        engine = _get_local_guardrail_engine()

    layers: list[tuple[str, Any]] = [("input", engine.check_input(user_message))]
    if generated_code:
        layers.append(("content", engine.check_content(generated_code)))

    blocked_at: str | None = None
    failed_rules: list[str] = []
    passed: int = 0
    for layer_name, result in layers:
        violations = tuple(getattr(result, "violations", ()) or ())
        verdict = getattr(result, "verdict", None)
        if verdict is not None and getattr(verdict, "value", None) == "block":
            if blocked_at is None:
                blocked_at = layer_name
        else:
            passed += 1
        failed_rules.extend(violations)

    return {
        "allowed": blocked_at is None,
        "blocked_at": blocked_at,
        "summary": {
            "passed": passed,
            "total_checks": len(layers),
            "failed_rules": failed_rules,
        },
    }


def _build_local_guardrail_pipeline() -> Any:
    """Construye el pipeline de guardrails LOCAL (o None si no esta disponible).

    Returns:
        Callable ``(user_message, generated_code, context) -> dict`` que usa
        el engine local, o None si ``harness.guardrails`` no carga.
    """
    try:
        engine = _get_local_guardrail_engine()
    except Exception as exc:  # noqa: BLE001 - fallback a fail-closed
        _rc.logger.warning(
            "[GUARDRAILS] WHAT=engine local harness.guardrails no disponible; "
            "WHY=%s; WHERE=_build_local_guardrail_pipeline", exc,
        )
        return None

    def _pipeline(user_message: str, generated_code: str, context: dict) -> dict:
        return _run_local_guardrail_pipeline(
            user_message, generated_code, context, engine=engine,
        )

    return _pipeline


def _fail_closed_no_engine(task: str, target_agent: str) -> None:
    """Aplica fail-closed cuando NINGUN engine de guardrails esta disponible.

    Args:
        task: Tarea solicitada (referencia para el log).
        target_agent: Agente destino (referencia para el log).
    """
    if FAIL_CLOSED_ON_NO_ENGINE:
        _rc.logger.error(
            "[GUARDRAILS] FAIL-CLOSED: WHAT=ni opencode.core.guardrails ni "
            "harness.guardrails disponibles; WHY=no se puede validar seguridad "
            "y fallar abierto es inaceptable; WHERE=_run_guardrails. "
            "BLOQUEANDO tarea de @%s.", target_agent,
        )
        _rc.sys.exit(1)
    _rc.logger.warning(
        "[GUARDRAILS] WHAT=sin engine de guardrails; "
        "WHY=FAIL_CLOSED_ON_NO_ENGINE=False (degradacion consciente); "
        "WHERE=_run_guardrails. Resultado marcado como INSEGURO."
    )


def _run_guardrails(task: str, target_agent: str, ctx: Any,
                     routing_source: str,
                     run_full_pipeline: Any = None) -> None:
    """Ejecuta guardrails de seguridad (fail-closed).

    Resuelve el pipeline en cascada: engine externo (``opencode.core.guardrails``)
    -> engine LOCAL (``harness.guardrails``) -> fail-closed si AMBOS faltan.

    Args:
        task: Descripcion de la tarea.
        target_agent: Agente destino.
        ctx: Contexto RAG de la tarea.
        routing_source: Fuente de routing ("local"/"cloud").
        run_full_pipeline: Pipeline externo inyectable (None = ausente).

    Raises:
        SystemExit: Si los guardrails bloquean o si no hay engine (fail-closed).
    """
    _ensure_builtin_hooks_registered()

    pipeline = run_full_pipeline
    if pipeline is None:
        pipeline = _build_local_guardrail_pipeline()
        if pipeline is not None:
            _rc.logger.info(
                "[Harness] Guardrails: opencode.core.guardrails ausente; "
                "usando engine LOCAL harness.guardrails (fail-closed)."
            )
    if pipeline is None:
        _fail_closed_no_engine(task, target_agent)
        return

    pre_context = {
        "agent_role": target_agent,
        "task_description": task,
        "rag_chunks": len(ctx.relevant_docs) if hasattr(ctx, 'relevant_docs') else 0,
        "token_budget": ctx.metadata.get("total_tokens_used", 0) if hasattr(ctx, 'metadata') else 0,
        "routing_source": routing_source,
    }
    result = pipeline(task, "", pre_context)
    if not result.get("allowed", True):
        blocked_at = result.get("blocked_at", "unknown")
        summary = result.get("summary", {})
        _rc.logger.info("[Harness] Guardrails BLOCKED en fase %s: %s",
                     blocked_at, summary.get("failed_rules", []))
        _rc.sys.exit(1)
    _rc.logger.info("[Harness] Guardrails OK (%s/%s checks pasados)",
                 result['summary']['passed'], result['summary']['total_checks'])


# ── ANSI helpers ────────────────────────────────────────────────────

__all__ = [
    "FAIL_CLOSED_ON_NO_ENGINE",
    "_apply_model_routing",
    "_build_local_guardrail_pipeline",
    "_check_hitl",
    "_ensure_builtin_hooks_registered",
    "_fail_closed_no_engine",
    "_get_files_to_watch",
    "_get_local_guardrail_engine",
    "_handle_evolve_mutate",
    "_handle_hooks_status",
    "_handle_schedule_add",
    "_handle_schedule_list",
    "_handle_watch_mode",
    "_run_guardrails",
    "_run_local_guardrail_pipeline",
]
