"""
CLI Common — Funcionalidad compartida entre run.py y delegate.py.

Extrae lógica duplicada de ambos entrypoints en un solo lugar,
aplicando el patrón DRY. Incluye:
  - setup_logging()
  - parse_message() — parsing de @rol y !comandos
  - load_vector_store()
  - print_banner()
  - ANSI helpers
  - First-run detection

REFACTOR: Elimina ~150 líneas de código duplicado entre run.py y delegate.py.
"""
from __future__ import annotations

import os
import re
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configura logging estructurado (JSON) para todos los entrypoints.
    
    Usa el módulo observability/logging.py que proporciona:
    - Formato JSON estructurado
    - Correlation IDs para trazabilidad
    - RED metrics (Rate, Errors, Duration)
    
    Si el módulo no está disponible, fallback a basicConfig tradicional.
    """
    try:
        from harness.observability.logging import setup_structured_logging
        setup_structured_logging(level)
    except ImportError:
        logging.basicConfig(level=level, format="%(message)s")
    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_harness_root() -> Path:
    """Retorna la ruta absoluta a harness/."""
    return Path(__file__).resolve().parent


def get_project_root() -> Path:
    """Retorna la ruta absoluta a la raíz del proyecto."""
    return get_harness_root().parent


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"{_GREEN}{msg}{_RESET}"


def _warn(msg: str) -> str:
    return f"{_YELLOW}{msg}{_RESET}"


def _err(msg: str) -> str:
    return f"{_RED}{msg}{_RESET}"


def _bold(msg: str) -> str:
    return f"{_BOLD}{msg}{_RESET}"


def _cyan(msg: str) -> str:
    return f"{_CYAN}{msg}{_RESET}"


def _safe_print(*args, **kwargs) -> None:
    """Print con fallback Unicode: reemplaza caracteres no imprimibles."""
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


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def parse_message(task: str) -> Tuple[Optional[str], str]:
    """
    Parsea un mensaje extrayendo @rol: y !comandos.
    
    AHORA CON AUTO-DETECCIÓN: si no hay @ explícito, detecta el rol
    automáticamente por el contenido del mensaje usando los roles universales:
      - @builder: implementación (Rust, Go, Python, Web, Mobile, Trading, Infra)
      - @scientist: investigación, papers, AI/ML, patrones
      - @guardian: calidad, seguridad, riesgo, docs, operaciones
      - @evolve: auto-mejora del sistema
      - @coordinator: default (analiza y delega)

    Args:
        task: Texto de entrada (e.g., "@builder: haz X", "!iteration end", o "implementa una API en Rust")

    Returns:
        Tuple de (rol detectado o None para !comandos, texto limpio)
    """
    # !comandos retornan (None, texto original)
    if task.startswith("!"):
        return None, task

    # @rol: texto — ruteo explícito (backward compatible)
    match = re.match(r"@(\w[\w-]*)\s*:\s*(.*)", task.strip())
    if match:
        return match.group(1), match.group(2).strip()

    # @rol texto (sin dos puntos)
    match = re.match(r"@(\w[\w-]*)\s+(.*)", task.strip())
    if match:
        return match.group(1), match.group(2).strip()

    # Auto-detección: sin @, detectar rol por contenido
    # Delegamos a DelegationEngine.auto_route()
    try:
        from harness.orchestrator.delegation_engine import DelegationEngine
        engine = DelegationEngine()
        detected = engine.auto_route(task)
        return detected, task.strip()
    except Exception as _exc:
        logger.warning("cli_common: %s", _exc)

    # Fallback: coordinator como default
    return "coordinator", task.strip()


def format_task_with_role(role: str, task: str) -> str:
    """Formatea tarea con @rol: prefix."""
    return f"@{role}: {task}"


# ---------------------------------------------------------------------------
# Vector Store loading
# ---------------------------------------------------------------------------

def load_vector_store(db_path: Optional[str] = None) -> Any:
    """
    Carga el vector store LanceDB, con manejo de errores claro.

    Args:
        db_path: Ruta opcional a la base de datos

    Returns:
        Instancia de LanceVectorStore

    Raises:
        ImportError: Si LanceDB no está instalado
        RuntimeError: Si no se puede conectar
    """
    from harness.memory_rag.lance_vector_store import LanceVectorStore

    kwargs = {}
    if db_path:
        kwargs["db_path"] = db_path

    store = LanceVectorStore(**kwargs)
    return store


# ---------------------------------------------------------------------------
# First-run onboarding
# ---------------------------------------------------------------------------

def check_first_run(harness_root: Path) -> bool:
    """Detecta si es primera ejecución y guía al usuario en la configuración."""
    from datetime import datetime

    marker_file = harness_root / ".harness_initialized"
    if marker_file.exists():
        return False

    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("  AGENTIC Harness -- Primera ejecucion detectada")
    logger.info("=" * 60)
    logger.info("")

    # Paso 1: Nombre del proyecto
    try:
        project_name = input("  1. Nombre del proyecto [default: mi-proyecto]: ").strip()
    except (EOFError, KeyboardInterrupt):
        project_name = ""
    if not project_name:
        project_name = "mi-proyecto"

    # Paso 2: Stack
    print("\n  2. Stack tecnologico:")
    print("     a) Python")
    print("     b) Rust")
    print("     c) Go")
    print("     d) Node/TypeScript")
    print("     e) Otro")
    try:
        stack = input("     Selecciona tu stack [a]: ").strip().lower() or "a"
    except (EOFError, KeyboardInterrupt):
        stack = "a"
    stack_map = {"a": "Python", "b": "Rust", "c": "Go", "d": "Node/TypeScript", "e": "Otro"}
    tech_stack = stack_map.get(stack, "Python")

    # Paso 3: Dominio
    print("\n  3. Dominio del proyecto:")
    print("     a) Web")
    print("     b) Trading")
    print("     c) CLI/Herramienta")
    print("     d) API/Microservicio")
    print("     e) Otro")
    try:
        dom = input("     Selecciona el dominio [a]: ").strip().lower() or "a"
    except (EOFError, KeyboardInterrupt):
        dom = "a"
    dom_map = {"a": "web", "b": "trading", "c": "cli", "d": "api", "e": "otro"}
    domain = dom_map.get(dom, "web")

    # Paso 4: Auto-configurar project_config.yaml
    config_path = get_project_root() / ".opencode" / "config" / "project_config.yaml"
    if config_path.exists():
        config_content = config_path.read_text(encoding="utf-8")
        config_content = config_content.replace('PROJECT_NAME: ""', f'PROJECT_NAME: "{project_name}"')
        config_content = config_content.replace('DOMAIN: ""', f'DOMAIN: "{domain}"')
        config_content = config_content.replace('TECH_STACK: ""', f'TECH_STACK: "{tech_stack}"')
        config_path.write_text(config_content, encoding="utf-8")
        logger.info("  project_config.yaml actualizado: %s (%s, %s)", project_name, tech_stack, domain)

        try:
            from harness.scripts.init import _load_domain_skills
            _load_domain_skills()
        except Exception as exc:
            logger.info("  (No se pudo cargar skill de dominio: %s)", exc)

    # Paso 5: Ejecutar init.py
    logger.info("")
    logger.info("  Ejecutando init.py para completar la configuracion...")
    import subprocess as _subprocess
    _subprocess.run([sys.executable, str(harness_root / "scripts" / "init.py")], cwd=get_project_root())

    # Paso 6: RAG Ingest
    logger.info("")
    try:
        rag = input("  Ingerir codigo fuente ahora? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        rag = ""
    if rag == "y":
        logger.info("  Ingestando codigo fuente...")
        try:
            from harness.memory_rag.doc_ingester import ingest_project_directory
            import time as _t
            _start = _t.time()
            _stats = ingest_project_directory(str(get_project_root()))
            _elapsed = _t.time() - _start
            logger.info(
                "  RAG ingest: %d archivos, %d chunks en %.1fs",
                _stats.get("files_processed", 0),
                _stats.get("chunks_inserted", 0),
                _elapsed,
            )
        except Exception as exc:
            logger.info("  (RAG ingest difiere: %s)", exc)

    # Paso 7: Crear marker
    marker_file.write_text(f"initialized: {datetime.now().isoformat()}\nproject: {project_name}\n")
    logger.info("")
    logger.info("  Harness configurado. Listo para usar!")
    logger.info("")
    return True


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner(title: str, harness_root: Optional[Path] = None) -> None:
    """Muestra banner del harness."""
    _safe_print(f"  {_bold(title)}")
    _safe_print(f"  {'=' * 60}")
