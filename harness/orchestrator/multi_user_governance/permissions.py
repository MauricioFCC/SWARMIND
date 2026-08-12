"""MultiUserGovernance permissions — mixin con verificacion y hooks.

Extraccion mecanica del modulo original
``harness/orchestrator/multi_user_governance.py`` (sin cambios de logica
ni firmas): check_permission, set_hooks, get_hooks, with_permission e
invocacion de hooks privados.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .models import AuditEntry, ExecutionHooks

logger = logging.getLogger(__name__)


class _PermissionsMixin:
    """Mixin con verificacion de permisos y execution hooks."""

    # ------------------------------------------------------------------
    # Verificacion de permisos
    # ------------------------------------------------------------------

    def check_permission(self, username: str, permission: str,
                         context: dict[str, Any] | None = None) -> bool:
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
                logger.exception(
                    "MultiUserGovernance: pre_exec hook fallo para "
                    "usuario='%s' permiso='%s'",
                    username, permission,
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
                        context: dict[str, Any] | None = None
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
    # Hooks privados
    # ------------------------------------------------------------------

    def _invoke_on_deny(self, username: str, permission: str,
                        context: dict[str, Any],
                        reason: str | None = None) -> None:
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
            except Exception:
                logger.exception(
                    "MultiUserGovernance: on_deny hook fallo para "
                    "usuario='%s' permiso='%s'",
                    username, permission,
                )

    def _invoke_post_exec(self, username: str, permission: str,
                          context: dict[str, Any], granted: bool) -> None:
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
            except Exception:
                logger.exception(
                    "MultiUserGovernance: post_exec hook fallo para "
                    "usuario='%s' permiso='%s'",
                    username, permission,
                )

    def _audit(self, action: str, detail: str) -> None:
        """Registrar un evento de auditoria (usuario system).

        Args:
            action: Tipo de accion (GRANTED, DENIED, ADD_USER, etc.).
            detail: Descripcion del evento.
        """
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
            username=username,
            action=action,
            detail=detail,
        )
        self._audit_log.append(entry)

    def get_audit_log(self) -> list[AuditEntry]:
        """Obtener una copia del registro completo de auditoria.

        Returns:
            List[AuditEntry]: Copia del log cronologico de eventos.
        """
        return list(self._audit_log)

    def get_audit_log_since(self, since: datetime) -> list[AuditEntry]:
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

    def get_audit_summary(self) -> dict[str, int]:
        """Obtener resumen de eventos de auditoria agrupados por accion.

        Returns:
            Dict[str, int]: Mapa de accion -> cantidad de ocurrencias.
        """
        summary: dict[str, int] = {}
        for entry in self._audit_log:
            summary[entry.action] = summary.get(entry.action, 0) + 1
        return summary
