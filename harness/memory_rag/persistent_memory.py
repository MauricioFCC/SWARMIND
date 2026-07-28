"""
PersistentMemory — Memoria cross-session tipo Engram para AGENTIC.

Inspirado en Engram (ASDT): persiste el contexto entre sesiones de trabajo
para que los agentes retomen donde dejaron.

Almacena: sesiones, decisiones, contexto de agentes, cache de respuestas.
Formato: JSON local (sin servidor, como LanceDB).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """
    Entrada de memoria persistente.

    Attributes:
        key: Clave unica de la entrada.
        value: Valor almacenado.
        agent: Agente que creo la entrada.
        session_id: Sesion a la que pertenece.
        timestamp: Timestamp de creacion.
        ttl: Time-to-live en segundos (0 = forever).
    """
    key: str
    value: Any
    agent: str
    session_id: str
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    ttl: int = 0


class PersistentMemory:
    """
    Memoria persistente cross-session.

    Almacena y recupera contexto entre sesiones de trabajo.
    Similar a Engram pero integrado con el ecosistema AGENTIC.

    Usage:
        pm = PersistentMemory()
        pm.store("decision:api-design", "REST con Axum", agent="scientist")
        value = pm.recall("decision:api-design")
        session = pm.get_session("session-123")
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        """
        Args:
            path: Ruta al archivo JSON de persistencia.
                  Si es None, usa 'data/persistent_memory.json'.
        """
        self._path = path or Path("data/persistent_memory.json")
        self._data: Dict[str, MemoryEntry] = {}
        self._load()

    def store(self, key: str, value: Any, agent: str = "system",
              session_id: str = "default", ttl: int = 0) -> None:
        """
        Almacenar un valor en memoria persistente.

        Args:
            key: Clave unica para recuperar el valor.
            value: Valor a almacenar (debe ser JSON-serializable).
            agent: Nombre del agente que almacena.
            session_id: Identificador de sesion.
            ttl: Time-to-live en segundos. 0 = vive para siempre.
        """
        self._data[key] = MemoryEntry(
            key=key, value=value, agent=agent,
            session_id=session_id, ttl=ttl,
        )
        self._save()

    def recall(self, key: str) -> Optional[Any]:
        """
        Recuperar un valor por clave.

        Args:
            key: Clave a buscar.

        Returns:
            El valor almacenado o None si no existe o expiro.
        """
        entry = self._data.get(key)
        if not entry:
            return None
        if entry.ttl > 0 and (datetime.now(timezone.utc).timestamp() - entry.timestamp) > entry.ttl:
            del self._data[key]
            self._save()
            return None
        return entry.value

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Recuperar todo el contexto de una sesion.

        Args:
            session_id: Identificador de sesion.

        Returns:
            Dict con clave -> valor de todas las entradas de esa sesion.
        """
        return {
            k: v.value for k, v in self._data.items()
            if v.session_id == session_id
        }

    def get_agent_memory(self, agent: str) -> Dict[str, Any]:
        """
        Recuperar toda la memoria de un agente.

        Args:
            agent: Nombre del agente.

        Returns:
            Dict con clave -> valor de todas las entradas de ese agente.
        """
        return {
            k: v.value for k, v in self._data.items()
            if v.agent == agent
        }

    def get_all_entries(self) -> Dict[str, MemoryEntry]:
        """
        Obtener todas las entradas (para inspeccion).

        Returns:
            Dict con todas las entradas de memoria.
        """
        return dict(self._data)

    def get_stats(self) -> Dict[str, Any]:
        """
        Estadisticas de memoria.

        Returns:
            Dict con total_entries, sessions y agents.
        """
        return {
            "total_entries": len(self._data),
            "sessions": len(set(e.session_id for e in self._data.values())),
            "agents": len(set(e.agent for e in self._data.values())),
        }

    def clear(self) -> None:
        """Limpiar toda la memoria."""
        self._data.clear()
        self._save()

    def _load(self) -> None:
        """Cargar datos desde el archivo JSON."""
        if self._path and self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._data[k] = MemoryEntry(**v)
            except Exception as e:
                logger.warning(f"Failed to load memory from {self._path}: {e}")

    def _save(self) -> None:
        """Guardar datos al archivo JSON."""
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.__dict__ for k, v in self._data.items()}
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

