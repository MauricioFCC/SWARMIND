"""MultiUserGovernance core — clase principal ``MultiUserGovernance``.

Extraccion mecanica del modulo original
``harness/orchestrator/multi_user_governance.py`` (sin cambios de logica
ni firmas). La clase compone los mixins por responsabilidad:

- ``_UsersMixin`` (users.py): gestion de usuarios.
- ``_PermissionsMixin`` (permissions.py): verificacion + hooks.
- ``_AuditMixin`` (audit.py): registro de auditoria.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import AuditEntry, ExecutionHooks, Role, User
from .permissions import _PermissionsMixin
from .users import _UsersMixin

logger = logging.getLogger(__name__)


class MultiUserGovernance(_UsersMixin, _PermissionsMixin):
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

    def __init__(self, hooks: ExecutionHooks | None = None) -> None:
        """Inicializar el sistema de gobernanza multi-usuario.

        Args:
            hooks: Configuracion opcional de execution hooks. Si no se
                   proporciona, se usan los hooks por defecto (solo logging).
        """
        self._users: dict[str, User] = {}
        self._audit_log: list[AuditEntry] = []
        self._hooks: ExecutionHooks = hooks or ExecutionHooks()
        logger.info("MultiUserGovernance iniciado con %s", self._hooks)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Obtener resumen del estado actual de la gobernanza.

        Returns:
            Dict con: total_users, users_by_role, total_permissions,
            audit_entries, hooks_configurados.
        """
        total_users = len(self._users)
        users_by_role: dict[str, int] = {}
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

    def get_user_permissions(self, username: str) -> list[str]:
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

    def get_users_by_role(self, role: Role) -> list[User]:
        """Obtener todos los usuarios que tienen un rol especifico.

        Args:
            role: Rol a filtrar.

        Returns:
            List[User]: Usuarios con ese rol.
        """
        return [u for u in self._users.values() if u.role == role]
