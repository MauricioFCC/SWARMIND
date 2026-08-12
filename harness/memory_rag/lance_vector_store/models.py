"""Modelos internos del fallback in-memory de ``lance_vector_store``.

Extraido mecanicamente de ``lance_vector_store.py`` (regla AGR < 500 lineas).
Sin cambios de logica: mismas dataclasses, mismos campos y defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class _StoredItem:
    """A single item held in the in-memory fallback store."""
    id: str
    vector: np.ndarray | None
    metadata: dict[str, Any]
    created_at: str


@dataclass
class _Collection:
    """An in-memory collection mirroring a LanceDB table."""
    name: str
    schema_def: dict[str, str]
    items: dict[str, _StoredItem] = field(default_factory=dict)
    last_updated: str = ""
