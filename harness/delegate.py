#!/usr/bin/env python3
"""
Delegate — Entry point simplificado para el harness multi-agente.

Uso:
    python harness/delegate.py "haz X"                          → detecta rol automáticamente
    python harness/delegate.py "@software-engineer: crea API"   → delegación explícita
    python harness/delegate.py --list                           → lista roles disponibles
    python harness/delegate.py --interactive                    → modo chat
"""

from __future__ import annotations

import re
import sys
import os
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Ensure harness root is on sys.path
HARNESS_ROOT = Path(__file__).resolve().parent
if str(HARNESS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT.parent))

# ── Agent registry (copied from AGENTS.md for independence) ──────────

AGENTS: List[Tuple[str, str, str]] = [
    ("project-manager", "Orquestacion F.R.A.M.E., planificacion", "@pm"),
    ("context-engineer", "Curation de contexto, token budget, RAG", "@context"),
    ("tool-mcp-engineer", "Ecosistema MCP, herramientas", "@mcp"),
    ("software-engineer", "APIs, servicios, full-stack", "@swe"),
    ("data-architect", "Schemas, modelos, migraciones", "@data"),
    ("devops-sre", "CI/CD, Docker, infraestructura", "@devops"),
    ("security-engineer", "Seguridad, compliance, hardening", "@sec"),
    ("frontend-engineer", "UI/UX, dashboards", "@frontend"),
    ("mobile-engineer", "Apps iOS/Android", "@mobile"),
    ("ai-engineer", "ML/AI, pipelines, LLMOps", "@ai"),
    ("quality-gate", "QA, tests, cobertura", "@qa"),
    ("documentation-specialist", "Documentacion tecnica", "@docs"),
    ("requirements-analyst", "Analisis de requerimientos", "@ra"),
    ("enterprise-architect", "Arquitectura de sistemas, ADR", "@architect"),
    ("quant-developer", "Estrategias cuantitativas, brokers", "@quant"),
    ("quant-scientist", "Validacion estadistica, experimentos", "@scientist"),
    ("risk-manager", "Gestion de riesgo, position sizing", "@risk"),
    ("trading-operations", "Monitoreo en vivo, alertas", "@ops"),
    ("evolve-researcher", "Investigacion de mejoras", "!evolve run"),
    ("evolve-engineer", "Ejecucion de mejoras", "!evolve run"),
    ("evolve-analyzer", "Analisis de resultados", "!evolve run"),
]

# ── Role detection ────────────────────────────────────────────────────

# Intent mapping (lightweight version of DelegationEngine's intent map)
_INTENT_AGENTS: dict[str, str] = {
    "api": "software-engineer",
    "endpoint": "software-engineer",
    "implementar": "software-engineer",
    "codigo": "software-engineer",
    "refactor": "software-engineer",
    "test": "quality-gate",
    "ui": "frontend-engineer",
    "frontend": "frontend-engineer",
    "dashboard": "frontend-engineer",
    "schema": "data-architect",
    "migracion": "data-architect",
    "base de datos": "data-architect",
    "deploy": "devops-sre",
    "docker": "devops-sre",
    "ci/cd": "devops-sre",
    "seguridad": "security-engineer",
    "vulnerabilidad": "security-engineer",
    "mobile": "mobile-engineer",
    "ios": "mobile-engineer",
    "android": "mobile-engineer",
    "documentacion": "documentation-specialist",
    "readme": "documentation-specialist",
    "estrategia": "quant-developer",
    "trading": "quant-developer",
    "backtest": "quant-developer",
    "riesgo": "risk-manager",
    "arquitectura": "enterprise-architect",
    "machine learning": "ai-engineer",
    "modelo": "ai-engineer",
    "plan": "project-manager",
    "planificar": "project-manager",
    "requerimiento": "requirements-analyst",
    "analisis": "requirements-analyst",
    "monitoreo": "trading-operations",
    "alerta": "trading-operations",
    "evolucion": "evolve-engineer",
    "mejora": "evolve-engineer",
    "contexto": "context-engineer",
    "prompt": "context-engineer",
    "mcp": "tool-mcp-engineer",
    "herramienta": "tool-mcp-engineer",
}


def _detect_role(task: str) -> str | None:
    """Detect the best agent role for a task using intent matching.

    Falls back to DelegationEngine if available, otherwise uses
    a built-in lightweight intent map.
    """
    # Try to use DelegationEngine first (more comprehensive)
    try:
        from harness.orchestrator.delegation_engine import DelegationEngine
        engine = DelegationEngine()
        detected = engine.route_message(task)
        if detected and detected != "project-manager":
            return detected
    except ImportError:
        pass
    except Exception:
        pass

    # Built-in fallback: keyword matching
    task_lower = task.lower()
    best_match: tuple[int, str] = (0, "")

    for keyword, agent in _INTENT_AGENTS.items():
        if keyword in task_lower:
            # Longer keyword = better match (more specific)
            score = len(keyword)
            if score > best_match[0]:
                best_match = (score, agent)

    if best_match[1]:
        return best_match[1]

    # Try ModelRouter as last resort for role detection
    try:
        from harness.model_router.router import ModelRouter
        router = ModelRouter()
        decision = router.route(task, "*")
        # If routed to cloud for complexity, default to software-engineer
        if decision.source == "cloud":
            return "software-engineer"
    except ImportError:
        pass
    except Exception:
        pass

    return None


