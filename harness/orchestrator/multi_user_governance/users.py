"""MultiUserGovernance users — mixin con gestion de usuarios.

Extraccion mecanica del modulo original
``harness/orchestrator/multi_user_governance.py`` (sin cambios de logica
ni firmas): add_user, remove_user, get_user, get_users,
update_user_role y set_user_enabled.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import Role, User, _resolve_role_permissions

logger = logging.getLogger(__name__)


class _UsersMixin:
    """Mixin con la gestion de usuarios del sistema."""

    # ------------------------------------------------------------------
    # Gestion de usuarios
    # ------------------------------------------------------------------

    def add_user(self, username: str, role: Role, enabled: bool = True,
                 metadata: dict[str, Any] | None = None) -> User:
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

    def get_user(self, username: str) -> User | None:
        """Obtener un usuario por su nombre.

        Args:
            username: Nombre del usuario a buscar.

        Returns:
            Optional[User]: El usuario si existe, None si no.
        """
        return self._users.get(username)

    def get_users(self) -> dict[str, User]:
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
