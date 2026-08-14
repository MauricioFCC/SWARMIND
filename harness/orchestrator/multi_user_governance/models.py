"""MultiUserGovernance models — roles, permisos, hooks y dataclasses.

Extraccion mecanica del modulo original
``harness/orchestrator/multi_user_governance.py`` (sin cambios de logica
ni firmas): Role, ROLE_PERMISSIONS, _ROLE_HIERARCHY,
_resolve_role_permissions, tipos de hooks, ExecutionHooks, AuditEntry
y User.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Role(str, Enum):
    """Roles de usuario en el sistema de gobernanza multi-principal.

    ADMIN: Control total del sistema (crear/eliminar/modificar agentes, gestionar usuarios).
    EDITOR: Crear y modificar agentes, ejecutar acciones, ver logs.
    VIEWER: Ejecutar agentes existentes y ver logs.
    AUDITOR: Solo lectura de logs y capacidad de auditoria.
    """

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    AUDITOR = "auditor"


# Mapa de permisos base por rol
ROLE_PERMISSIONS: dict[Role, list[str]] = {
    Role.ADMIN: [
        "create_agent", "delete_agent", "modify_agent",
        "execute_agent", "view_logs", "manage_users",
        "audit_agent",
    ],
    Role.EDITOR: [
        "create_agent", "modify_agent", "execute_agent", "view_logs",
    ],
    Role.VIEWER: [
        "execute_agent", "view_logs",
    ],
    Role.AUDITOR: [
        "view_logs", "audit_agent",
    ],
}

# Herencia de roles: cada rol hereda permisos del rol del que depende
# (ADMIN -> EDITOR -> VIEWER, AUDITOR es independiente)
_ROLE_HIERARCHY: dict[Role, Role | None] = {
    Role.ADMIN: Role.EDITOR,
    Role.EDITOR: Role.VIEWER,
    Role.VIEWER: None,
    Role.AUDITOR: None,
}


def _resolve_role_permissions(role: Role) -> list[str]:
    """Resolver permisos completos de un rol incluyendo herencia.

    Args:
        role: Rol del cual resolver permisos.

    Returns:
        List[str]: Lista completa de permisos incluyendo los heredados.
    """
    permissions: list[str] = []
    current: Role | None = role
    visited: set = set()
    while current is not None and current not in visited:
        visited.add(current)
        permissions.extend(ROLE_PERMISSIONS.get(current, []))
        current = _ROLE_HIERARCHY.get(current)
    # Eliminar duplicados preservando orden
    seen: set = set()
    unique: list[str] = []
    for p in permissions:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Tipos para execution hooks
# ---------------------------------------------------------------------------

PreExecHook = Callable[[str, str, dict[str, Any]], bool | None]
"""Hook antes de ejecutar una accion: (username, permission, context) -> Optional[bool].
Retorna False para denegar, True/None para permitir."""

PostExecHook = Callable[[str, str, dict[str, Any], bool], None]
"""Hook despues de ejecutar una accion: (username, permission, context, granted) -> None."""

OnDenyHook = Callable[[str, str, dict[str, Any], str | None], None]
"""Hook cuando se deniega una accion: (username, permission, context, reason) -> None."""


@dataclass
class ExecutionHooks:
    """Contenedor de hooks de ejecucion para gobernanza multi-principal.

    Attributes:
        pre_exec: Hook invocado antes de cada verificacion de permiso.
                  Si retorna False, la accion se deniega inmediatamente.
        post_exec: Hook invocado despues de cada verificacion (exitosa o denegada).
        on_deny: Hook invocado especificamente cuando se deniega un permiso.
    """

    pre_exec: PreExecHook | None = None
    post_exec: PostExecHook | None = None
    on_deny: OnDenyHook | None = None


@dataclass
class AuditEntry:
    """Entrada individual del registro de auditoria.

    Attributes:
        timestamp: Momento exacto del evento (UTC).
        username: Nombre del usuario que ejecuto la accion.
        action: Tipo de evento (CHECK, GRANTED, DENIED, ADD_USER, etc.).
        detail: Descripcion detallada del evento.
    """
    timestamp: datetime
    username: str
    action: str
    detail: str


@dataclass
class User:
    """Representacion de un usuario en el sistema de gobernanza.

    Attributes:
        username: Identificador unico del usuario.
        role: Rol asignado al usuario.
        permissions: Lista de permisos efectivos del usuario (incluye herencia).
        enabled: Si el usuario esta activo en el sistema.
        metadata: Datos adicionales del usuario (libre).
    """
    username: str
    role: Role
    permissions: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
