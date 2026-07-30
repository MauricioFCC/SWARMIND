"""RuntimeDetector — Deteccion automatica del runtime activo.

Detecta automaticamente cual asistente AI esta ejecutando Swarmind
basado en variables de entorno, archivos de configuracion y heurísticas.

Runtimes soportados:
- OpenCode (.opencode/)
- Claude Code (ANTHROPIC_API_KEY + .claude/)
- Codex CLI (CODEX_CLI_SESSION + .codex/)
- Cursor (CURSOR_MODE + .cursor/)
- Gemini CLI (GEMINI_CLI + .gemini/)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RuntimeInfo:
    """Informacion completa sobre un runtime detectado.

    Attributes:
        name: Nombre del runtime (opencode, claude, codex, cursor, gemini).
        display_name: Nombre comercial para mostrar al usuario.
        config_dir: Directorio de configuracion relativo a project root.
        env_var: Variable de entorno que seniala su presencia.
        detected: True si el runtime fue detectado en el entorno actual.
        config_path: Ruta absoluta al archivo de configuracion principal.
        version: Version detectada del runtime (si disponible).
    """
    name: str
    display_name: str
    config_dir: str
    env_var: str
    detected: bool = False
    config_path: Optional[Path] = None
    version: Optional[str] = None


# Registro canónico de runtimes (SSOT).
# Orden de prioridad para deteccion: mas especifico primero.
RUNTIME_REGISTRY: List[RuntimeInfo] = [
    RuntimeInfo(
        name="gemini",
        display_name="Gemini CLI",
        config_dir=".gemini",
        env_var="GEMINI_CLI",
    ),
    RuntimeInfo(
        name="cursor",
        display_name="Cursor",
        config_dir=".cursor",
        env_var="CURSOR_MODE",
    ),
    RuntimeInfo(
        name="codex",
        display_name="Codex CLI",
        config_dir=".codex",
        env_var="CODEX_CLI_SESSION",
    ),
    RuntimeInfo(
        name="claude",
        display_name="Claude Code",
        config_dir=".claude",
        env_var="CLAUDE_CODE",
    ),
    RuntimeInfo(
        name="opencode",
        display_name="OpenCode",
        config_dir=".opencode",
        env_var="OPENCODE_AGENT_MD",
    ),
]


def detect_runtime(project_root: Optional[Path] = None) -> RuntimeInfo:
    """Detecta automaticamente el runtime activo.

    El orden de deteccion es:
    1. Variable de entorno Swarmind_RUNTIME (explicita, override total).
    2. Variable de entorno especifica de cada runtime.
    3. Presencia del directorio de configuracion en project_root.
    4. Variable de entorno de API key del proveedor (fallback heuristico).

    Args:
        project_root: Raiz del proyecto. Si es None, se usa CWD.

    Returns:
        RuntimeInfo del runtime detectado. Si no se detecta ninguno,
        retorna el primero con detected=False (opencode por defecto).

    Example:
        >>> runtime = detect_runtime()
        >>> runtime.name
        'opencode'
        >>> runtime.detected
        True
    """
    root: Path = project_root or Path.cwd()

    # 1. Override explicito via variable de entorno
    explicit: Optional[str] = os.environ.get("Swarmind_RUNTIME")
    if explicit:
        for rt in RUNTIME_REGISTRY:
            if rt.name == explicit.lower():
                rt.detected = True
                _resolve_config_path(rt, root)
                logger.info("[RuntimeDetector] Override explicito: %s", rt.display_name)
                return rt
        logger.warning("[RuntimeDetector] Swarmind_RUNTIME desconocido: %s", explicit)

    # 2-3. Deteccion por env var + directorio de configuracion
    for rt in RUNTIME_REGISTRY:
        # Variable de entorno especifica
        has_env: bool = bool(os.environ.get(rt.env_var))
        # Directorio de configuracion presente
        has_dir: bool = (root / rt.config_dir).is_dir()

        # API key heuristico para runtimes sin env var explicita
        api_key_hint: bool = False
        if rt.name == "claude":
            api_key_hint = bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif rt.name == "codex":
            api_key_hint = bool(os.environ.get("OPENAI_API_KEY"))
        elif rt.name == "gemini":
            api_key_hint = bool(os.environ.get("GOOGLE_API_KEY"))

        if has_env or has_dir or api_key_hint:
            rt.detected = True
            _resolve_config_path(rt, root)
            logger.info(
                "[RuntimeDetector] Detectado: %s (env=%s, dir=%s, key=%s)",
                rt.display_name, has_env, has_dir, api_key_hint,
            )
            return rt

    # 4. Fallback: OpenCode por defecto (siempre presente si .opencode/ existe)
    opencode_rt = RUNTIME_REGISTRY[-1]  # opencode
    if (root / ".opencode").is_dir():
        opencode_rt.detected = True
        _resolve_config_path(opencode_rt, root)
        logger.info("[RuntimeDetector] Fallback a OpenCode (directorio .opencode/ presente)")

    return opencode_rt


def _resolve_config_path(rt: RuntimeInfo, root: Path) -> None:
    """Resuelve la ruta al archivo de configuracion principal del runtime.

    Args:
        rt: RuntimeInfo a actualizar.
        root: Raiz del proyecto donde buscar.
    """
    config_files: Dict[str, str] = {
        "opencode": ".opencode/opencode.json",
        "claude": ".claude/settings.json",
        "codex": ".codex/config.toml",
        "cursor": ".cursorrules",
        "gemini": ".gemini/instructions.md",
    }
    cfg: Optional[str] = config_files.get(rt.name)
    if cfg:
        candidate: Path = root / cfg
        if candidate.exists():
            rt.config_path = candidate


def get_detected_runtimes(project_root: Optional[Path] = None) -> List[RuntimeInfo]:
    """Retorna todos los runtimes detectados en el proyecto.

    A diferencia de detect_runtime() que retorna el activo, esta funcion
    escanea todos los runtimes que tienen configuracion presente.

    Args:
        project_root: Raiz del proyecto.

    Returns:
        Lista de RuntimeInfo con detected=True para cada runtime presente.
    """
    root: Path = project_root or Path.cwd()
    detected: List[RuntimeInfo] = []
    for rt in RUNTIME_REGISTRY:
        if (root / rt.config_dir).is_dir():
            rt.detected = True
            _resolve_config_path(rt, root)
            detected.append(rt)
    return detected
