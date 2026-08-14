"""Federated Memory — sincronizacion automatica de conocimiento entre proyectos.

Antes: harness/orchestrator/federated_memory.py (568 lineas).
Ahora: paquete ``harness/orchestrator/federated_memory/``:

- ``models.py``: ``KnowledgeType`` y ``KnowledgeRecord``.
- ``store_mixin.py``: mixin ``_StoreMixin`` (store/delete/query/stats).
- ``sync_mixin.py``: mixin ``_SyncMixin`` (sync/clear/persistencia/thread).
- ``core.py``: clase ``FederatedMemoryStore`` (estado + __init__).
- ``convenience.py``: ``discover_federated_projects`` y ``sync_all_projects``.

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original (y ``Path`` de pathlib, usado por los tests via patch) para
mantener backward-compat:

    from harness.orchestrator.federated_memory import FederatedMemoryStore

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""
from __future__ import annotations

from pathlib import Path as Path

from .convenience import (
    discover_federated_projects,
    sync_all_projects,
)
from .core import FederatedMemoryStore
from .models import KnowledgeRecord, KnowledgeType

__all__ = [
    "FederatedMemoryStore",
    "KnowledgeRecord",
    "KnowledgeType",
    "discover_federated_projects",
    "sync_all_projects",
]
