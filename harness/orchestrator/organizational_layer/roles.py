"""OrganizationalLayer roles — mixin con la capa WHO (roles Belbin).

Extraccion mecanica del modulo original
``harness/orchestrator/organizational_layer.py`` (sin cambios de logica
ni firmas): asignacion de roles, coordinacion Mintzberg, protocolo
activo y consultas por rol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import BelbinRole, CollaborationProtocol, MintzbergCoordination

if TYPE_CHECKING:
    from .core import OrganizationalLayer


class _RolesMixin:
    """Mixin con la capa WHO (roles Belbin) y HOW (coordinacion)."""

    # ── WHO: Roles Belbin ──────────────────────────────────────────────

    def assign_role(self, agent: str, role: BelbinRole) -> None:
        """Asigna un rol Belbin a un agente.

        Args:
            agent: Identificador del agente.
            role: Rol Belbin a asignar.

        Raises:
            TypeError: Si ``role`` no es instancia de BelbinRole.
        """
        if not isinstance(role, BelbinRole):
            raise TypeError(
                f"role debe ser BelbinRole, recibido: {type(role).__name__}"
            )
        self._roles[agent] = role

    def get_role(self, agent: str) -> BelbinRole | None:
        """Obtiene el rol Belbin de un agente.

        Args:
            agent: Identificador del agente.

        Returns:
            BelbinRole del agente o ``None`` si no tiene rol asignado.
        """
        return self._roles.get(agent)

    def remove_role(self, agent: str) -> bool:
        """Remueve el rol de un agente.

        Args:
            agent: Identificador del agente.

        Returns:
            ``True`` si el agente tenía rol, ``False`` en caso contrario.
        """
        return self._roles.pop(agent, None) is not None

    def list_roles(self) -> dict[str, BelbinRole]:
        """Lista todas las asignaciones de roles actuales.

        Returns:
            Dict mapeando agente → BelbinRole.
        """
        return dict(self._roles)

    def has_role(self, agent: str, role: BelbinRole) -> bool:
        """Verifica si un agente tiene un rol específico.

        Args:
            agent: Identificador del agente.
            role: Rol Belbin a verificar.

        Returns:
            ``True`` si el agente tiene exactamente ese rol.
        """
        return self._roles.get(agent) == role

    # ── HOW: Coordinación Mintzberg ────────────────────────────────────

    @property
    def coordination(self) -> MintzbergCoordination:
        """Mecanismo de coordinación activo."""
        return self._coordination

    @coordination.setter
    def coordination(self, mechanism: MintzbergCoordination) -> None:
        """Establece el mecanismo de coordinación.

        Args:
            mechanism: Mecanismo Mintzberg a utilizar.

        Raises:
            TypeError: Si no es instancia de MintzbergCoordination.
        """
        if not isinstance(mechanism, MintzbergCoordination):
            raise TypeError(
                f"mechanism debe ser MintzbergCoordination, "
                f"recibido: {type(mechanism).__name__}"
            )
        self._coordination = mechanism

    # ── WHICH: Protocolo de colaboración ──────────────────────────────

    def get_active_protocol(self) -> CollaborationProtocol:
        """Obtiene el protocolo de colaboración por defecto.

        Returns:
            CollaborationProtocol activo (VOTING por defecto).
        """
        return CollaborationProtocol.VOTING

    # ── Query ─────────────────────────────────────────────────────────

    def find_agents_by_role(self, role: BelbinRole) -> list[str]:
        """Encuentra todos los agentes con un rol específico.

        Args:
            role: Rol Belbin a buscar.

        Returns:
            Lista de identificadores de agentes con ese rol.
        """
        return [agent for agent, r in self._roles.items() if r == role]

    @classmethod
    def from_preset_belbin(cls) -> OrganizationalLayer:
        """Asigna los cinco roles Belbin a agentes con coordinación por
        ajuste mutuo. Es el preset por defecto en IMACS.

        Returns:
            OrganizationalLayer configurada con roles Belbin.
        """
        layer = cls()
        layer._team_name = "belbin"
        layer._coordination = MintzbergCoordination.MUTUAL_ADJUSTMENT
        layer.assign_role("coordinator", BelbinRole.SHAPER)
        layer.assign_role("builder", BelbinRole.IMPLEMENTER)
        layer.assign_role("guardian", BelbinRole.COMPLETER)
        layer.assign_role("scientist", BelbinRole.SPECIALIST)
        layer.assign_role("evolver", BelbinRole.TEAMWORKER)
        return layer

    # Alias backward-compat del nombre original
    from_preset_default = from_preset_belbin

    @classmethod
    def from_preset_adhocracy(cls) -> OrganizationalLayer:
        """Crea capa con preset Adhocracy.

        Equipo flexible con supervisión directa, ideal para generación
        abierta y tareas exploratorias.

        Returns:
            OrganizationalLayer configurada como adhocracy.
        """
        layer = cls()
        layer._team_name = "adhocracy"
        layer._coordination = MintzbergCoordination.DIRECT_SUPERVISION
        layer.assign_role("lead", BelbinRole.SHAPER)
        layer.assign_role("creator", BelbinRole.SPECIALIST)
        layer.assign_role("reviewer", BelbinRole.COMPLETER)
        return layer

    @classmethod
    def from_preset_three_departments(cls) -> OrganizationalLayer:
        """Crea capa con preset Three Departments (Tang dynasty).

        Inspirado en el sistema ministerial Tang con roles jerárquicos
        y supervisión directa. Útil para tareas complejas descomponibles.

        Returns:
            OrganizationalLayer configurada como three-departments.
        """
        layer = cls()
        layer._team_name = "three-departments"
        layer._coordination = MintzbergCoordination.DIRECT_SUPERVISION
        layer.assign_role("chancellor", BelbinRole.SHAPER)
        layer.assign_role("secretary", BelbinRole.IMPLEMENTER)
        layer.assign_role("censor", BelbinRole.COMPLETER)
        layer.assign_role("advisor", BelbinRole.SPECIALIST)
        return layer
