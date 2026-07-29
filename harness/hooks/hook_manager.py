"""HookManager — Orquestador central de hooks.

Ejecuta los hooks registrados en el orden correcto y gestiona los resultados.
Los hooks CRITICAL pueden detener la operacion (fail-fast).
Los hooks LOW registran pero no bloquean.

Flujo de ejecucion:
1. PRE_TOOL hooks: Validacion antes de ejecutar herramienta.
2. Ejecucion de la herramienta.
3. POST_TOOL hooks: Validacion de resultados.
4. ON_EDIT hooks: Formateo/linting post-escritura.
5. ON_NOTIFICATION hooks: Eventos asincronos.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from harness.hooks.hook_registry import (
    HookPriority,
    HookRegistration,
    HookRegistry,
    HookType,
)

logger = logging.getLogger(__name__)


class HookResultStatus(Enum):
    """Estado del resultado de ejecucion de un hook."""
    SUCCESS = auto()
    BLOCKED = auto()       # Hook critico rechazo la operacion
    ERROR = auto()         # Error inesperado durante ejecucion
    SKIPPED = auto()       # Hook deshabilitado o no aplicable


@dataclass
class HookResult:
    """Resultado de la ejecucion de un hook individual.

    Attributes:
        hook_name: Nombre del hook ejecutado.
        status: Estado de la ejecucion.
        duration_ms: Duracion en milisegundos.
        message: Mensaje descriptivo del resultado.
        data: Datos adicionales retornados por el hook.
    """
    hook_name: str
    status: HookResultStatus
    duration_ms: float = 0.0
    message: str = ""
    data: Optional[Dict[str, Any]] = None


@dataclass
class HookExecutionContext:
    """Contexto de ejecucion compartido entre hooks.

    Proporciona informacion sobre la operacion actual y permite
    a los hooks comunicarse entre si.

    Attributes:
        hook_type: Tipo de hook actual.
        tool_name: Nombre de la herramienta (si aplica).
        tool_args: Argumentos de la herramienta (si aplica).
        tool_result: Resultado de la herramienta (post_tool).
        file_path: Ruta del archivo afectado (on_edit).
        metadata: Datos adicionales compartidos entre hooks.
    """
    hook_type: HookType
    tool_name: str = ""
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    file_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class HookManager:
    """Orquestador central de hooks.

    Gestiona la ejecucion de hooks en el orden correcto, mantiene
    el contexto compartido y reporta resultados agregados.

    Args:
        registry: Instancia de HookRegistry. Si es None, usa la default.
    """

    def __init__(self, registry: Optional[HookRegistry] = None) -> None:
        """Inicializa el gestor de hooks.

        Args:
            registry: Registro de hooks a usar. Si es None, usa el singleton.
        """
        self._registry: HookRegistry = registry or HookRegistry.get_instance()

    def execute_pre_tool(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> List[HookResult]:
        """Ejecuta todos los hooks PRE_TOOL registrados.

        Los hooks CRITICAL pueden detener la ejecucion (fail-fast).
        Si un hook CRITICAL retorna BLOCKED, los hooks restantes se saltan.

        Args:
            tool_name: Nombre de la herramienta a ejecutar.
            tool_args: Argumentos de la herramienta.

        Returns:
            Lista de resultados de cada hook ejecutado.
        """
        ctx: HookExecutionContext = HookExecutionContext(
            hook_type=HookType.PRE_TOOL,
            tool_name=tool_name,
            tool_args=tool_args or {},
        )
        return self._execute_hooks(HookType.PRE_TOOL, ctx)

    def execute_post_tool(
        self,
        tool_name: str,
        tool_result: Any = None,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> List[HookResult]:
        """Ejecuta todos los hooks POST_TOOL registrados.

        Args:
            tool_name: Nombre de la herramienta ejecutada.
            tool_result: Resultado de la herramienta.
            tool_args: Argumentos originales de la herramienta.

        Returns:
            Lista de resultados de cada hook ejecutado.
        """
        ctx: HookExecutionContext = HookExecutionContext(
            hook_type=HookType.POST_TOOL,
            tool_name=tool_name,
            tool_result=tool_result,
            tool_args=tool_args or {},
        )
        return self._execute_hooks(HookType.POST_TOOL, ctx)

    def execute_on_edit(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[HookResult]:
        """Ejecuta todos los hooks ON_EDIT registrados.

        Args:
            file_path: Ruta del archivo modificado.
            metadata: Metadatos adicionales del cambio.

        Returns:
            Lista de resultados de cada hook ejecutado.
        """
        ctx: HookExecutionContext = HookExecutionContext(
            hook_type=HookType.ON_EDIT,
            file_path=file_path,
            metadata=metadata or {},
        )
        return self._execute_hooks(HookType.ON_EDIT, ctx)

    def execute_on_notification(
        self,
        notification_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> List[HookResult]:
        """Ejecuta todos los hooks ON_NOTIFICATION registrados.

        Args:
            notification_type: Tipo de notificacion.
            data: Datos de la notificacion.

        Returns:
            Lista de resultados de cada hook ejecutado.
        """
        ctx: HookExecutionContext = HookExecutionContext(
            hook_type=HookType.ON_NOTIFICATION,
            tool_name=notification_type,
            metadata=data or {},
        )
        return self._execute_hooks(HookType.ON_NOTIFICATION, ctx)

    def _execute_hooks(
        self,
        hook_type: HookType,
        ctx: HookExecutionContext,
    ) -> List[HookResult]:
        """Ejecuta todos los hooks de un tipo en orden de prioridad.

        Args:
            hook_type: Tipo de hook a ejecutar.
            ctx: Contexto de ejecucion compartido.

        Returns:
            Lista de resultados ordenada por prioridad.
        """
        hooks: List[HookRegistration] = self._registry.get_hooks(hook_type)
        results: List[HookResult] = []

        for hook in hooks:
            if not hook.enabled:
                results.append(HookResult(
                    hook_name=hook.name,
                    status=HookResultStatus.SKIPPED,
                    message="Hook deshabilitado",
                ))
                continue

            start: float = time.perf_counter()
            try:
                hook_result: Any = hook.func(ctx)
                duration: float = (time.perf_counter() - start) * 1000

                # Interpretar el resultado del hook
                if hook_result is False:
                    results.append(HookResult(
                        hook_name=hook.name,
                        status=HookResultStatus.BLOCKED,
                        duration_ms=duration,
                        message=hook.description or "Hook rechazo la operacion",
                    ))
                    # Fail-fast para hooks CRITICAL
                    if hook.priority == HookPriority.CRITICAL:
                        logger.warning(
                            "[HookManager] Hook CRITICAL '%s' BLOQUEO operacion (%dms)",
                            hook.name, duration,
                        )
                        break
                else:
                    results.append(HookResult(
                        hook_name=hook.name,
                        status=HookResultStatus.SUCCESS,
                        duration_ms=duration,
                        message=hook.description or "Ejecutado exitosamente",
                        data=hook_result if isinstance(hook_result, dict) else None,
                    ))

                logger.debug(
                    "[HookManager] Hook '%s' %s (%dms)",
                    hook.name,
                    "BLOQUEO" if hook_result is False else "OK",
                    duration,
                )

            except Exception as exc:
                duration = (time.perf_counter() - start) * 1000
                results.append(HookResult(
                    hook_name=hook.name,
                    status=HookResultStatus.ERROR,
                    duration_ms=duration,
                    message=f"Error: {exc}",
                ))
                logger.error(
                    "[HookManager] Hook '%s' error: %s",
                    hook.name, exc,
                )
                # Fail-fast para hooks CRITICAL con error
                if hook.priority == HookPriority.CRITICAL:
                    break

        return results

    def has_blocked(self, results: List[HookResult]) -> bool:
        """Verifica si algun hook bloqueo la operacion.

        Args:
            results: Lista de resultados de hooks.

        Returns:
            True si al menos un hook BLOCKED la operacion.
        """
        return any(r.status == HookResultStatus.BLOCKED for r in results)

    def has_errors(self, results: List[HookResult]) -> bool:
        """Verifica si algun hook tuvo errores.

        Args:
            results: Lista de resultados de hooks.

        Returns:
            True si al menos un hook tuvo ERROR.
        """
        return any(r.status == HookResultStatus.ERROR for r in results)
