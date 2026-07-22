"""
Scoped Context Spawn — Aislamiento de contexto por sesion con herencia.

Implementa scopedCtx (ADR-0018): contexto bajo demanda con aislamiento
entre sesiones paralelas. Basado en Symphony-Coord: -44% tiempo.

Usage:
    parent = ScopedContext(name="session-1")
    child = parent.spawn("subtask-1")  # hereda contexto padre
    child.set("key", "value")  # aislamiento: no afecta al padre
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScopedContext:
    """
    Contexto aislado con herencia jerarquica.

    Cada scoped context tiene su propio espacio de claves, pero puede
    heredar del padre bajo demanda. Aislamiento total entre siblings.

    Attributes:
        name: Nombre del contexto (unico por sesion).
        parent: Contexto padre (None si es raiz).
        data: Datos del contexto (aislado).
        created_at: Timestamp de creacion.
    """
    name: str
    parent: Optional[ScopedContext] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _children: List[ScopedContext] = field(default_factory=list)

    def spawn(self, name: str) -> ScopedContext:
        """
        Crear un contexto hijo que hereda del padre.

        Args:
            name: Nombre del nuevo contexto.

        Returns:
            Nuevo ScopedContext con este como padre.
        """
        child = ScopedContext(name=name, parent=self)
        self._children.append(child)
        logger.debug("ScopedContext spawned: %s -> %s", self.name, child.name)
        return child

    def get(self, key: str, default: Any = None, inherit: bool = False) -> Any:
        """
        Obtener valor de una clave.

        Args:
            key: Clave a buscar.
            default: Valor por defecto.
            inherit: Si True, busca tambien en padres.

        Returns:
            Valor de la clave o default si no existe.
        """
        if key in self.data:
            return self.data[key]
        if inherit and self.parent:
            return self.parent.get(key, default, inherit=True)
        return default

    def set(self, key: str, value: Any) -> None:
        """Establecer valor (solo en este contexto, no propaga)."""
        self.data[key] = value

    def snapshot(self) -> Dict[str, Any]:
        """Tomar snapshot completo (propio + herencia plana)."""
        base = {}
        if self.parent:
            base.update(self.parent.snapshot())
        base.update(self.data)
        return base

    @property
    def depth(self) -> int:
        """Profundidad en el arbol de contextos."""
        return 1 + (self.parent.depth if self.parent else 0)

    @property
    def is_root(self) -> bool:
        """Es contexto raiz (sin padre)."""
        return self.parent is None

    @property
    def children(self) -> List[ScopedContext]:
        """Lista de contextos hijos."""
        return list(self._children)
