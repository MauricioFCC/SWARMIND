"""OrganizationalLayer core — clase principal ``OrganizationalLayer``.

Extraccion mecanica del modulo original
``harness/orchestrator/organizational_layer.py`` (sin cambios de logica
ni firmas). La clase compone los mixins por responsabilidad:

- ``_RolesMixin`` (roles.py): capa WHO (roles Belbin) + HOW (coordinacion).
- ``_RACIMixin`` (raci.py): matrices RACI + model binding.
- ``_SpecMixin`` (spec.py): TeamSpec + serializacion.
- ``_PresetsMixin`` (presets.py): presets organizacionales.
"""

from __future__ import annotations

from .models import BelbinRole, MintzbergCoordination, RACIMatrix
from .raci import _RACIMixin
from .roles import _RolesMixin


class OrganizationalLayer(_RolesMixin, _RACIMixin):
    """Capa organizacional orquestando WHO/HOW/WHICH (arXiv:2607.25446).

    Gestiona roles Belbin, matrices RACI y especificaciones de equipo.
    Sirve como punto único de entrada para la configuración organizacional
    del sistema multi-agente.

    Examples:
        >>> layer = OrganizationalLayer()
        >>> layer.assign_role("agent-a", BelbinRole.SHAPER)
        >>> layer.get_role("agent-a")
        <BelbinRole.SHAPER: 'shaper'>
        >>> raci = layer.create_raci("build-api", "agent-a", "agent-b")
        >>> raci.accountable
        'agent-b'
    """

    def __init__(self) -> None:
        """Inicializa la capa organizacional vacía."""
        self._roles: dict[str, BelbinRole] = {}
        self._raci: dict[str, RACIMatrix] = {}
        self._coordination: MintzbergCoordination = (
            MintzbergCoordination.MUTUAL_ADJUSTMENT
        )
        self._model_binding: dict[str, str] = {}
        self._team_name: str = "default"

    def clear(self) -> None:
        """Limpia toda la configuración organizacional."""
        self._roles.clear()
        self._raci.clear()
        self._model_binding.clear()
        self._coordination = MintzbergCoordination.MUTUAL_ADJUSTMENT
        self._team_name = "default"

    @property
    def team_name(self) -> str:
        """Nombre del preset organizacional activo."""
        return self._team_name

    @property
    def agent_count(self) -> int:
        """Cantidad de agentes con rol asignado."""
        return len(self._roles)

    def __repr__(self) -> str:
        return (
            f"OrganizationalLayer(team='{self._team_name}', "
            f"agents={self.agent_count}, "
            f"coordination={self._coordination.value})"
        )
