"""HookRegistry — Registro central de hooks (singleton thread-safe).

Mantiene el registro maestro de todos los hooks del sistema, organizados
por tipo y prioridad. Los hooks se ejecutan en orden de prioridad
(CRITICAL primero, LOW ultimo).

Thread-safe via threading.Lock para entornos multi-agente.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from typing_extensions import Self

logger = logging.getLogger(__name__)


class HookType(Enum):
    """Tipos de hooks soportados por el sistema."""
    PRE_TOOL = auto()        # Antes de ejecutar una herramienta
    POST_TOOL = auto()       # Despues de ejecutar una herramienta
    ON_EDIT = auto()         # Cuando un archivo es modificado
    ON_NOTIFICATION = auto() # Cuando ocurre un evento del sistema


class HookPriority(Enum):
    """Prioridad de ejecucion de hooks.

    Los hooks CRITICAL se ejecutan primero y pueden detener la operacion.
    Los hooks LOW se ejecutan al final y no pueden detener la operacion.
    """
    CRITICAL = 0   # Validacion de seguridad, cortafuegos
    HIGH = 1       # Validacion de integridad, permisos
    NORMAL = 2     # Logging, metricas, auditoria
    LOW = 3        # Notificaciones, cosmeticos


HookFunc = Callable[..., Any]


@dataclass
class HookRegistration:
    """Registro de un hook en el sistema.

    Attributes:
        name: Nombre unico del hook.
        hook_type: Tipo de hook (PRE_TOOL, POST_TOOL, etc.).
        priority: Prioridad de ejecucion.
        func: Funcion a ejecutar.
        description: Descripcion del proposito del hook.
        enabled: Si el hook esta habilitado.
    """
    name: str
    hook_type: HookType
    priority: HookPriority
    func: HookFunc
    description: str = ""
    enabled: bool = True


class HookRegistry:
    """Registro central de hooks (singleton thread-safe).

    Mantiene el registro maestro de todos los hooks del sistema.
    Los hooks se organizan por tipo y se ejecutan en orden de prioridad.

    Example:
        >>> registry = HookRegistry.get_instance()
        >>> registry.register("validar_seguridad", HookType.PRE_TOOL,
        ...                   HookPriority.CRITICAL, mi_func)
        >>> hooks = registry.get_hooks(HookType.PRE_TOOL)
    """

    _instance: HookRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> Self:
        """Singleton thread-safe.

        Returns:
            Instancia unica de HookRegistry.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Inicializa el registro (solo una vez)."""
        if getattr(self, "_initialized", False):
            return
        self._hooks: dict[str, HookRegistration] = {}
        self._hooks_by_type: dict[HookType, list[HookRegistration]] = {
            hook_type: [] for hook_type in HookType
        }
        self._lock = threading.Lock()
        self._initialized = True

    @classmethod
    def get_instance(cls) -> HookRegistry:
        """Retorna la instancia unica del registro.

        Returns:
            Instancia de HookRegistry.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        hook_type: HookType,
        priority: HookPriority,
        func: HookFunc,
        description: str = "",
    ) -> bool:
        """Registra un nuevo hook en el sistema.

        Args:
            name: Nombre unico del hook.
            hook_type: Tipo de hook (PRE_TOOL, POST_TOOL, etc.).
            priority: Prioridad de ejecucion.
            func: Funcion a ejecutar cuando se dispare el hook.
            description: Descripcion del proposito del hook.

        Returns:
            True si se registro exitosamente, False si ya existe un hook
            con el mismo nombre.

        Example:
            >>> registry.register("check_permissions", HookType.PRE_TOOL,
            ...                   HookPriority.CRITICAL, check_perms,
            ...                   "Verifica permisos antes de ejecutar")
        """
        with self._lock:
            if name in self._hooks:
                logger.warning("[HookRegistry] Hook '%s' ya registrado", name)
                return False

            registration: HookRegistration = HookRegistration(
                name=name,
                hook_type=hook_type,
                priority=priority,
                func=func,
                description=description,
            )
            self._hooks[name] = registration
            self._hooks_by_type[hook_type].append(registration)
            # Mantener ordenado por prioridad
            self._hooks_by_type[hook_type].sort(key=lambda h: h.priority.value)

            logger.debug(
                "[HookRegistry] Hook registrado: %s (tipo=%s, prioridad=%s)",
                name, hook_type.name, priority.name,
            )
            return True

    def unregister(self, name: str) -> bool:
        """Elimina un hook del registro.

        Args:
            name: Nombre del hook a eliminar.

        Returns:
            True si se elimino exitosamente, False si no existia.
        """
        with self._lock:
            registration: HookRegistration | None = self._hooks.pop(name, None)
            if registration is None:
                return False

            hooks_of_type: list[HookRegistration] = self._hooks_by_type[registration.hook_type]
            self._hooks_by_type[registration.hook_type] = [
                h for h in hooks_of_type if h.name != name
            ]
            logger.debug("[HookRegistry] Hook eliminado: %s", name)
            return True

    def get_hooks(self, hook_type: HookType) -> list[HookRegistration]:
        """Retorna los hooks de un tipo especifico, ordenados por prioridad.

        Args:
            hook_type: Tipo de hook a consultar.

        Returns:
            Lista de HookRegistration ordenada por prioridad (CRITICAL primero).
        """
        with self._lock:
            return list(self._hooks_by_type.get(hook_type, []))

    def get_hook(self, name: str) -> HookRegistration | None:
        """Retorna un hook por su nombre.

        Args:
            name: Nombre del hook.

        Returns:
            HookRegistration o None si no existe.
        """
        return self._hooks.get(name)

    def enable(self, name: str) -> bool:
        """Habilita un hook previamente registrado.

        Args:
            name: Nombre del hook a habilitar.

        Returns:
            True si se habilito exitosamente.
        """
        with self._lock:
            hook: HookRegistration | None = self._hooks.get(name)
            if hook is None:
                return False
            hook.enabled = True
            return True

    def disable(self, name: str) -> bool:
        """Deshabilita un hook sin eliminarlo del registro.

        Args:
            name: Nombre del hook a deshabilitar.

        Returns:
            True si se deshabilito exitosamente.
        """
        with self._lock:
            hook: HookRegistration | None = self._hooks.get(name)
            if hook is None:
                return False
            hook.enabled = False
            return True

    def list_hooks(self) -> list[HookRegistration]:
        """Retorna todos los hooks registrados.

        Returns:
            Lista completa de HookRegistration.
        """
        with self._lock:
            return list(self._hooks.values())

    def count(self) -> int:
        """Retorna el numero total de hooks registrados.

        Returns:
            Cantidad de hooks.
        """
        with self._lock:
            return len(self._hooks)

    def clear(self) -> None:
        """Elimina todos los hooks del registro (solo para testing)."""
        with self._lock:
            self._hooks.clear()
            for hook_type in HookType:
                self._hooks_by_type[hook_type] = []
            logger.debug("[HookRegistry] Registro limpiado")