def _parse_mention(task: str) -> tuple[str | None, str]:
    """Extract @rol: prefix from task text.

    Returns:
        Tuple of (role or None, remaining text).
    """
    match = re.match(r"@(\w[\w-]*)\s*:\s*(.*)", task.strip())
    if match:
        return match.group(1), match.group(2).strip()
    return None, task.strip()


def resolve_role(role_alias: str) -> str | None:
    """Resolve a role alias/shortname to its canonical agent name."""
    alias_map: dict[str, str] = {
        "pm": "project-manager",
        "context": "context-engineer",
        "mcp": "tool-mcp-engineer",
        "swe": "software-engineer",
        "data": "data-architect",
        "devops": "devops-sre",
        "sec": "security-engineer",
        "frontend": "frontend-engineer",
        "mobile": "mobile-engineer",
        "ai": "ai-engineer",
        "qa": "quality-gate",
        "docs": "documentation-specialist",
        "ra": "requirements-analyst",
        "architect": "enterprise-architect",
        "quant": "quant-developer",
        "scientist": "quant-scientist",
        "risk": "risk-manager",
        "ops": "trading-operations",
    }
    canonical = role_alias.lower().replace("_", "-")
    return alias_map.get(canonical, canonical if any(canonical == a[0] for a in AGENTS) else None)


# ── Core function ─────────────────────────────────────────────────────


def delegate_task(task_text: str, extra_args: list[str] | None = None) -> int:
    """Parse task text, detect role if needed, and delegate to run.py.

    Args:
        task_text: The raw task description (may include @rol: prefix).
        extra_args: Additional CLI flags to pass to run.py.

    Returns:
        Exit code from the subprocess.
    """
    extra_args = extra_args or []
    role, clean_task = _parse_mention(task_text)

    if role:
        # Explicit @rol: prefix — resolve alias if needed
        resolved = resolve_role(role)
        if not resolved:
            logger.info(f"[Delegate] Rol desconocido: @{role}")
            logger.info(f"[Delegate] Usa --list para ver los roles disponibles.")
            return 1
        role = resolved
    else:
        # Auto-detect role
        detected = _detect_role(task_text)
        if detected:
            role = detected
            logger.info(f"[Delegate] Rol detectado: @{role}")
        else:
            # Can't detect — ask user
            logger.info("[Delegate] No se pudo detectar el rol automaticamente.")
            logger.info("[Delegate] Selecciona un rol para esta tarea:")
            agents_sorted = sorted(AGENTS, key=lambda x: x[0])
            for i, (name, desc, _) in enumerate(agents_sorted, 1):
                logger.info(f"  {i:2d}. @{name:<25s} {desc}")
            logger.info(f"  {len(agents_sorted) + 1:2d}. project-manager (default)")
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
            logger.info(f"[Delegate] Usando rol: @{role}")

    # Build the task string for run.py
    full_task = f"@{role}: {clean_task}"

    # Invoke run.py
    run_py = HARNESS_ROOT / "run.py"
    cmd = [sys.executable, str(run_py), full_task] + extra_args

    logger.info(f"[Delegate] Ejecutando: python harness/run.py \"{full_task}\"")
    result = subprocess.run(cmd, cwd=str(HARNESS_ROOT.parent))
    return result.returncode


# ── CLI modes ─────────────────────────────────────────────────────────


def _list_agents() -> None:
    """Print all available agents with descriptions."""
    logger.info("=" * 72)
    logger.info("  AGENTES DISPONIBLES (21 roles)")
    logger.info("=" * 72)
    logger.info("")
    logger.info(f"  {'Rol':<28s} {'Dominio':<40s} {'Alias':<12s}")
    logger.info(f"  {'---':<28s} {'------':<40s} {'-----':<12s}")
    for name, desc, alias in AGENTS:
        logger.info(f"  @{name:<25s} {desc:<40s} {alias:<12s}")
    logger.info("")
    logger.info("  Uso: python harness/delegate.py \"@rol: tu tarea aqui\"")
    logger.info("  Uso: python harness/delegate.py \"tu tarea aqui\"       (deteccion automatica)")
    logger.info("")


def _interactive_mode() -> None:
    """Continuous chat mode with readline history support."""
    try:
        import readline  # noqa: F401 — enables arrow key history on Unix
    except ImportError:
        pass  # Windows: arrow keys won't have history, but input() still works

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
            logger.info(f"[Delegate] La tarea termino con codigo {exit_code}")
        logger.info("")  # Blank line for readability


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

    # Everything else is the task (possibly with extra flags)
    # Find where the task ends and extra flags begin
    task_parts: list[str] = []
    extra_flags: list[str] = []
    found_task = False

    for arg in args:
        if not found_task and arg.startswith("-") and not task_parts:
            # Flags before the task (e.g. --auto-pilot)
            extra_flags.append(arg)
        elif not found_task:
            task_parts.append(arg)
            found_task = True
        else:
            # After the task starts, collect remaining as extra args
            extra_flags.append(arg)

    task_text = " ".join(task_parts).strip()
    if not task_text:
        logger.info("[Delegate] No se proporciono ninguna tarea.")
        return 1

    return delegate_task(task_text, extra_flags)


if __name__ == "__main__":
    sys.exit(main())
