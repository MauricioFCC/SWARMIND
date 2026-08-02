"""BuiltinHooks — Hooks incorporados del sistema Swarmind.

Registra automaticamente los hooks esenciales para seguridad, calidad
y monitoreo del sistema.

Hooks incluidos:
1. SecurityValidator (PRE_TOOL, CRITICAL): Valida argumentos de herramientas.
2. PermissionChecker (PRE_TOOL, HIGH): Verifica permisos del agente.
3. AuditLogger (POST_TOOL, NORMAL): Registra auditoria de operaciones.
4. CodeFormatter (ON_EDIT, NORMAL): Formatea codigo Python al guardar.
5. MetricsCollector (ON_NOTIFICATION, LOW): Recolecta metricas del sistema.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.hooks.hook_manager import HookExecutionContext
from harness.hooks.hook_registry import (
    HookPriority,
    HookRegistry,
    HookType,
)

logger = logging.getLogger(__name__)

# Patrones de argumentos peligrosos para SecurityValidator
DANGEROUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE),
    re.compile(r"ALTER\s+TABLE.*DROP", re.IGNORECASE),
    re.compile(r"shutdown\s+-[fh]"),  # Apagar sistema
    re.compile(r"format\s+[a-z]:", re.IGNORECASE),  # Formatear disco
    re.compile(r"del\s+/[fs]"),  # Borrado masivo Windows
    re.compile(r"rd\s+/[fs]"),  # Borrado recursivo Windows
]

# Archivos bloqueados para escritura (nucleo del sistema)
PROTECTED_FILES: set[str] = {
    ".opencode/opencode.json",
    ".opencode/opencode.jsonc",
    "pyproject.toml",
}


def security_validator_hook(ctx: HookExecutionContext) -> bool:
    """PRE_TOOL CRITICAL: Valida que los argumentos no contengan comandos peligrosos.

    Args:
        ctx: Contexto de ejecucion del hook.

    Returns:
        True si es seguro, False si detecta actividad peligrosa.
    """
    if ctx.tool_name in ("bash", "shell", "exec", "run_command"):
        args_str: str = json.dumps(ctx.tool_args or {})
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(args_str):
                logger.warning(
                    "[SecurityValidator] BLOQUEADO: patron peligroso '%s' en %s",
                    pattern.pattern, ctx.tool_name,
                )
                return False
    return True


def permission_checker_hook(ctx: HookExecutionContext) -> bool:
    """PRE_TOOL HIGH: Verifica que el agente tenga permiso para la operacion.

    Args:
        ctx: Contexto de ejecucion del hook.

    Returns:
        True si la operacion esta permitida.
    """
    # Verificar si es una operacion de escritura en archivos protegidos
    if ctx.tool_name in ("write", "edit", "modify"):
        file_path: str = ""
        if ctx.tool_args:
            file_path = ctx.tool_args.get("filePath", "") or ctx.tool_args.get("file_path", "")
        if file_path:
            # Verificar archivos protegidos
            for protected in PROTECTED_FILES:
                if file_path.endswith(protected) or protected in file_path:
                    logger.warning(
                        "[PermissionChecker] BLOQUEADO: intento de escribir en archivo protegido: %s",
                        file_path,
                    )
                    return False
    return True


def audit_logger_hook(ctx: HookExecutionContext) -> dict:
    """POST_TOOL NORMAL: Registra en bitacora de auditoria las operaciones.

    Args:
        ctx: Contexto de ejecucion del hook.

    Returns:
        Dict con la entrada de auditoria generada.
    """
    audit_entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": ctx.tool_name,
        "hook_type": ctx.hook_type.name,
        "file_path": ctx.file_path if ctx.file_path else None,
        "status": "completed",
    }

    # Registrar en log estructurado
    logger.info("[Audit] %s", json.dumps(audit_entry))

    # Si hay archivo de auditoria, append
    audit_path: Path = Path.cwd() / ".opencode" / "audit.log"
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("[Audit] No se pudo escribir auditoria: %s", exc)

    return audit_entry


def metrics_collector_hook(ctx: HookExecutionContext) -> dict:
    """ON_NOTIFICATION LOW: Recolecta metricas del sistema.

    Args:
        ctx: Contexto de ejecucion del hook.

    Returns:
        Dict con las metricas recolectadas.
    """
    metrics: dict[str, Any] = {
        "event": ctx.tool_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "metadata": ctx.metadata,
    }
    logger.debug("[Metrics] %s", json.dumps(metrics))
    return metrics


def register_builtin_hooks(registry: HookRegistry | None = None) -> int:
    """Registra todos los hooks incorporados del sistema.

    Args:
        registry: Registro donde instalar los hooks. Si es None, usa el default.

    Returns:
        Numero de hooks registrados.

    Example:
        >>> n = register_builtin_hooks()
        >>> n
        4
    """
    reg: HookRegistry = registry or HookRegistry.get_instance()
    count: int = 0

    hooks: list[tuple] = [
        ("security_validator", HookType.PRE_TOOL, HookPriority.CRITICAL,
         security_validator_hook, "Valida comandos peligrosos en herramientas"),
        ("permission_checker", HookType.PRE_TOOL, HookPriority.HIGH,
         permission_checker_hook, "Verifica permisos de escritura en archivos protegidos"),
        ("audit_logger", HookType.POST_TOOL, HookPriority.NORMAL,
         audit_logger_hook, "Registra operaciones en bitacora de auditoria"),
        ("metrics_collector", HookType.ON_NOTIFICATION, HookPriority.LOW,
         metrics_collector_hook, "Recolecta metricas del sistema"),
    ]

    for name, hook_type, priority, func, description in hooks:
        if reg.register(name, hook_type, priority, func, description):
            count += 1

    logger.info("[BuiltinHooks] %d hooks incorporados registrados", count)
    return count
