"""ToolGuardian core — clase principal ``ToolGuardian``.

Extraccion mecanica del modulo original
``harness/orchestrator/tool_guardian.py`` (sin cambios de logica
ni firmas). La clase compone los mixins por responsabilidad:

- ``_PoliciesMixin`` (policies.py): politicas por defecto + CRUD.
- ``_ValidationMixin`` (validation.py): validate_tool_call.
- ``_AnalysisMixin`` (analysis.py): analyze_tool.
- ``_CharacterizationMixin`` (characterization.py): pipeline 4 etapas.
"""

from __future__ import annotations

from .characterization import _CharacterizationMixin
from .models import ToolPolicy
from .validation import _ValidationMixin


class ToolGuardian(_ValidationMixin, _CharacterizationMixin):
    """Guardian de seguridad declarativa para herramientas de agente.

    Implementa progressive characterization pipeline (arXiv:2607.21835)
    con 4 etapas y una policy layer basada en ASP para determinar
    si una tool es segura, sospechosa o maliciosa.

    Examples:
        >>> guardian = ToolGuardian()
        >>> guardian.validate_tool_call("filesystem", "read", {"path": "/tmp"})
        True
        >>> guardian.validate_tool_call("shell", "execute", {"cmd": "rm -rf /"})
        False
    """

    def __init__(self, strict_mode: bool = False) -> None:
        """Inicializa ToolGuardian con politicas por defecto.

        Args:
            strict_mode: Si True, bloquea cualquier accion no explicitamente
                permitida. Si False, permite acciones no listadas como
                bloqueadas.
        """
        self._strict = strict_mode
        self._policies: dict[str, ToolPolicy] = {}
        self._load_default_policies()
