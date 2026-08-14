"""MultiUserGovernance — Permisos multi-principal con execution hooks (arXiv:2606.21856).

Antes: harness/orchestrator/multi_user_governance.py (661 lineas).
Ahora: paquete ``harness/orchestrator/multi_user_governance/``:

- ``models.py``: Role, ROLE_PERMISSIONS, _ROLE_HIERARCHY,
  _resolve_role_permissions, hooks types, ExecutionHooks, AuditEntry, User.
- ``users.py``: mixin ``_UsersMixin`` (gestion de usuarios).
- ``permissions.py``: mixin ``_PermissionsMixin`` (verificacion + hooks,
  incluye auditoria fusionada del antiguo ``_AuditMixin``).
- ``core.py``: clase ``MultiUserGovernance`` (estado + __init__).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.multi_user_governance import MultiUserGovernance

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .core import MultiUserGovernance
from .models import (
    _ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
    AuditEntry,
    ExecutionHooks,
    OnDenyHook,
    PostExecHook,
    PreExecHook,
    Role,
    User,
    _resolve_role_permissions,
)
from .permissions import _PermissionsMixin
from .users import _UsersMixin

__all__ = [
    "ROLE_PERMISSIONS",
    "_ROLE_HIERARCHY",
    "AuditEntry",
    "ExecutionHooks",
    "MultiUserGovernance",
    "OnDenyHook",
    "PostExecHook",
    "PreExecHook",
    "Role",
    "User",
    "_PermissionsMixin",
    "_UsersMixin",
    "_resolve_role_permissions",
]
