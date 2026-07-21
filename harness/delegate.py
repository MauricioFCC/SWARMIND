#!/usr/bin/env python3
"""

logger = logging.getLogger(__name__)
Delegate — Entry point simplificado para el harness multi-agente.

Uso:
    python harness/delegate.py "haz X"                          → detecta rol automaticamente
    python harness/delegate.py "@software-engineer: crea API"   → delegacion explicita
    python harness/delegate.py --list                           → lista roles disponibles
    python harness/delegate.py --interactive                    → modo chat

REFACTOR: Elimina ~150 líneas de registros duplicados e intent mapping.
Ahora usa agent_discovery (descubrimiento recursivo desde .opencode/agents/*.md)
y cli_common (funcionalidad compartida con run.py).
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Optional, Tuple

# Importar funcionalidad compartida
from harness.cli_common import (
    get_harness_root,
    get_project_root,
    setup_logging,
)

# Importar descubrimiento recursivo de agentes
# (reemplaza AGENTS list y _INTENT_AGENTS hardcodeados)
from harness.orchestrator.agent_discovery import (
    build_intent_map,
    discover_agents_recursive,
)
from harness.orchestrator.agent_discovery import (
    resolve_agent_name as discovery_resolve_agent,
)

logger = setup_logging()
HARNESS_ROOT = get_harness_root()

# Asegurar que la raíz del proyecto está en sys.path
if str(get_project_root()) not in sys.path:
    sys.path.insert(1, str(get_project_root()))

# Cache de agentes descubiertos (se carga una vez)
_AGENTS_CACHE = None


def _get_agents() -> list[dict]:
    """Retorna agentes descubiertos, con cache."""
    global _AGENTS_CACHE
    if _AGENTS_CACHE is None:
        _AGENTS_CACHE = discover_agents_recursive()
    return _AGENTS_CACHE


def _get_agent_list() -> List[Tuple[str, str, str]]:
    """
    Construye lista de (nombre, descripcion, alias) desde agentes descubiertos.
    Reemplaza la lista AGETS hardcodeada de ~30 líneas.
    """
    agents = _get_agents()
    result: List[Tuple[str, str, str]] = []
    for name, info in sorted(agents.items()):
        aliases = info.get("aliases", [])
        alias_str = f"@{aliases[0]}" if aliases else ""
        result.append((name, info.get("description", ""), alias_str))
    return result


def _detect_role(task: str) -> Optional[str]:
    """Detecta el mejor rol para una tarea usando intent matching.

    Reemplaza _INTENT_AGENTS hardcodeado (~40 líneas) con el mapa
    construido dinámicamente desde los triggers de cada agente.

    Args:
        task: Descripción de la tarea

    Returns:
        Nombre del agente o None si no se puede detectar.
    """
    # Intentar usar DelegationEngine primero (más completo, incluye Router v2)
    try:
        from harness.orchestrator.delegation_engine import DelegationEngine
        engine = DelegationEngine()
        detected = engine.route_message(task)
        if detected and detected != "project-manager":
            return detected
    except Exception as _exc:
        logger.warning("delegate route_message failed: %s", _exc)

    # Fallback: intent matching desde agent discovery
    agents = _get_agents()
    intent_map = build_intent_map(agents)
    task_lower = task.lower()

    best_match: Tuple[int, str] = (0, "")
    for keyword, agent in intent_map.items():
        if keyword in task_lower:
            score = len(keyword)
            if score > best_match[0]:
                best_match = (score, agent)

    if best_match[1]:
        return best_match[1]

    # Último recurso: ModelRouter
    try:
        from harness.model_router.router import ModelRouter
        router = ModelRouter()
        decision = router.route(task, "*")
        if decision.source == "cloud":
            return "software-engineer"
    except ImportError:
        logger.warning("delegate ImportError: ModelRouter not available")
    except Exception as _exc:
        logger.warning("delegate route failed: %s", _exc)

    return None


def resolve_role(role_alias: str) -> Optional[str]:
    """Resuelve un alias a su nombre canónico de agente.

    Args:
        role_alias: Alias (@pm, @swe) o nombre parcial

    Returns:
        Nombre canónico o None si no se encuentra.
    """
    agents = _get_agents()
    canonical = discovery_resolve_agent(role_alias, agents)
    return canonical if canonical else None


def _parse_mention(task: str) -> Tuple[Optional[str], str]:
    """Extrae @rol: prefix del texto de la tarea.

    Returns:
        Tuple de (rol o None, texto restante).
    """
    match = re.match(r"@(\w[\w-]*)\s*:\s*(.*)", task.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, task.strip()


# ── Core function ─────────────────────────────────────────────────────


def delegate_task(task_text: str, extra_args: Optional[List[str]] = None) -> int:
    """Parsea la tarea, detecta rol si es necesario, y delega a run.py.

    Args:
        task_text: Texto de la tarea (puede incluir @rol: prefix).
        extra_args: Flags adicionales para run.py.

    Returns:
        Código de salida del subprocess.
    """
    extra_args = extra_args or []
    role, clean_task = _parse_mention(task_text)

    if role:
        # @rol explícito — resolver alias
        resolved = resolve_role(role)
        if not resolved:
            logger.info("[Delegate] Rol desconocido: @%s", role)
            agents = _get_agent_list()
            logger.info("[Delegate] Roles disponibles: %s", ", ".join(a[0] for a in agents))
            return 1
        role = resolved
    else:
        # Auto-detección de rol
        detected = _detect_role(task_text)
        if detected:
            role = detected
            logger.info("[Delegate] Rol detectado: @%s", role)
        else:
            # No se pudo detectar — preguntar al usuario
            logger.info("[Delegate] No se pudo detectar el rol automaticamente.")
            logger.info("[Delegate] Selecciona un rol para esta tarea:")
            agents_sorted = sorted(_get_agent_list(), key=lambda x: x[0])
            for i, (name, desc, _) in enumerate(agents_sorted, 1):
                logger.info("  %2d. @%-25s %s", i, name, desc)
            logger.info("  %2d. project-manager (default)", len(agents_sorted) + 1)
            try:
                choice = input(f"\nSelecciona un rol [1-{len(agents_sorted) + 1}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                choice = ""
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(agents_sorted):
                    role = agents_sorted[idx][0]
                else:
                    role = "project-manager"
            else:
                role = "project-manager"
            logger.info("[Delegate] Usando rol: @%s", role)

    # Construir string de tarea para run.py
    full_task = f"@{role}: {clean_task}"

    # Invocar run.py
    run_py = HARNESS_ROOT / "run.py"
    cmd = [sys.executable, str(run_py), full_task] + extra_args

    logger.info("[Delegate] Ejecutando: python harness/run.py \"%s\"", full_task)
    result = subprocess.run(cmd, cwd=str(get_project_root()))
    return result.returncode


# ── CLI modes ─────────────────────────────────────────────────────────


def _list_agents() -> None:
    """Muestra todos los agentes disponibles con descripciones."""
    agents = _get_agent_list()
    logger.info("=" * 72)
    logger.info("  AGENTES DISPONIBLES (%d roles)", len(agents))
    logger.info("=" * 72)
    logger.info("")
    logger.info("  %-28s %-40s %-12s", "Rol", "Dominio", "Alias")
    logger.info("  %-28s %-40s %-12s", "---", "------", "-----")
    for name, desc, alias in agents:
        logger.info("  @%-25s %-40s %-12s", name, desc[:38], alias)
    logger.info("")
    logger.info("  Uso: python harness/delegate.py \"@rol: tu tarea aqui\"")
    logger.info("  Uso: python harness/delegate.py \"tu tarea aqui\"       (deteccion automatica)")
    logger.info("")


def _interactive_mode() -> None:
    """Modo chat continuo con historial."""
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    logger.info("=" * 72)
    logger.info("  Modo interactivo — Escribe tu tarea o 'exit' para salir.")
    logger.info("")
    logger.info("  Ejemplos:")
    logger.info("    @software-engineer: crea un endpoint REST")
    logger.info("    implementa una API REST              (deteccion automatica)")
    logger.info("    --list                               (lista roles)")
    logger.info("")
    logger.info("  Presiona Ctrl+C o escribe 'exit' para salir.")
    logger.info("=" * 72)
    logger.info("")

    history: list[str] = []
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("")
            logger.info("[Delegate] Modo interactivo terminado.")
            break

        if not line:
            continue

        if line.lower() in ("exit", "quit", "q", "salir"):
            logger.info("[Delegate] Hasta luego!")
            break

        if line == "--list":
            _list_agents()
            continue

        history.append(line)
        exit_code = delegate_task(line)
        if exit_code != 0:
            logger.info("[Delegate] La tarea termino con codigo %d", exit_code)
        logger.info("")


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    """Delegate main entry point."""
    args = sys.argv[1:]

    if not args:
        logger.info("[Delegate] Uso: python harness/delegate.py \"<tu tarea>\"")
        logger.info("[Delegate]       python harness/delegate.py --list")
        logger.info("[Delegate]       python harness/delegate.py --interactive")
        logger.info("[Delegate]       python harness/delegate.py \"@rol: <tarea>\"")
        return 1

    if args[0] in ("--list", "-l"):
        _list_agents()
        return 0

    if args[0] in ("--interactive", "-i", "--chat"):
        _interactive_mode()
        return 0

    # Todo lo demás es la tarea (posiblemente con flags extra)
    task_parts: list[str] = []
    extra_flags: list[str] = []
    found_task = False

    for arg in args:
        if not found_task and arg.startswith("-") and not task_parts:
            extra_flags.append(arg)
        elif not found_task:
            task_parts.append(arg)
            found_task = True
        else:
            extra_flags.append(arg)

    task_text = " ".join(task_parts).strip()
    if not task_text:
        logger.info("[Delegate] No se proporciono ninguna tarea.")
        return 1

    return delegate_task(task_text, extra_flags)


if __name__ == "__main__":
    sys.exit(main())
