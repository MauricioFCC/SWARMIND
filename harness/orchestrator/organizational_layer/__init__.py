"""OrganizationalLayer — Capa organizacional para sistemas multi-agente (arXiv:2607.25446).

Antes: harness/orchestrator/organizational_layer.py (676 lineas).
Ahora: paquete ``harness/orchestrator/organizational_layer/``:

- ``models.py``: BelbinRole, MintzbergCoordination, CollaborationProtocol,
  RACIMatrix, TeamSpec.
- ``roles.py``: mixin ``_RolesMixin`` (WHO — roles Belbin + coordinacion).
- ``raci.py``: mixin ``_RACIMixin`` (matrices RACI + model binding).
- ``spec.py``: mixin ``_SpecMixin`` (load_spec/to_spec/serializacion).
- ``presets.py``: mixin ``_PresetsMixin`` (presets organizacionales).
- ``core.py``: clase ``OrganizationalLayer`` (estado + __init__).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.organizational_layer import OrganizationalLayer

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .core import OrganizationalLayer
from .models import (
    BelbinRole,
    CollaborationProtocol,
    MintzbergCoordination,
    RACIMatrix,
    TeamSpec,
)

__all__ = [
    "BelbinRole",
    "CollaborationProtocol",
    "MintzbergCoordination",
    "OrganizationalLayer",
    "RACIMatrix",
    "TeamSpec",
]
