"""
MultiUserGovernance — Permisos multi-principal con execution hooks (arXiv:2606.21856).

Implementa un sistema de gobernanza multi-usuario para agentes, donde cada
principal (usuario) tiene un rol con permisos especificos sobre acciones de
agentes. Proporciona execution hooks (pre_exec, post_exec, on_deny) para
interceptar y controlar operaciones en tiempo de ejecucion.

Roles: admin, editor, viewer, auditor. El admin hereda todos los permisos;
editor hereda de viewer; auditor tiene permisos de lectura y auditoria.

Basado en: arXiv:2606.21856 — Multi-Principal Permission Governance with
Execution Hooks for Agentic Systems.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


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
ROLE_PERMISSIONS: Dict[Role, List[str]] = {
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
_ROLE_HIERARCHY: Dict[Role, Optional[Role]] = {
    Role.ADMIN: Role.EDITOR,
    Role.EDITOR: Role.VIEWER,
    Role.VIEWER: None,
    Role.AUDITOR: None,
}


def _resolve_role_permissions(role: Role) -> List[str]:
    """Resolver permisos completos de un rol incluyendo herencia.

    Args:
        role: Rol del cual resolver permisos.

    Returns:
        List[str]: Lista completa de permisos incluyendo los heredados.
    """
    permissions: List[str] = []
    current: Optional[Role] = role
    visited: set = set()
    while current is not None and current not in visited:
        visited.add(current)
        permissions.extend(ROLE_PERMISSIONS.get(current, []))
        current = _ROLE_HIERARCHY.get(current)
    # Eliminar duplicados preservando orden
    seen: set = set()
    unique: List[str] = []
    for p in permissions:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Tipos para execution hooks
# ---------------------------------------------------------------------------

PreExecHook = Callable[[str, str, Dict[str, Any]], Optional[bool]]
"""Hook antes de ejecutar una accion: (username, permission, context) -> Optional[bool].
Retorna False para denegar, True/None para permitir."""

PostExecHook = Callable[[str, str, Dict[str, Any], bool], None]
"""Hook despues de ejecutar una accion: (username, permission, context, granted) -> None."""

OnDenyHook = Callable[[str, str, Dict[str, Any], Optional[str]], None]
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

    pre_exec: Optional[PreExecHook] = None
    post_exec: Optional[PostExecHook] = None
    on_deny: Optional[OnDenyHook] = None


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
    permissions: List[str] = field(default_factory=list)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiUserGovernance:
    """Sistema de gobernanza multi-usuario con execution hooks.

    Gestiona usuarios, roles, permisos y proporciona un mecanismo de
    verificacion de permisos con hooks de pre/post ejecucion y manejo
    de denegaciones. Mantiene un registro de auditoria completo.

    Basado en: arXiv:2606.21856 — Multi-Principal Permission Governance.

    Examples:
        >>> gov = MultiUserGovernance()
        >>> user = gov.add_user("alice", Role.ADMIN)
        >>> gov.check_permission("alice", "delete_agent")
        True
        >>> gov.check_permission("bob", "delete_agent")
        False
    """

    def __init__(self, hooks: Optional[ExecutionHooks] = None) -> None:
        """Inicializar el sistema de gobernanza multi-usuario.

        Args:
            hooks: Configuracion opcional de execution hooks. Si no se
                   proporciona, se usan los hooks por defecto (solo logging).
        """
        self._users: Dict[str, User] = {}
        self._audit_log: List[AuditEntry] = []
        self._hooks: ExecutionHooks = hooks or ExecutionHooks()
        logger.info("MultiUserGovernance iniciado con %s", self._hooks)

    # ------------------------------------------------------------------
    # Gestion de usuarios
    # ------------------------------------------------------------------

    def add_user(self, username: str, role: Role, enabled: bool = True,
                 metadata: Optional[Dict[str, Any]] = None) -> User:
        """Agregar un nuevo usuario al sistema de gobernanza.

        Los permisos se asignan automaticamente segun el rol y su
        jerarquia de herencia.

        Args:
            username: Nombre unico del usuario.
            role: Rol asignado.
            enabled: Si el usuario comienza activo.
            metadata: Datos adicionales opcionales.

        Returns:
            User: El usuario creado.

        Raises:
            ValueError: Si el username ya existe en el sistema.
        """
        if username in self._users:
            raise ValueError(
                f"MultiUserGovernance: usuario '{username}' ya existe"
            )
        permissions = _resolve_role_permissions(role)
        user = User(
            username=username,
            role=role,
            permissions=permissions,
            enabled=enabled,
            metadata=metadata or {},
        )
        self._users[username] = user
        self._audit("ADD_USER", f"Usuario '{username}' rol={role.value}")
        logger.info(
            "MultiUserGovernance: usuario '%s' agregado con rol=%s (%d permisos)",
            username, role.value, len(permissions),
        )
        return user

    def remove_user(self, username: str) -> None:
        """Eliminar un usuario del sistema de gobernanza.

        Args:
            username: Nombre del usuario a eliminar.

        Raises:
            ValueError: Si el usuario no existe.
        """
        if username not in self._users:
            raise ValueError(
                f"MultiUserGovernance: usuario '{username}' no encontrado"
            )
        del self._users[username]
        self._audit("REMOVE_USER", f"Usuario '{username}' eliminado")
        logger.info("MultiUserGovernance: usuario '%s' eliminado", username)

    def get_user(self, username: str) -> Optional[User]:
        """Obtener un usuario por su nombre.

        Args:
            username: Nombre del usuario a buscar.

        Returns:
            Optional[User]: El usuario si existe, None si no.
        """
        return self._users.get(username)

    def get_users(self) -> Dict[str, User]:
        """Obtener copia del diccionario completo de usuarios.

        Returns:
            Dict[str, User]: Copia del mapa de usuarios.
        """
        return dict(self._users)

    def update_user_role(self, username: str, new_role: Role) -> User:
        """Actualizar el rol de un usuario y recalcular sus permisos.

        Args:
            username: Nombre del usuario.
            new_role: Nuevo rol a asignar.

        Returns:
            User: El usuario actualizado.

        Raises:
            ValueError: Si el usuario no existe.
        """
        user = self._users.get(username)
        if user is None:
            raise ValueError(
                f"MultiUserGovernance: usuario '{username}' no encontrado"
            )
        old_role = user.role
        user.role = new_role
        user.permissions = _resolve_role_permissions(new_role)
        self._audit(
            "UPDATE_ROLE",
            f"Usuario '{username}' rol={old_role.value} -> {new_role.value}",
        )
        logger.info(
            "MultiUserGovernance: usuario '%s' rol actualizado %s -> %s",
            username, old_role.value, new_role.value,
        )
        return user

    def set_user_enabled(self, username: str, enabled: bool) -> None:
        """Habilitar o deshabilitar un usuario.

        Args:
            username: Nombre del usuario.
            enabled: True para activar, False para desactivar.

        Raises:
            ValueError: Si el usuario no existe.
        """
        user = self._users.get(username)
        if user is None:
            raise ValueError(
                f"MultiUserGovernance: usuario '{username}' no encontrado"
            )
        user.enabled = enabled
        status = "habilitado" if enabled else "deshabilitado"
        self._audit("SET_ENABLED", f"Usuario '{username}' {status}")
        logger.info("MultiUserGovernance: usuario '%s' %s", username, status)

    # ------------------------------------------------------------------
    # Verificacion de permisos
    # ------------------------------------------------------------------

    def check_permission(self, username: str, permission: str,
                         context: Optional[Dict[str, Any]] = None) -> bool:
        """Verificar si un usuario tiene un permiso especifico.

        Evalua la cadena completa: usuario existe -> habilitado -> hook
        pre_exec -> permiso en lista -> audit trail. Invoca los hooks
        correspondientes en cada etapa.

        Args:
            username: Nombre del usuario.
            permission: Permiso a verificar (ej: 'delete_agent').
            context: Contexto opcional de la operacion para los hooks.

        Returns:
            bool: True si el usuario tiene el permiso, False en caso contrario.
        """
        context = context or {}
        user = self._users.get(username)

        # 1. Verificar que el usuario exista
        if user is None:
            self._audit(
                "DENIED",
                f"Usuario '{username}' no existe (permiso={permission})",
            )
            self._invoke_on_deny(username, permission, context,
                                 "usuario no existe")
            self._invoke_post_exec(username, permission, context, granted=False)
            return False

        # 2. Verificar que el usuario este habilitado
        if not user.enabled:
            self._audit(
                "DENIED",
                f"Usuario '{username}' deshabilitado (permiso={permission})",
            )
            self._invoke_on_deny(username, permission, context,
                                 "usuario deshabilitado")
            self._invoke_post_exec(username, permission, context, granted=False)
            return False

        # 3. Hook pre_exec — permite denegar antes de la verificacion
        if self._hooks.pre_exec is not None:
            try:
                pre_result = self._hooks.pre_exec(username, permission, context)
                if pre_result is False:
                    self._audit(
                        "DENIED",
                        f"Usuario '{username}' bloqueado por pre_exec "
                        f"(permiso={permission})",
                    )
                    self._invoke_on_deny(username, permission, context,
                                         "bloqueado por pre_exec hook")
                    self._invoke_post_exec(username, permission, context,
                                           granted=False)
                    return False
            except Exception as exc:
                logger.error(
                    "MultiUserGovernance: pre_exec hook fallo para "
                    "usuario='%s' permiso='%s': %s",
                    username, permission, exc,
                    exc_info=True,
                )
                self._audit(
                    "HOOK_ERROR",
                    f"pre_exec hook error para '{username}': {exc}",
                )
                # Denegar por seguridad ante fallo del hook
                self._invoke_post_exec(username, permission, context,
                                       granted=False)
                return False

        # 4. Verificar permiso en la lista
        has_perm = permission in user.permissions

        # 5. Audit trail y hooks post ejecucion
        if has_perm:
            self._audit(
                "GRANTED",
                f"Usuario '{username}' permiso={permission} concedido",
            )
        else:
            self._audit(
                "DENIED",
                f"Usuario '{username}' permiso={permission} denegado "
                f"(tiene: {user.permissions})",
            )
            self._invoke_on_deny(username, permission, context,
                                 "permiso no asignado")

        self._invoke_post_exec(username, permission, context,
                               granted=has_perm)
        return has_perm

    # ------------------------------------------------------------------
    # Execution hooks
    # ------------------------------------------------------------------

    def set_hooks(self, hooks: ExecutionHooks) -> None:
        """Establecer los execution hooks del sistema.

        Args:
            hooks: Nueva configuracion de hooks.
        """
        self._hooks = hooks
        logger.info("MultiUserGovernance: hooks actualizados")

    def get_hooks(self) -> ExecutionHooks:
        """Obtener la configuracion actual de execution hooks.

        Returns:
            ExecutionHooks: Copia de los hooks actuales.
        """
        return self._hooks

    # ------------------------------------------------------------------
    # Context manager para permisos temporales
    # ------------------------------------------------------------------

    @contextmanager
    def with_permission(self, username: str, permission: str,
                        context: Optional[Dict[str, Any]] = None
                        ) -> Generator[bool, None, None]:
        """Context manager que verifica un permiso y lo concede temporalmente.

        Permite ejecutar un bloque de codigo solo si el usuario tiene el
        permiso especificado. Si no lo tiene, no se ejecuta el bloque.

        Args:
            username: Nombre del usuario.
            permission: Permiso requerido.
            context: Contexto opcional para los hooks.

        Yields:
            bool: True si el permiso fue concedido (el bloque se ejecuta),
                  False si fue denegado.

        Examples:
            >>> gov = MultiUserGovernance()
            >>> gov.add_user("alice", Role.ADMIN)
            >>> with gov.with_permission("alice", "execute_agent") as ok:
            ...     if ok:
            ...         print("Accion permitida")
            Accion permitida
        """
        granted = self.check_permission(username, permission, context)
        yield granted

    # ------------------------------------------------------------------
    # Auditoria
    # ------------------------------------------------------------------

    def _audit(self, action: str, detail: str) -> None:
        """Registrar un evento en el log de auditoria interno.

        Args:
            action: Tipo de accion (GRANTED, DENIED, ADD_USER, etc.).
            detail: Descripcion del evento.
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            username="system",
            action=action,
            detail=detail,
        )
        self._audit_log.append(entry)

    def _audit_with_user(self, username: str, action: str, detail: str) -> None:
        """Registrar un evento de auditoria asociado a un usuario.

        Args:
            username: Usuario que origino el evento.
            action: Tipo de accion.
            detail: Descripcion del evento.
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            username=username,
            action=action,
            detail=detail,
        )
        self._audit_log.append(entry)

    def get_audit_log(self) -> List[AuditEntry]:
        """Obtener una copia del registro completo de auditoria.

        Returns:
            List[AuditEntry]: Copia del log cronologico de eventos.
        """
        return list(self._audit_log)

    def get_audit_log_since(self, since: datetime) -> List[AuditEntry]:
        """Obtener entradas de auditoria desde una fecha especifica.

        Args:
            since: Filtro temporal (UTC). Solo entradas con timestamp >= since.

        Returns:
            List[AuditEntry]: Entradas de auditoria filtradas.
        """
        return [e for e in self._audit_log if e.timestamp >= since]

    def clear_audit_log(self) -> None:
        """Limpiar el registro de auditoria."""
        self._audit_log.clear()
        logger.info("MultiUserGovernance: log de auditoria limpiado")

    def count_audit_entries(self) -> int:
        """Contar el numero total de entradas en el log de auditoria.

        Returns:
            int: Cantidad de entradas registradas.
        """
        return len(self._audit_log)

    def get_audit_summary(self) -> Dict[str, int]:
        """Obtener resumen de eventos de auditoria agrupados por accion.

        Returns:
            Dict[str, int]: Mapa de accion -> cantidad de ocurrencias.
        """
        summary: Dict[str, int] = {}
        for entry in self._audit_log:
            summary[entry.action] = summary.get(entry.action, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # Hooks privados
    # ------------------------------------------------------------------

    def _invoke_on_deny(self, username: str, permission: str,
                        context: Dict[str, Any],
                        reason: Optional[str] = None) -> None:
        """Invocar el hook on_deny si esta configurado.

        Args:
            username: Usuario al que se denego el permiso.
            permission: Permiso denegado.
            context: Contexto de la operacion.
            reason: Razon de la denegacion.
        """
        if self._hooks.on_deny is not None:
            try:
                self._hooks.on_deny(username, permission, context, reason)
            except Exception as exc:
                logger.error(
                    "MultiUserGovernance: on_deny hook fallo para "
                    "usuario='%s' permiso='%s': %s",
                    username, permission, exc,
                    exc_info=True,
                )

    def _invoke_post_exec(self, username: str, permission: str,
                          context: Dict[str, Any], granted: bool) -> None:
        """Invocar el hook post_exec si esta configurado.

        Args:
            username: Usuario que solicito el permiso.
            permission: Permiso verificado.
            context: Contexto de la operacion.
            granted: Si el permiso fue concedido.
        """
        if self._hooks.post_exec is not None:
            try:
                self._hooks.post_exec(username, permission, context, granted)
            except Exception as exc:
                logger.error(
                    "MultiUserGovernance: post_exec hook fallo para "
                    "usuario='%s' permiso='%s': %s",
                    username, permission, exc,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Obtener resumen del estado actual de la gobernanza.

        Returns:
            Dict con: total_users, users_by_role, total_permissions,
            audit_entries, hooks_configurados.
        """
        total_users = len(self._users)
        users_by_role: Dict[str, int] = {}
        total_permissions = 0
        for user in self._users.values():
            role_name = user.role.value
            users_by_role[role_name] = users_by_role.get(role_name, 0) + 1
            total_permissions += len(user.permissions)

        return {
            "total_users": total_users,
            "users_by_role": users_by_role,
            "total_permissions": total_permissions,
            "audit_entries": len(self._audit_log),
            "hooks_configured": {
                "pre_exec": self._hooks.pre_exec is not None,
                "post_exec": self._hooks.post_exec is not None,
                "on_deny": self._hooks.on_deny is not None,
            },
        }

    def has_user(self, username: str) -> bool:
        """Verificar si un usuario existe en el sistema.

        Args:
            username: Nombre del usuario.

        Returns:
            bool: True si el usuario existe.
        """
        return username in self._users

    def get_user_permissions(self, username: str) -> List[str]:
        """Obtener la lista de permisos de un usuario.

        Args:
            username: Nombre del usuario.

        Returns:
            List[str]: Permisos del usuario. Lista vacia si no existe.
        """
        user = self._users.get(username)
        if user is None:
            return []
        return list(user.permissions)

    def get_users_by_role(self, role: Role) -> List[User]:
        """Obtener todos los usuarios que tienen un rol especifico.

        Args:
            role: Rol a filtrar.

        Returns:
            List[User]: Usuarios con ese rol.
        """
        return [u for u in self._users.values() if u.role == role]
