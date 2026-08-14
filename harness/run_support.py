"""Helpers de harness/run.py extraidos para cumplir la regla AGR.

Submodulo de :mod:`harness.run` con funciones auxiliares que NO dependen
de las globales del modulo run (``LanceVectorStore``, ``HARNESS_ROOT``,
``_safe_print``, etc.) y por tanto pueden vivir fuera sin romper los
patches de los tests (``patch("harness.run.*")``).

Extraido de forma mecanica desde ``run.py`` (regla AGR: archivos < 500
lineas). Los cuerpos son identicos al original; solo cambia la ubicacion
fisica del codigo.

Contiene:
    - ``_USAGE_LINES``: lineas de ayuda del CLI (data de ``_show_usage``).
    - ``_parse_args``: parseo de argumentos CLI (usa solo ``sys.argv``).
    - ``_handle_gateway_mode``: modo gateway (imports lazy).
    - ``_dispatch_task``: despacho via AgentDispatcher (imports lazy).
    - ``_resolve_hitl_mode``: determinacion del modo HITL (pura).
    - ``_start_sandbox_if_needed``: SandboxLoop para agentes builder.
"""

from __future__ import annotations

import sys
from typing import Any

from harness.cli_common import setup_logging

logger = setup_logging()


# ---------------------------------------------------------------------------
# Datos de ayuda del CLI (extraidos de _show_usage)
# ---------------------------------------------------------------------------

_USAGE_LINES: tuple[str, ...] = (
    "Uso: python harness/run.py \"<descripcion de la tarea>\"",
    "Ej: python harness/run.py \"@software-engineer: Implementa endpoint de API\"",
    "",
    "Flags:",
    "  --daemon                    Inicia scheduler en background",
    "  --watch                     Modo watch (monitorea cambios)",
    "  --gateway <type>            Modo gateway (cli, slack, telegram)",
    "  --force-cloud               Override: todas las tareas a cloud API",
    "  --auto-pilot                Desactiva HITL (entornos de confianza)",
    "  --hitl-sensitive            HITL solo para acciones criticas",
    "  (dispatch paralelo por defecto, no requiere flags)",
    "  --help                      Muestra esta ayuda",
    "",
    "Roles universales (auto-deteccion SIN @):",
    "  @coordinator   - Entry point, analiza y delega (default)",
    "  @builder       - Implementacion: Rust, Go, Python, Web, Mobile, Trading, Infra",
    "  @scientist     - Investigacion: papers, AI/ML, arquitectura, patrones",
    "  @guardian      - Calidad: testing, seguridad, riesgo, docs, operaciones",
    "  @evolve        - Auto-mejora del sistema",
    "  !evolve mutate @<a> \"<t>\"   Evolucion de prompts",
    "  !schedule add <n> ...       Programar job",
    "  !schedule list              Listar jobs",
    "  !db migrate                 Migrar BD desde import/",
    "  !db migrate --path <ruta>   Migrar BD especifica",
    "  !db list-imports            Listar BDs disponibles",
    "  !db stats                   Estadisticas de BD activa",
    "  !db rollback <backup>       Restaurar desde backup",
    "  !iteration end              Pipeline fin de iteracion",
    "  !iteration end --dry-run    Simulacion del pipeline",
    "  !iteration end --skip-bugs  Salta bug hunting",
    "  !iteration end --skip-sec   Salta security review",
    "  !iteration end --skip-docs  Salta docs update",
    "  !iteration end --quick      Modo rapido (bugs+tokens, <2s)",
    "  !iteration end --auto       Modo automatico (full pipeline+commit)",
    "  !iteration quick            Modo rapido directo",
    "  !iteration auto             Modo automatico directo",
    "  !iteration report           Muestra ultimo reporte",
    "  !iteration history          Muestra timeline (ultimas 10)",
    "  !iteration history --all    Muestra todas las iteraciones",
    "  !iteration diff             Muestra detalle ultima iteracion",
    "  !iteration diff --last      Muestra detalle ultima iteracion",
    "  !iteration diff --n <num>   Muestra detalle iteracion #num",
    "  !hooks install              Instala pre-commit hook",
    "  !hooks uninstall            Desinstala pre-commit hook",
    "  !hooks status               Muestra estado del hook",
    "  !rag ingest                 Ingiere codigo fuente como RAG",
    "  !rag ingest --dir <path>    Ingiere solo un directorio",
    "  !rag stats                  Estadisticas de la BD RAG",
    "  !hermes sync                Sync bidireccional Swarmind <-> shared_memory",
    "  !hermes stats               Estadisticas del puente Hermes",
    "",
)


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
            f"Sesión: `{orch_result.session_id}`\n"
            f"Routing: `{routing_source}`\n\n"
            f"Plan de ejecución con {len(orch_result.plan.subtasks)} subtareas.\n"
            f"Nivel actual: {len(orch_result.current_level)} subtarea(s) lista(s).\n\n"
            f"El SandboxLoop esta listo para ejecutar el bucle autonomo.\n"
        ),
        message_type="notification",
        task_id=task_id,
    )
    logger.info("[Harness] SandboxLoop listo en canal #swe-sandbox")
